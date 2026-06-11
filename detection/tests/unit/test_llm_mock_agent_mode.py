"""LLMMock 에이전트 모드 — 오프라인 데모 리허설 결정성 (Story 3-9 Task 5).

키워드 기반 시나리오 라우팅: 동일 입력 → 동일 verdict (호출 순서 무관). 실 OpenAI·네트워크 0.
"""

from __future__ import annotations

import pytest

from detection.src.mocks.llm_mock import LLMMock, load_agent_scenarios, select_scenario

_SCENARIOS = [
    {
        "name": "핵_치트",
        "keywords": ["월핵", "에임핵"],
        "triage": {
            "type": "핵_치트", "confidence": 0.97, "game_context": "리니지M",
            "reason_ko": "월핵 판매", "translated_text_ko": None,
            "needs_image": True, "needs_link_trace": False,
            "input_tokens": 120, "output_tokens": 40, "cost_usd": 0.00042,
        },
        "image": {
            "illegal_indicators": ["핵 실행 화면"], "extracted_text": "WallHack v3",
            "summary_ko": "핵 실행 화면", "contributes": True,
            "input_tokens": 900, "output_tokens": 60, "cost_usd": 0.0058,
        },
        "synth": {
            "type": "핵_치트", "confidence": 0.98, "reason_ko": "핵 판매 확정",
            "translated_text_ko": None, "image_observed": True,
            "input_tokens": 1500, "output_tokens": 80, "cost_usd": 0.0080,
        },
    },
    {
        "name": "정상",
        "keywords": ["공략", "패치노트"],
        "default": True,
        "triage": {
            "type": "기타", "confidence": 0.93, "game_context": "리니지",
            "reason_ko": "정상 공략 공유", "translated_text_ko": None,
            "needs_image": False, "needs_link_trace": False,
            "input_tokens": 110, "output_tokens": 30, "cost_usd": 0.00040,
        },
    },
]


def test_select_scenario_keyword_match() -> None:
    sc = select_scenario(_SCENARIOS, "리니지M 월핵 팝니다")
    assert sc["name"] == "핵_치트"


def test_select_scenario_falls_back_to_default() -> None:
    sc = select_scenario(_SCENARIOS, "전혀 매칭 안 되는 본문")
    assert sc["name"] == "정상"  # default=True


def test_agent_mode_triage_is_deterministic() -> None:
    mock = LLMMock(agent_scenarios=_SCENARIOS)
    text = "리니지M 월핵 최신 버전 팝니다"
    out1 = mock.run_structured(
        system_prompt="", user_text=text, schema={}, schema_name="tracker_triage", model="gpt-4o-mini",
    )
    out2 = mock.run_structured(
        system_prompt="", user_text=text, schema={}, schema_name="tracker_triage", model="gpt-4o-mini",
    )
    assert out1 == out2  # 동일 입력 → 동일 출력 (상태 없음)
    parsed, _, _, _ = out1
    assert parsed["type"] == "핵_치트"
    assert parsed["needs_image"] is True


def test_agent_mode_routes_image_and_synth_by_schema_name() -> None:
    mock = LLMMock(agent_scenarios=_SCENARIOS)
    text = "에임핵 판매"
    img, *_ = mock.run_structured(
        system_prompt="", user_text=text, schema={}, schema_name="tracker_image_analysis", model="gpt-4o",
    )
    assert img["contributes"] is True
    synth, *_ = mock.run_structured(
        system_prompt="", user_text=text, schema={}, schema_name="tracker_synthesis", model="gpt-4o",
    )
    assert synth["type"] == "핵_치트"
    assert synth["image_observed"] is True


def test_agent_mode_synth_derives_from_triage_when_absent() -> None:
    """synth fixture 없는 시나리오(정상 등) — 트리아지 verdict로 합성 파생 (KeyError 금지)."""
    mock = LLMMock(agent_scenarios=_SCENARIOS)
    synth, *_ = mock.run_structured(
        system_prompt="", user_text="패치노트 공유합니다", schema={},
        schema_name="tracker_synthesis", model="gpt-4o",
    )
    assert synth["type"] == "기타"
    assert synth["image_observed"] is False


def test_agent_mode_order_independent() -> None:
    """호출 순서를 섞어도 같은 본문 → 같은 결과 (큐 방식의 순서 의존 버그 회피)."""
    mock = LLMMock(agent_scenarios=_SCENARIOS)
    a = mock.run_structured(system_prompt="", user_text="에임핵", schema={}, schema_name="tracker_triage", model="m")
    _ = mock.run_structured(system_prompt="", user_text="공략", schema={}, schema_name="tracker_triage", model="m")
    b = mock.run_structured(system_prompt="", user_text="에임핵", schema={}, schema_name="tracker_triage", model="m")
    assert a == b


def test_demo_fixture_has_ten_scenarios() -> None:
    """리허설 fixture는 명확 불법 + 정상 혼합 10건 — 결정성 보장 (각 keywords 비어있지 않음)."""
    scenarios = load_agent_scenarios()
    assert len(scenarios) == 10
    for sc in scenarios:
        assert sc.get("keywords"), f"scenario {sc.get('name')} missing keywords"
        assert "triage" in sc


def test_demo_fixture_scenarios_are_deterministic() -> None:
    scenarios = load_agent_scenarios()
    mock = LLMMock(agent_scenarios=scenarios)
    for sc in scenarios:
        text = sc["keywords"][0]
        r1, *_ = mock.run_structured(
            system_prompt="", user_text=text, schema={}, schema_name="tracker_triage", model="m",
        )
        r2, *_ = mock.run_structured(
            system_prompt="", user_text=text, schema={}, schema_name="tracker_triage", model="m",
        )
        assert r1 == r2
        assert r1["type"] == sc["triage"]["type"]


def test_agent_mode_rejects_unknown_scenario_shape() -> None:
    with pytest.raises((KeyError, ValueError)):
        LLMMock(agent_scenarios=[{"name": "broken"}])  # triage 없음
