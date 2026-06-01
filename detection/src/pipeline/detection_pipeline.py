"""Detection Pipeline — Redis 메시지 1건 처리 흐름 (Story 3-4 갱신).

흐름:
  1. CrawlEvent 파싱
  2. CostCap.check_and_hold — 일일 비용 cap 도달 시 sleep
  3. LLMClassifier.classify (RetryHandler 감싸기) — OpenAI 멀티모달 단일 호출
  4. TierRouter.route — type → Tier 매핑
  5. CostCap.record — 누적 비용 갱신
  6. DetectionRepository.save — posts + detections RDS 저장 (Story 3-4 신규)
  7. 구조화 로그 출력

threshold 분기 미사용 (전수 저장 정책 — 부록 A-2).
RDS 저장 실패는 retryable로 보지 않음 — ACK 되지 않고 watchdog이 재시도.
"""

from __future__ import annotations

import os

from detection.src.pipeline.llm_classifier import LLMClassifier
from detection.src.pipeline.tier_router import TierRouter
from detection.src.rate_limit.cost_cap import CostCap
from detection.src.repository.detection_repository import DetectionRepository
from detection.src.retry.retry_handler import RetryHandler
from shared.models.crawl_event import CrawlEvent
from shared.structured_logger import get_logger

_SERVICE_NAME = os.environ.get("SERVICE_NAME", "detection")
_logger = get_logger(__name__)


class DetectionPipeline:
    def __init__(
        self,
        classifier: LLMClassifier,
        tier_router: TierRouter,
        cost_cap: CostCap,
        retry_handler: RetryHandler,
        repository: DetectionRepository | None = None,
    ) -> None:
        self._classifier = classifier
        self._tier_router = tier_router
        self._cost_cap = cost_cap
        self._retry_handler = retry_handler
        self._repository = repository

    def process(self, message: str) -> None:
        event = CrawlEvent.from_json(message)

        self._cost_cap.check_and_hold()

        images: list[str] = list(event.s3_image_paths or event.image_urls or [])

        response = self._retry_handler.execute_with_retry(
            lambda: self._classifier.classify(
                event.raw_text, images=images, source_id=event.source_id
            ),
            message=message,
            post_id=event.post_id,
            correlation_id=event.correlation_id,
        )

        tier = self._tier_router.route(response.type)

        self._cost_cap.record(response.input_tokens, response.output_tokens, self._classifier.model_name)

        if self._repository is not None:
            self._repository.save(
                event=event,
                response=response,
                tier=tier,
                model_version=self._classifier.model_version,
            )

        _logger.info(
            "classification — type=%s tier=%s conf=%.3f cost=$%.5f tokens(in/out)=%d/%d image_observed=%s",
            response.type, tier, response.confidence, response.cost_usd,
            response.input_tokens, response.output_tokens, response.image_observed,
            extra={
                "correlation_id": event.correlation_id,
                "service": _SERVICE_NAME,
                "post_id": event.post_id,
                "tier": tier,
                "model_version": self._classifier.model_version,
            },
        )
