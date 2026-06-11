"""LLM Mock — OpenAI 멀티모달 응답 시뮬레이터 (Story 3-3 / 3-8 확장).

mode 4종(clean/illegal/timeout/rate_limited)을 제공하고,
응답 스키마는 SPIKE 3.0 `CLASSIFICATION_SCHEMA`에 맞춰 `LLMResponse`를 사용.
Story 3-8: `run_structured`가 schema_name으로 에이전트 종류를 식별 —
S2a(`tracker_image_analysis`)·S3(`tracker_synthesis`)는 전용 fixture
(`mock_image_{mode}.json` / `mock_synth_{mode}.json`)로 응답한다.
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

    def _load_aux(self, kind: str) -> dict:
        """에이전트 전용 fixture 로드 (kind: image|synth) — 모드별, lazy + 캐시."""
        if not hasattr(self, "_aux_cache"):
            self._aux_cache: dict[str, dict] = {}
        if kind not in self._aux_cache:
            path = _FIXTURES / f"mock_{kind}_{self._mode}.json"
            with path.open(encoding="utf-8") as f:
                self._aux_cache[kind] = json.load(f)
        return self._aux_cache[kind]

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
        image_blocks: list[dict] | None = None,
    ) -> tuple[dict, int, int, float]:
        """LLMClient.run_structured 시그니처 호환 — agentic 경로 통합 테스트용.

        schema_name으로 에이전트 종류 분기:
        - tracker_image_analysis(S2a) → mock_image_{mode}.json (4필드)
        - tracker_synthesis(S3)      → mock_synth_{mode}.json (5필드)
        - 그 외(트리아지 등)          → mock_response_{mode}.json (7필드)
        timeout/rate_limited 모드는 classify와 동일하게 예외를 던져 retry/DLQ를 검증할 수 있다.
        """
        self._sleep()
        if self._mode == "rate_limited":
            raise RateLimitError(self._data.get("retry_after_seconds", 30))
        if self._mode == "timeout":
            raise TimeoutError("LLM API timeout")

        if schema_name == "tracker_image_analysis":
            data = self._load_aux("image")
            parsed = {
                "illegal_indicators": list(data.get("illegal_indicators", [])),
                "extracted_text": data.get("extracted_text", ""),
                "summary_ko": data.get("summary_ko", ""),
                "contributes": bool(data.get("contributes", False)),
            }
        elif schema_name == "tracker_synthesis":
            data = self._load_aux("synth")
            parsed = {
                "type": data["type"],
                "confidence": data["confidence"],
                "reason_ko": data["reason_ko"],
                "translated_text_ko": data.get("translated_text_ko"),
                "image_observed": bool(data.get("image_observed", False)),
            }
        else:
            data = self._data
            parsed = {
                "type": data["type"],
                "confidence": data["confidence"],
                "game_context": data.get("game_context", "불명"),
                "reason_ko": data["reason_ko"],
                "translated_text_ko": data.get("translated_text_ko"),
                "needs_image": bool(data.get("needs_image", False)),
                "needs_link_trace": bool(data.get("needs_link_trace", False)),
            }
        in_tok = int(data.get("input_tokens", 0))
        out_tok = int(data.get("output_tokens", 0))
        cost = float(data.get("cost_usd", 0.0))
        return parsed, in_tok, out_tok, cost
