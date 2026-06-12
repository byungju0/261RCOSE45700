"""Detection Pipeline — Redis 메시지 1건 처리 흐름 (Story 3-4 / 3-7 갱신).

흐름:
  1. CrawlEvent 파싱
  2. CostCap.check_and_hold — 일일 비용 cap 도달 시 sleep
  3. DETECTION_MODE 분기:
     - single : LLMClassifier.classify — OpenAI 멀티모달 단일 호출 (기존 경로)
     - agentic: AgentOrchestrator.run — S0→S1→(fast path|escalate→degrade) (Story 3-7)
     (둘 다 RetryHandler로 감싸 transient 오류 재시도)
  4. TierRouter.route — type → Tier 매핑
  5. CostCap.record — 누적 비용 갱신
  6. DetectionRepository.save — posts + detections (+ agentic이면 agent_runs) RDS 저장
  7. 구조화 로그 출력

threshold 분기 미사용 (전수 저장 정책 — 부록 A-2).
RDS 저장 실패는 retryable로 보지 않음 — ACK 되지 않고 watchdog이 재시도.
출력 계약 불변: 두 모드 모두 detections에 동일한 5필드(+ 파생 tier/is_illegal)를 채운다 (AC #13).
"""

from __future__ import annotations

import os

from detection.src.agents.contracts import AgentRunTrace
from detection.src.agents.orchestrator import AgentOrchestrator
from detection.src.pipeline.llm_classifier import LLMClassifier
from detection.src.pipeline.tier_router import TierRouter
from detection.src.rate_limit.cost_cap import CostCap
from detection.src.repository.detection_repository import DetectionRepository
from detection.src.retry.retry_handler import RetryHandler
from shared.interfaces.llm import LLMResponse
from shared.models.crawl_event import CrawlEvent
from shared.structured_logger import get_logger

_SERVICE_NAME = os.environ.get("SERVICE_NAME", "detection")
_logger = get_logger(__name__)


def _classification_images(event: CrawlEvent) -> list[str]:
    """분류기에 전달할 이미지 후보.

    S3 archive 경로는 현재 presigned URL이 아니면 LLMClient가 스킵한다. 따라서 원본
    HTTP 이미지 URL을 함께 보존해, S3 업로드가 켜져도 비전 입력이 조용히 사라지지
    않도록 한다. 순서는 즉시 사용 가능한 원본 URL 우선, 보관 경로 후순위.
    """
    images: list[str] = []
    seen: set[str] = set()
    for image in [*event.image_urls, *event.s3_image_paths]:
        if image and image not in seen:
            images.append(image)
            seen.add(image)
    return images


class DetectionPipeline:
    def __init__(
        self,
        classifier: LLMClassifier,
        tier_router: TierRouter,
        cost_cap: CostCap,
        retry_handler: RetryHandler,
        repository: DetectionRepository | None = None,
        orchestrator: AgentOrchestrator | None = None,
        mode: str | None = None,
    ) -> None:
        self._classifier = classifier
        self._tier_router = tier_router
        self._cost_cap = cost_cap
        self._retry_handler = retry_handler
        self._repository = repository
        self._orchestrator = orchestrator
        self._mode = (mode or os.environ.get("DETECTION_MODE", "single")).strip().lower()

    def process(self, message: str) -> None:
        event = CrawlEvent.from_json(message)

        self._cost_cap.check_and_hold()

        use_agentic = self._mode == "agentic" and self._orchestrator is not None

        if self._mode == "agentic" and self._orchestrator is None:
            _logger.warning(
                "DETECTION_MODE=agentic이지만 orchestrator가 None — single 모드로 폴백 (DI 설정 확인 필요)",
                extra={"correlation_id": event.correlation_id, "service": _SERVICE_NAME},
            )

        if use_agentic:
            response, traces, model_version, model_name = self._run_agentic(message, event)
        else:
            response, traces, model_version, model_name = self._run_single(message, event)

        tier = self._tier_router.route(response.type)

        self._cost_cap.record(response.input_tokens, response.output_tokens, model_name)

        if self._repository is not None:
            self._repository.save(
                event=event,
                response=response,
                tier=tier,
                model_version=model_version,
                agent_runs=traces,
            )

        actual_mode = "agentic" if use_agentic else "single"
        _logger.info(
            "classification — mode=%s type=%s tier=%s conf=%.3f cost=$%.5f tokens(in/out)=%d/%d image_observed=%s",
            actual_mode, response.type, tier, response.confidence, response.cost_usd,
            response.input_tokens, response.output_tokens, response.image_observed,
            extra={
                "correlation_id": event.correlation_id,
                "service": _SERVICE_NAME,
                "post_id": event.post_id,
                "tier": tier,
                "model_version": model_version,
                "detection_mode": actual_mode,
            },
        )

    def _run_single(
        self, message: str, event: CrawlEvent
    ) -> tuple[LLMResponse, list[AgentRunTrace] | None, str, str]:
        images = _classification_images(event)
        response = self._retry_handler.execute_with_retry(
            lambda: self._classifier.classify(
                event.raw_text, images=images, source_id=event.source_id
            ),
            message=message,
            post_id=event.post_id,
            correlation_id=event.correlation_id,
        )
        return response, None, self._classifier.model_version, self._classifier.model_name

    def _run_agentic(
        self, message: str, event: CrawlEvent
    ) -> tuple[LLMResponse, list[AgentRunTrace], str, str]:
        assert self._orchestrator is not None
        verdict, traces = self._retry_handler.execute_with_retry(
            lambda: self._orchestrator.run(event.raw_text, correlation_id=event.correlation_id),
            message=message,
            post_id=event.post_id,
            correlation_id=event.correlation_id,
        )
        return verdict, traces, self._orchestrator.model_version, self._orchestrator.model_name
