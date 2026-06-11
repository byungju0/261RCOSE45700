"""S3 Synthesizer 단위 테스트 (Story 3-8) — 증거 직렬화 + 5필드 verdict + 방어 검증."""

from __future__ import annotations

import pytest

from detection.src.agents.contracts import ImageEvidence, LinkEvidence, TriageResult
from detection.src.agents.synthesizer import Synthesizer
from detection.src.pipeline.llm_client import CLASSIFICATION_SCHEMA
from shared.interfaces.llm import LLMResponse


class _StubLLM:
    def __init__(self, parsed: dict, tokens=(1500, 80), cost=0.008) -> None:
        self._parsed = parsed
        self._tokens = tokens
        self._cost = cost
        self.last_call: dict | None = None

    def run_structured(self, *, system_prompt, user_text, schema, schema_name, model, image_blocks=None):
        self.last_call = {
            "system_prompt": system_prompt,
            "user_text": user_text,
            "schema": schema,
            "schema_name": schema_name,
            "model": model,
            "image_blocks": image_blocks,
        }
        return self._parsed, self._tokens[0], self._tokens[1], self._cost


def _synth_payload(**overrides) -> dict:
    base = {
        "type": "핵_치트",
        "confidence": 0.97,
        "reason_ko": "링크 추적 결과 다운로드 페이지가 확인되어 핵 배포로 판정.",
        "translated_text_ko": None,
        "image_observed": True,
    }
    base.update(overrides)
    return base


def _triage(**overrides) -> TriageResult:
    base = dict(
        type="핵_치트", confidence=0.78, game_context="리니지M(TW)",
        reason_ko="핵 배포 정황.", translated_text_ko="외부 핵 다운로드",
        needs_image=True, needs_link_trace=True,
        input_tokens=100, output_tokens=30, cost_usd=0.00042,
    )
    base.update(overrides)
    return TriageResult(**base)


def _image_evidence() -> ImageEvidence:
    return ImageEvidence(
        illegal_indicators=["핵 UI 오버레이"],
        extracted_text="ESP aimbot",
        summary_ko="핵 실행 화면 확인.",
        contributes=True,
        input_tokens=900, output_tokens=60, cost_usd=0.0058,
    )


def _link_evidence() -> list[LinkEvidence]:
    return [LinkEvidence(
        url="https://evil.example/dl", kind="web", fetch_status="ok",
        page_title="Free Hack Download", is_distribution_site=True,
        indicators=["배포 관련 표현 발견"], excerpt="download now hack v3",
    )]


def test_run_returns_llm_response_verdict() -> None:
    stub = _StubLLM(_synth_payload())
    synth = Synthesizer(stub, model="gpt-4o")
    verdict = synth.run("ㅎr킹 팝니다", _triage(), _image_evidence(), _link_evidence())

    assert isinstance(verdict, LLMResponse)
    assert verdict.type == "핵_치트"
    assert verdict.confidence == 0.97
    assert "다운로드 페이지" in verdict.reason_ko
    assert verdict.input_tokens == 1500
    assert verdict.cost_usd == 0.008


def test_run_uses_classification_schema_as_ssot() -> None:
    # 5필드 계약 SSOT — 신규 스키마 정의 금지 (Story 3-8 Task 4).
    stub = _StubLLM(_synth_payload())
    synth = Synthesizer(stub, model="gpt-4o")
    synth.run("본문", _triage(), None, [])

    assert stub.last_call["schema"] is CLASSIFICATION_SCHEMA
    assert stub.last_call["schema_name"] == "tracker_synthesis"
    assert stub.last_call["image_blocks"] is None  # S3는 텍스트 증거만 소비


def test_user_text_serializes_all_evidence() -> None:
    stub = _StubLLM(_synth_payload())
    synth = Synthesizer(stub, model="gpt-4o")
    synth.run("게시글 원문", _triage(), _image_evidence(), _link_evidence())

    user_text = stub.last_call["user_text"]
    assert "게시글 원문" in user_text
    assert "핵_치트" in user_text and "0.78" in user_text          # 트리아지
    assert "핵 실행 화면 확인." in user_text                        # 이미지 증거
    assert "https://evil.example/dl" in user_text                  # 링크 증거
    assert "download now hack v3" in user_text                     # 링크 발췌(excerpt)
    assert "리니지M(TW)" in user_text                              # game_context


def test_user_text_omits_missing_evidence_sections() -> None:
    stub = _StubLLM(_synth_payload())
    synth = Synthesizer(stub, model="gpt-4o")
    synth.run("본문", _triage(), None, [])

    user_text = stub.last_call["user_text"]
    assert "[이미지 증거" not in user_text
    assert "[링크 증거" not in user_text


def test_system_prompt_has_evidence_priority_and_tier_rules() -> None:
    # AC #4: 구체적 증거 우선 + 다중 type 시 최상위 Tier 채택 + reason_ko 증거 1문장.
    stub = _StubLLM(_synth_payload())
    synth = Synthesizer(stub, model="gpt-4o")
    synth.run("본문", _triage(), None, [])

    sp = stub.last_call["system_prompt"]
    assert "증거 통합 단계 지침" in sp
    assert "구체적" in sp                       # 구체적 증거 우선
    assert "최상위 Tier" in sp
    assert "T1" in sp and "핵_치트" in sp        # type→Tier 매핑 명시
    assert "1문장" in sp                        # reason_ko 채택 증거 1문장


def test_translated_text_falls_back_to_triage() -> None:
    # S3가 null을 반환해도 트리아지 번역이 있으면 유지 (Task 4).
    stub = _StubLLM(_synth_payload(translated_text_ko=None))
    synth = Synthesizer(stub, model="gpt-4o")
    verdict = synth.run("본문", _triage(translated_text_ko="번역문"), None, [])
    assert verdict.translated_text_ko == "번역문"


def test_image_observed_overridden_by_contributes() -> None:
    # AC #3: image_observed는 LLM 자가보고가 아니라 S2a contributes 값 (결정론적).
    stub = _StubLLM(_synth_payload(image_observed=True))
    synth = Synthesizer(stub, model="gpt-4o")
    no_image = synth.run("본문", _triage(), None, [])
    assert no_image.image_observed is False  # 이미지 증거 없음 → False 강제

    not_contributing = ImageEvidence(
        illegal_indicators=[], extracted_text="", summary_ko="무관한 고양이 사진.",
        contributes=False,
    )
    verdict = synth.run("본문", _triage(), not_contributing, [])
    assert verdict.image_observed is False  # contributes=False → False 강제


def test_model_override_for_budget_fallback() -> None:
    stub = _StubLLM(_synth_payload())
    synth = Synthesizer(stub, model="gpt-4o")
    synth.run("본문", _triage(), None, [], model="gpt-4o-mini")
    assert stub.last_call["model"] == "gpt-4o-mini"


def test_model_from_env_when_not_passed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SYNTHESIZER_MODEL", "gpt-4o-custom")
    synth = Synthesizer(_StubLLM(_synth_payload()))
    assert synth.model == "gpt-4o-custom"


def test_invalid_type_rejected() -> None:
    stub = _StubLLM(_synth_payload(type="존재하지않는유형"))
    synth = Synthesizer(stub, model="gpt-4o")
    with pytest.raises(ValueError, match="invalid synthesis type"):
        synth.run("본문", _triage(), None, [])


def test_confidence_out_of_range_rejected() -> None:
    stub = _StubLLM(_synth_payload(confidence=1.7))
    synth = Synthesizer(stub, model="gpt-4o")
    with pytest.raises(ValueError, match="confidence out of range"):
        synth.run("본문", _triage(), None, [])
