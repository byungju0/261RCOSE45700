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
    build_image_blocks,
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


def test_build_system_prompt_base_plus_type_and_domain_guide() -> None:
    # 2026-06-11 재정의: 베이스 + 유형 가이드 + 공용 도메인 가이드 (게임별 오버레이 제거).
    prompt = build_system_prompt(None)
    assert "NC AI 게임 보안 분석가" in prompt           # 베이스 보존
    assert "유형 판별 가이드:" in prompt                 # Stage 2-A 항상 적용
    assert "공용 도메인 가이드" in prompt                # 공용 도메인 가이드 항상 주입
    # 안정부 순서(캐싱 prefix): 베이스 < 유형 가이드 < 도메인 가이드.
    assert prompt.index("유형 판별 가이드:") < prompt.index("공용 도메인 가이드")


def test_build_system_prompt_site_independent() -> None:
    # 라우팅 제거(FR12-C): source_id가 달라도 동일 프롬프트.
    assert build_system_prompt("bahamut_lineage") == build_system_prompt("does_not_exist")
    assert build_system_prompt("does_not_exist") == build_system_prompt(None)


def test_classify_injects_domain_guide_into_system_prompt() -> None:
    mock_openai = MagicMock()
    mock_openai.chat.completions.create.return_value = _make_openai_response(
        _classification_payload()
    )
    client = LLMClient(client=mock_openai)
    client.classify("게시글", source_id="bahamut_lineage")

    system_msg = mock_openai.chat.completions.create.call_args.kwargs["messages"][0]["content"]
    assert "공용 도메인 가이드" in system_msg  # 공용 도메인 가이드가 system prompt에 반영됨


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


def test_build_image_blocks_resolves_urls_and_skips_s3() -> None:
    # Story 3-8: classify()와 S2a ImageAnalyst가 공유하는 이미지 블록 빌더.
    blocks = build_image_blocks([
        "https://example.com/a.jpg",
        "s3://bucket/key.png",   # presigned 변환 전 — 스킵
        "data:image/png;base64,AAAA",
    ])
    assert len(blocks) == 2
    assert blocks[0] == {"type": "image_url", "image_url": {"url": "https://example.com/a.jpg"}}
    assert blocks[1]["image_url"]["url"].startswith("data:image/png")


def test_run_structured_appends_image_blocks() -> None:
    # Story 3-8: S2a가 멀티모달 structured 호출에 image_blocks를 전달.
    mock_openai = MagicMock()
    mock_openai.chat.completions.create.return_value = _make_openai_response(
        {"contributes": True}
    )
    client = LLMClient(client=mock_openai)
    blocks = [{"type": "image_url", "image_url": {"url": "https://example.com/a.jpg"}}]
    parsed, in_tok, out_tok, cost = client.run_structured(
        system_prompt="sp", user_text="본문", schema={"type": "object"},
        schema_name="tracker_image_analysis", model="gpt-4o", image_blocks=blocks,
    )

    assert parsed == {"contributes": True}
    content = mock_openai.chat.completions.create.call_args.kwargs["messages"][1]["content"]
    assert isinstance(content, list)
    assert content[0]["type"] == "text"
    assert content[1] == blocks[0]
    assert cost > 0


def test_run_structured_without_blocks_keeps_str_content() -> None:
    # 기존 호출자(S1 트리아지) 하위호환 — image_blocks 미전달 시 3-7 wire format(str content) 보존.
    mock_openai = MagicMock()
    mock_openai.chat.completions.create.return_value = _make_openai_response({"ok": 1})
    client = LLMClient(client=mock_openai)
    client.run_structured(
        system_prompt="sp", user_text="본문", schema={"type": "object"},
        schema_name="tracker_triage", model="gpt-4o-mini",
    )
    content = mock_openai.chat.completions.create.call_args.kwargs["messages"][1]["content"]
    assert isinstance(content, str)
    assert content == "게시글:\n본문"


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
