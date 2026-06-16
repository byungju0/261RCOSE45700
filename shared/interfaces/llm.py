"""LLM Protocol — Story 3-3 (2026-05-27 PIVOT).

OpenAI 멀티모달 LLM 단일 호출 계약.
구 분류 계약은 본 모듈로 이전됨.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

# detection type enum 단일 정의 — llm_client / llm_classifier 양쪽에서 import.
ALLOWED_DETECTION_TYPES: frozenset[str] = frozenset({
    "핵_치트", "사설서버", "불법프로그램_배포",
    "계정_거래", "매크로_판매",
    "리세마라", "현금화", "광고_도배",
    "기타",
})


def validate_detection_fields(type_value: object, confidence: object, *, context: str = "") -> float:
    """type enum(9종) + confidence 범위(0~1) 검증, 정규화된 confidence(float) 반환.

    llm_classifier / llm_client / triage_agent가 각자 레이어에서 동일 검증을 반복 수행하는
    의도된 다중 방어(multi worker / mock 객체 / 향후 backend 교체 대비)이므로, 호출부는 그대로 두고
    검증 로직만 여기로 모은다.
    """
    prefix = f"{context} " if context else ""
    if type_value not in ALLOWED_DETECTION_TYPES:
        raise ValueError(f"invalid {prefix}type: {type_value}")
    if not isinstance(confidence, (int, float)) or not 0.0 <= float(confidence) <= 1.0:
        raise ValueError(f"{prefix}confidence out of range: {confidence}")
    return float(confidence)


@dataclass
class LLMResponse:
    """OpenAI 멀티모달 단일 호출 응답.

    SPIKE 3.0의 `CLASSIFICATION_SCHEMA` 5필드 + token usage + 비용.
    Story 3-4에서 RDS `detections` 테이블에 그대로 매핑.
    """

    type: str
    confidence: float
    reason_ko: str
    translated_text_ko: str | None
    image_observed: bool
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


# RateLimitError는 OpenAI 429 / rate-limited mock을 호출자에게 통보하는 본 모듈 공용 예외.
class RateLimitError(Exception):
    """LLM API rate limit 또는 quota 초과. 호출자가 Retry-After sleep 후 자체 재시도."""

    def __init__(self, retry_after: int = 30) -> None:
        self.retry_after = retry_after
        super().__init__(f"LLM rate limit exceeded. Retry after {retry_after}s")


@runtime_checkable
class LLMInterface(Protocol):
    """텍스트(+선택적 이미지) 분류 인터페이스.

    Raises:
        RateLimitError: API quota 초과. RetryHandler가 catch하지 않음(호출자 책임).
        TimeoutError / ConnectionError / httpx.HTTPError / openai.APITimeoutError /
            openai.APIConnectionError: RetryHandler retryable.
        ValueError: 응답 스키마 위반(type enum / confidence 범위 등) — non-retryable.
    """

    def classify(
        self, text: str, images: list[str] | None = None, source_id: str | None = None
    ) -> LLMResponse: ...
