"""S2a ImageAnalyst 단위 테스트 (Story 3-8) — 이미지 판독 + PII 토글 + resolve 실패 처리."""

from __future__ import annotations

import pytest

from detection.src.agents.contracts import ImageEvidence
from detection.src.agents.image_analyst import IMAGE_SCHEMA, ImageAnalyst


class _StubLLM:
    """LLMClient.run_structured(image_blocks 지원) 시그니처만 흉내내는 스텁."""

    def __init__(self, parsed: dict, tokens=(900, 60), cost=0.0058) -> None:
        self._parsed = parsed
        self._tokens = tokens
        self._cost = cost
        self.last_call: dict | None = None
        self.call_count = 0

    def run_structured(self, *, system_prompt, user_text, schema, schema_name, model, image_blocks=None):
        self.call_count += 1
        self.last_call = {
            "system_prompt": system_prompt,
            "user_text": user_text,
            "schema": schema,
            "schema_name": schema_name,
            "model": model,
            "image_blocks": image_blocks,
        }
        return self._parsed, self._tokens[0], self._tokens[1], self._cost


def _image_payload(**overrides) -> dict:
    base = {
        "illegal_indicators": ["핵 UI 오버레이", "텔레그램 ID"],
        "extracted_text": "ESP aimbot v3.2 / @hackseller",
        "summary_ko": "핵 프로그램 실행 화면과 판매자 연락처가 확인됨.",
        "contributes": True,
    }
    base.update(overrides)
    return base


@pytest.fixture(autouse=True)
def _send_images_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_SEND_IMAGES", "true")


def test_run_returns_image_evidence_with_cost() -> None:
    stub = _StubLLM(_image_payload())
    analyst = ImageAnalyst(stub, model="gpt-4o")
    evidence = analyst.run("핵 팝니다", ["https://example.com/shot.jpg"])

    assert isinstance(evidence, ImageEvidence)
    assert evidence.contributes is True
    assert "핵 UI 오버레이" in evidence.illegal_indicators
    assert evidence.extracted_text == "ESP aimbot v3.2 / @hackseller"
    assert evidence.summary_ko
    assert evidence.cost_usd == 0.0058
    assert evidence.input_tokens == 900


def test_run_uses_image_schema_and_blocks() -> None:
    stub = _StubLLM(_image_payload())
    analyst = ImageAnalyst(stub, model="gpt-4o")
    analyst.run("본문", ["https://example.com/a.jpg", "https://example.com/b.png"])

    assert stub.last_call["schema"] is IMAGE_SCHEMA
    assert stub.last_call["schema_name"] == "tracker_image_analysis"
    assert stub.last_call["model"] == "gpt-4o"
    blocks = stub.last_call["image_blocks"]
    assert len(blocks) == 2
    assert all(b["type"] == "image_url" for b in blocks)


def test_disabled_when_send_images_false(monkeypatch: pytest.MonkeyPatch) -> None:
    # PII 가드: LLM_SEND_IMAGES=false면 S2a 비활성 (single 모드와 동일 정책).
    monkeypatch.setenv("LLM_SEND_IMAGES", "false")
    stub = _StubLLM(_image_payload())
    analyst = ImageAnalyst(stub, model="gpt-4o")

    assert analyst.enabled is False
    assert analyst.run("본문", ["https://example.com/a.jpg"]) is None
    assert stub.call_count == 0  # LLM 호출 0


def test_no_resolvable_images_returns_none() -> None:
    # s3://는 presigned 변환 전이라 resolve 불가 — LLM 호출 없이 None.
    stub = _StubLLM(_image_payload())
    analyst = ImageAnalyst(stub, model="gpt-4o")
    assert analyst.run("본문", ["s3://bucket/key.jpg"]) is None
    assert stub.call_count == 0


def test_empty_images_returns_none() -> None:
    stub = _StubLLM(_image_payload())
    analyst = ImageAnalyst(stub, model="gpt-4o")
    assert analyst.run("본문", []) is None
    assert stub.call_count == 0


def test_model_from_env_when_not_passed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IMAGE_ANALYST_MODEL", "gpt-4o-custom")
    analyst = ImageAnalyst(_StubLLM(_image_payload()))
    assert analyst.model == "gpt-4o-custom"


def test_contributes_false_passthrough() -> None:
    stub = _StubLLM(_image_payload(contributes=False, illegal_indicators=[]))
    analyst = ImageAnalyst(stub, model="gpt-4o")
    evidence = analyst.run("본문", ["https://example.com/cat.jpg"])
    assert evidence is not None
    assert evidence.contributes is False
    assert evidence.illegal_indicators == []
