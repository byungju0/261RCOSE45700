"""LLMClient — OpenAI 호출 패턴 + 멀티모달 분기 + 토글 검증 (Story 3-3)."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from detection.src.pipeline import llm_client as llm_client_module
from detection.src.pipeline.llm_client import (
    CLASSIFICATION_SCHEMA,
    LLMClient,
    SYSTEM_PROMPT,
    build_system_prompt,
)
from shared.interfaces.llm import RateLimitError


def _make_openai_response(parsed: dict, prompt_tokens: int = 100, completion_tokens: int = 40) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(parsed)))],
        usage=SimpleNamespace(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens),
    )


def _classification_payload(**overrides) -> dict:
    base = {
        "type": "기타",
        "confidence": 0.92,
        "reason_ko": "정상 게시글입니다.",
        "translated_text_ko": None,
        "image_observed": False,
    }
    base.update(overrides)
    return base


@pytest.fixture(autouse=True)
def _env_setup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-real")
    monkeypatch.setenv("LLM_MODEL", "gpt-4o")
    monkeypatch.setenv("LLM_TIMEOUT_SEC", "30")
    monkeypatch.setenv("LLM_SEND_IMAGES", "false")
    monkeypatch.setenv("LLM_SPLIT_TEXT_IMAGE", "false")


def test_classify_text_only_uses_text_content_block() -> None:
    mock_openai = MagicMock()
    mock_openai.chat.completions.create.return_value = _make_openai_response(
        _classification_payload()
    )

    client = LLMClient(client=mock_openai)
    response = client.classify("정상 게시글")

    assert response.type == "기타"
    assert response.confidence == 0.92
    call_kwargs = mock_openai.chat.completions.create.call_args.kwargs
    assert call_kwargs["model"] == "gpt-4o"
    assert call_kwargs["response_format"]["type"] == "json_schema"
    assert call_kwargs["response_format"]["json_schema"]["strict"] is True
    assert call_kwargs["response_format"]["json_schema"]["schema"] == CLASSIFICATION_SCHEMA
    messages = call_kwargs["messages"]
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    # user.content는 list (multi-content block 패턴), 텍스트 only면 길이 1.
    assert isinstance(messages[1]["content"], list)
    assert len(messages[1]["content"]) == 1
    assert messages[1]["content"][0]["type"] == "text"
    # 비용 산출이 input/output 토큰 기반으로 채워졌는지.
    assert response.input_tokens == 100
    assert response.output_tokens == 40
    assert response.cost_usd > 0


def test_system_prompt_defines_confidence_rubric() -> None:
    assert "confidence는 불법 위험도가 아니라 선택한 type 분류의 신뢰도" in SYSTEM_PROMPT
    assert "0.95-1.00" in SYSTEM_PROMPT
    assert "0.50-0.69" in SYSTEM_PROMPT
    assert "0.90 또는 0.95를 기본값처럼 반복하지 말고" in SYSTEM_PROMPT


def test_build_system_prompt_base_plus_type_guidance_for_unknown_source() -> None:
    # source_id 없음/미매핑 → 베이스 + 유형 가이드만, 게임 오버레이는 없음 (동작 중립 fallback).
    prompt = build_system_prompt(None)
    assert "NC AI 게임 보안 분석가" in prompt           # 베이스 보존
    assert "유형 판별 가이드:" in prompt                 # Stage 2-A 항상 적용
    assert "게임 맥락:" not in prompt                    # 오버레이 없음


def test_build_system_prompt_injects_game_overlay() -> None:
    # 매핑된 source_id → 게임 오버레이 주입. 안정부(베이스+가이드)가 오버레이보다 앞 (캐싱 prefix).
    prompt = build_system_prompt("bahamut_lineage")
    assert "유형 판별 가이드:" in prompt
    assert "게임 맥락:" in prompt
    assert prompt.index("유형 판별 가이드:") < prompt.index("게임 맥락:")


def test_build_system_prompt_unknown_source_falls_back_to_base() -> None:
    assert build_system_prompt("does_not_exist") == build_system_prompt(None)


def test_classify_threads_source_id_into_system_prompt() -> None:
    mock_openai = MagicMock()
    mock_openai.chat.completions.create.return_value = _make_openai_response(
        _classification_payload()
    )
    client = LLMClient(client=mock_openai)
    client.classify("게시글", source_id="bahamut_lineage")

    system_msg = mock_openai.chat.completions.create.call_args.kwargs["messages"][0]["content"]
    assert "게임 맥락:" in system_msg  # 게임 오버레이가 system prompt에 반영됨


def test_classify_with_images_sends_multimodal_content(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_SEND_IMAGES", "true")
    mock_openai = MagicMock()
    mock_openai.chat.completions.create.return_value = _make_openai_response(
        _classification_payload(type="핵_치트", confidence=0.95, image_observed=True)
    )

    client = LLMClient(client=mock_openai)
    response = client.classify("핵 팝니다", images=["https://example.com/screenshot.jpg"])

    assert response.type == "핵_치트"
    assert response.image_observed is True
    content = mock_openai.chat.completions.create.call_args.kwargs["messages"][1]["content"]
    assert any(b.get("type") == "image_url" for b in content)
    image_block = next(b for b in content if b.get("type") == "image_url")
    assert image_block["image_url"]["url"] == "https://example.com/screenshot.jpg"


def test_send_images_false_falls_back_to_text_only() -> None:
    # 기본 LLM_SEND_IMAGES=false (autouse fixture)
    mock_openai = MagicMock()
    mock_openai.chat.completions.create.return_value = _make_openai_response(
        _classification_payload()
    )

    client = LLMClient(client=mock_openai)
    client.classify("텍스트", images=["https://example.com/x.jpg"])

    content = mock_openai.chat.completions.create.call_args.kwargs["messages"][1]["content"]
    # 이미지 토글 off → image_url 블록이 추가되지 않아야 함.
    assert not any(b.get("type") == "image_url" for b in content)


def test_rate_limit_retries_after_sleep_then_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx
    from openai import RateLimitError as OpenAIRateLimitError

    real_response = httpx.Response(
        status_code=429,
        headers={"Retry-After": "2"},
        request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"),
    )
    mock_openai = MagicMock()
    mock_openai.chat.completions.create.side_effect = OpenAIRateLimitError(
        message="429", response=real_response, body=None,
    )

    client = LLMClient(client=mock_openai)
    sleep_calls: list[float] = []
    monkeypatch.setattr(llm_client_module.time, "sleep", lambda s: sleep_calls.append(s))

    with pytest.raises(RateLimitError):
        client.classify("text")

    # 2회 시도(첫 호출 + 1회 자동 재시도) 후 RateLimitError 변환.
    assert mock_openai.chat.completions.create.call_count == 2
    assert sleep_calls == [2]
