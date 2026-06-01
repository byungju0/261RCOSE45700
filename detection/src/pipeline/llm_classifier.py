"""LLM Classifier — LLMInterface 위임 + 응답 스키마 방어적 검증 (Story 3-3, 2026-05-27 PIVOT).

OpenAI 멀티모달 단일 호출 의미론으로 분류 결과를 검증.
type enum(9종) + confidence 범위(0~1) 검증은 `LLMClient`가 이미 수행하지만 본 클래스에서
한 번 더 가드 — 다중 worker / mock 객체 / 향후 backend 교체 대비.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from detection.src.rate_limit.token_bucket import TokenBucket
from shared.interfaces.llm import ALLOWED_DETECTION_TYPES, LLMInterface, LLMResponse
from shared.structured_logger import get_logger

_SERVICE_NAME = os.environ.get("SERVICE_NAME", "detection")

_logger = get_logger(__name__)


def _resolve_model_version() -> str:
    """`openai:{model}:{release_date}` 포맷 (Story 3-4 RDS 매핑용)."""
    model = os.environ.get("LLM_MODEL", "gpt-4o")
    release = os.environ.get("LLM_MODEL_RELEASE_DATE")
    if not release:
        release = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"openai:{model}:{release}"


class LLMClassifier:
    def __init__(
        self,
        llm: LLMInterface,
        token_bucket: TokenBucket,
        model_version: str | None = None,
    ) -> None:
        self._llm = llm
        self._bucket = token_bucket
        self._model_version = model_version or _resolve_model_version()

    @property
    def model_version(self) -> str:
        return self._model_version

    @property
    def model_name(self) -> str:
        """'openai:{model}:{date}' 포맷에서 model 부분만 반환. CostCap.record 용."""
        parts = self._model_version.split(":", 2)
        return parts[1] if len(parts) >= 2 else self._model_version

    def classify(
        self, text: str, images: list[str] | None = None, source_id: str | None = None
    ) -> LLMResponse:
        self._bucket.acquire()
        result = self._llm.classify(text, images, source_id=source_id)

        if result.type not in ALLOWED_DETECTION_TYPES:
            raise ValueError(f"invalid type: {result.type}")
        if not 0.0 <= result.confidence <= 1.0:
            raise ValueError(f"confidence out of range: {result.confidence}")

        return result
