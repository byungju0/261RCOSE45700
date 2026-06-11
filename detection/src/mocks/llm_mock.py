"""LLM Mock — OpenAI 멀티모달 응답 시뮬레이터 (Story 3-3 / 3-8 / 3-9 확장).

mode 4종(clean/illegal/timeout/rate_limited)을 제공하고,
응답 스키마는 SPIKE 3.0 `CLASSIFICATION_SCHEMA`에 맞춰 `LLMResponse`를 사용.
Story 3-8: `run_structured`가 schema_name으로 에이전트 종류를 식별 —
S2a(`tracker_image_analysis`)·S3(`tracker_synthesis`)는 전용 fixture
(`mock_image_{mode}.json` / `mock_synth_{mode}.json`)로 응답한다.
Story 3-9: **에이전트 모드** — `agent_scenarios`를 주입하면 `run_structured`가 본문 키워드로
시나리오를 라우팅해 게시글별 결정론적 verdict를 낸다(오프라인 데모 리허설, 실 OpenAI 0).
단일 mode 1응답의 한계(10건 각각 다른 결과 불가)를 키워드 매핑으로 해소 — 큐 방식과 달리
호출 순서에 의존하지 않아 escalate 분기(triage→image→synth)에서도 안정적.
통합 테스트에서 외부 OpenAI 호출 0건 보장.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from shared.interfaces.llm import LLMResponse, RateLimitError

# detection/src/mocks/ → parents[3] == 프로젝트 루트
_FIXTURES = Path(__file__).parents[3] / "tests" / "fixtures" / "llm"
_VALID_MODES = {"clean", "illegal", "rate_limited", "timeout"}
# 데모 리허설 시나리오 fixture (Story 3-9) — 명확 불법 + 정상 혼합 10건.
_AGENT_SCENARIOS_FILE = _FIXTURES / "mock_agent_scenarios.json"


def load_agent_scenarios(path: Path | None = None) -> list[dict[str, Any]]:
    """데모 리허설 시나리오 목록 로드 (기본: mock_agent_scenarios.json)."""
    with (path or _AGENT_SCENARIOS_FILE).open(encoding="utf-8") as f:
        return json.load(f)


def select_scenario(
    scenarios: list[dict[str, Any]], user_text: str
) -> dict[str, Any] | None:
    """본문 키워드 → 시나리오 (등록 순서대로 첫 매칭). 미매칭은 default=True 또는 첫 시나리오.

    순수 함수 — 호출 순서·상태 무관(결정성). 빈 목록은 None.
    """
    text = user_text or ""
    for scenario in scenarios:
        for keyword in scenario.get("keywords", []):
            if keyword and keyword in text:
                return scenario
    for scenario in scenarios:
        if scenario.get("default"):
            return scenario
    return scenarios[0] if scenarios else None


class LLMMock:
    """LLMInterface Protocol 구현체 — 통합 테스트 전용."""

    def __init__(
        self,
        mode: str = "clean",
        latency_ms: int = 0,
        agent_scenarios: list[dict[str, Any]] | None = None,
    ) -> None:
        if mode not in _VALID_MODES:
            raise ValueError(f"unsupported LLM mock mode: {mode}")
        self._mode = mode
        self._latency_ms = latency_ms
        self._data: dict = self._load(mode)
        self._scenarios = agent_scenarios
        if agent_scenarios is not None:
            # 데모 리허설(Story 3-9) — 각 시나리오는 triage 응답 + _run_scenario가 하드키로
            # 역참조하는 필수 필드(type/confidence/reason_ko)를 가져야 한다. 키 존재만 봐서는
            # 무음 KeyError를 못 막으므로(가드가 한 단계 아래로 밀릴 뿐) 하위필드까지 구성 시점에 검증.
            _required_triage = ("type", "confidence", "reason_ko")
            for scenario in agent_scenarios:
                triage = scenario.get("triage")
                if not isinstance(triage, dict):
                    raise ValueError(
                        f"agent_scenario {scenario.get('name')!r} missing 'triage' payload"
                    )
                missing = [k for k in _required_triage if k not in triage]
                if missing:
                    raise ValueError(
                        f"agent_scenario {scenario.get('name')!r} triage missing fields: {missing}"
                    )

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

        # 에이전트 모드(Story 3-9) — 본문 키워드로 시나리오 라우팅(게시글별 결정론적 verdict).
        if self._scenarios is not None:
            return self._run_scenario(user_text, schema_name)

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

    def _run_scenario(
        self, user_text: str, schema_name: str
    ) -> tuple[dict, int, int, float]:
        """에이전트 모드 — 본문 키워드로 시나리오를 고르고 schema_name별 payload 반환 (3-9).

        image/synth fixture가 없는 시나리오(정상 등)는 triage로부터 결정론적으로 파생 —
        fast-path만 타는 게시글은 triage만 정의하면 충분하도록(fixture 간결성).
        """
        assert self._scenarios is not None
        scenario = select_scenario(self._scenarios, user_text)
        if scenario is None:
            raise ValueError("no agent scenario available for routing")
        triage = scenario["triage"]

        if schema_name == "tracker_image_analysis":
            payload = scenario.get("image") or {
                "illegal_indicators": [], "extracted_text": "", "summary_ko": "",
                "contributes": False,
            }
            parsed = {
                "illegal_indicators": list(payload.get("illegal_indicators", [])),
                "extracted_text": payload.get("extracted_text", ""),
                "summary_ko": payload.get("summary_ko", ""),
                "contributes": bool(payload.get("contributes", False)),
            }
            data = payload
        elif schema_name == "tracker_synthesis":
            # synth 미정의 → triage verdict로 파생 (image_observed는 image.contributes 반영).
            image = scenario.get("image") or {}
            payload = scenario.get("synth") or {
                "type": triage["type"],
                "confidence": triage["confidence"],
                "reason_ko": triage["reason_ko"],
                "translated_text_ko": triage.get("translated_text_ko"),
                "image_observed": bool(image.get("contributes", False)),
            }
            parsed = {
                "type": payload["type"],
                "confidence": payload["confidence"],
                "reason_ko": payload["reason_ko"],
                "translated_text_ko": payload.get("translated_text_ko"),
                "image_observed": bool(payload.get("image_observed", False)),
            }
            data = payload
        else:  # tracker_triage 등
            parsed = {
                "type": triage["type"],
                "confidence": triage["confidence"],
                "game_context": triage.get("game_context", "불명"),
                "reason_ko": triage["reason_ko"],
                "translated_text_ko": triage.get("translated_text_ko"),
                "needs_image": bool(triage.get("needs_image", False)),
                "needs_link_trace": bool(triage.get("needs_link_trace", False)),
            }
            data = triage

        in_tok = int(data.get("input_tokens", 0))
        out_tok = int(data.get("output_tokens", 0))
        cost = float(data.get("cost_usd", 0.0))
        return parsed, in_tok, out_tok, cost
