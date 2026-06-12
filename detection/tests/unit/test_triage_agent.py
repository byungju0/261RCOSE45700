"""S1 TriageAgent 단위 테스트 (Story 3-7) — 7필드 산출 + 검증 + LLMClient 재사용."""

from __future__ import annotations

import pytest

from detection.src.agents.contracts import TriageResult
from detection.src.agents.triage_agent import TRIAGE_SCHEMA, TriageAgent


class _StubLLM:
    """LLMClient.run_structured 시그니처만 흉내내는 스텁."""

    def __init__(self, parsed: dict, tokens=(100, 30), cost=0.00042) -> None:
        self._parsed = parsed
        self._tokens = tokens
        self._cost = cost
        self.last_call: dict | None = None

    def run_structured(self, *, system_prompt, user_text, schema, schema_name, model):
        self.last_call = {
            "system_prompt": system_prompt,
            "user_text": user_text,
            "schema": schema,
            "schema_name": schema_name,
            "model": model,
        }
        return self._parsed, self._tokens[0], self._tokens[1], self._cost


def _triage_payload(**overrides) -> dict:
    base = {
        "type": "핵_치트",
        "confidence": 0.88,
        "game_context": "리니지M(TW)",
        "reason_ko": "핵 배포 정황.",
        "translated_text_ko": "외부 핵 다운로드",
        "needs_image": False,
        "needs_link_trace": True,
    }
    base.update(overrides)
    return base


def test_run_returns_triage_result_with_all_fields() -> None:
    stub = _StubLLM(_triage_payload())
    agent = TriageAgent(stub, model="gpt-4o-mini")
    result = agent.run("ㅎr킹 팝니다 https://evil.example")

    assert isinstance(result, TriageResult)
    assert result.type == "핵_치트"
    assert result.confidence == 0.88
    assert result.game_context == "리니지M(TW)"
    assert result.needs_link_trace is True
    assert result.needs_image is False
    assert result.cost_usd == 0.00042
    assert result.input_tokens == 100


def test_run_uses_triage_model_and_schema() -> None:
    stub = _StubLLM(_triage_payload())
    agent = TriageAgent(stub, model="gpt-4o-mini")
    agent.run("게시글")

    assert stub.last_call["model"] == "gpt-4o-mini"
    assert stub.last_call["schema"] is TRIAGE_SCHEMA
    assert stub.last_call["schema_name"] == "tracker_triage"
    # 공용 도메인 가이드 + 트리아지 지침이 system prompt에 포함됐는지.
    assert "공용 도메인 가이드" in stub.last_call["system_prompt"]
    assert "트리아지 단계 지침" in stub.last_call["system_prompt"]


def test_model_from_env_when_not_passed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRIAGE_MODEL", "gpt-4o-mini-custom")
    agent = TriageAgent(_StubLLM(_triage_payload()))
    assert agent.model == "gpt-4o-mini-custom"


def test_invalid_type_rejected() -> None:
    stub = _StubLLM(_triage_payload(type="존재하지않는유형"))
    agent = TriageAgent(stub)
    with pytest.raises(ValueError, match="invalid triage type"):
        agent.run("게시글")


def test_confidence_out_of_range_rejected() -> None:
    stub = _StubLLM(_triage_payload(confidence=1.5))
    agent = TriageAgent(stub)
    with pytest.raises(ValueError, match="confidence out of range"):
        agent.run("게시글")
