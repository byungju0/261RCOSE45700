"""LLM Mock — OpenAI 멀티모달 응답 시뮬레이터 (Story 3-3, 2026-05-27 PIVOT).

mode 4종(clean/illegal/timeout/rate_limited)을 제공하고,
응답 스키마는 SPIKE 3.0 `CLASSIFICATION_SCHEMA`에 맞춰 `LLMResponse`를 사용.
통합 테스트에서 외부 OpenAI 호출 0건 보장.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from shared.interfaces.llm import LLMResponse, RateLimitError

# detection/src/mocks/ → parents[3] == 프로젝트 루트
_FIXTURES = Path(__file__).parents[3] / "tests" / "fixtures" / "llm"
_VALID_MODES = {"clean", "illegal", "rate_limited", "timeout"}


class LLMMock:
    """LLMInterface Protocol 구현체 — 통합 테스트 전용."""

    def __init__(self, mode: str = "clean", latency_ms: int = 0) -> None:
        if mode not in _VALID_MODES:
            raise ValueError(f"unsupported LLM mock mode: {mode}")
        self._mode = mode
        self._latency_ms = latency_ms
        self._data: dict = self._load(mode)

    def _load(self, mode: str) -> dict:
        path = _FIXTURES / f"mock_response_{mode}.json"
        with path.open(encoding="utf-8") as f:
            return json.load(f)

    def simulate_latency(self, ms: int) -> None:
        self._latency_ms = ms

    def _sleep(self) -> None:
        if self._latency_ms > 0:
            time.sleep(self._latency_ms / 1000)

    def classify(
        self, text: str, images: list[str] | None = None, source_id: str | None = None
    ) -> LLMResponse:
        # source_id는 mock 분류에 영향 없음 — Protocol 시그니처 일치를 위해 수용.
        self._sleep()
        if self._mode == "rate_limited":
            raise RateLimitError(self._data.get("retry_after_seconds", 30))
        if self._mode == "timeout":
            raise TimeoutError("LLM API timeout")
        image_observed = bool(images) and self._data.get("image_observed", False)
        return LLMResponse(
            type=self._data["type"],
            confidence=self._data["confidence"],
            reason_ko=self._data["reason_ko"],
            translated_text_ko=self._data.get("translated_text_ko"),
            image_observed=image_observed,
            input_tokens=int(self._data.get("input_tokens", 0)),
            output_tokens=int(self._data.get("output_tokens", 0)),
            cost_usd=float(self._data.get("cost_usd", 0.0)),
        )

    def run_structured(
        self,
        *,
        system_prompt: str,
        user_text: str,
        schema: dict,
        schema_name: str,
        model: str,
    ) -> tuple[dict, int, int, float]:
        """LLMClient.run_structured 시그니처 호환 — agentic 경로(S1 트리아지) 통합 테스트용.

        fixture의 type/confidence/reason_ko/translated_text_ko + 트리아지 7필드 추가분
        (game_context/needs_image/needs_link_trace)을 반환한다. timeout/rate_limited 모드는
        classify와 동일하게 예외를 던져 에이전트 경로의 retry/DLQ를 검증할 수 있다.
        """
        self._sleep()
        if self._mode == "rate_limited":
            raise RateLimitError(self._data.get("retry_after_seconds", 30))
        if self._mode == "timeout":
            raise TimeoutError("LLM API timeout")
        parsed = {
            "type": self._data["type"],
            "confidence": self._data["confidence"],
            "game_context": self._data.get("game_context", "불명"),
            "reason_ko": self._data["reason_ko"],
            "translated_text_ko": self._data.get("translated_text_ko"),
            "needs_image": bool(self._data.get("needs_image", False)),
            "needs_link_trace": bool(self._data.get("needs_link_trace", False)),
        }
        in_tok = int(self._data.get("input_tokens", 0))
        out_tok = int(self._data.get("output_tokens", 0))
        cost = float(self._data.get("cost_usd", 0.0))
        return parsed, in_tok, out_tok, cost
