"""CostCap — micro-USD INCRBY + check_and_hold (Story 3-3)."""

from __future__ import annotations

from unittest.mock import patch

import fakeredis
import pytest

from detection.src.rate_limit import cost_cap as cost_cap_module
from detection.src.rate_limit.cost_cap import CostCap, estimate_cost_usd


@pytest.fixture
def fake_redis() -> fakeredis.FakeRedis:
    return fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture(autouse=True)
def _env_setup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_DAILY_COST_CAP_USD", "5")


def test_record_accumulates_cost_under_cap(fake_redis: fakeredis.FakeRedis) -> None:
    cap = CostCap(fake_redis)
    # gpt-4o: input $2.5/1M, output $10/1M → 1000 in + 500 out = $0.0025 + $0.005 = $0.0075
    cost = cap.record(input_tokens=1000, output_tokens=500, model="gpt-4o")
    assert cost == pytest.approx(0.0075, rel=1e-3)
    # 누적 비용은 cap 미만 — hold 없음.
    cap.check_and_hold()
    assert cap.cumulative_usd() == pytest.approx(0.0075, rel=1e-3)


def test_check_and_hold_sleeps_when_cap_reached(
    fake_redis: fakeredis.FakeRedis, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Cap을 거의 가득 채워서 직후 check가 hold loop에 진입하도록.
    cap = CostCap(fake_redis)
    # 1회 호출로 $5 초과 — gpt-4o 기준 output 500k 토큰 ≈ $5.
    cap.record(input_tokens=0, output_tokens=500_000, model="gpt-4o")
    assert cap.cumulative_usd() >= 5.0

    sleep_calls: list[float] = []
    monkeypatch.setattr(cost_cap_module.time, "sleep", lambda s: sleep_calls.append(s))

    cap.check_and_hold()
    # hold loop가 sleep을 _HOLD_MAX_RETRIES+1 회 호출했어야 함 (cap 해소 안 되므로).
    assert len(sleep_calls) >= 1


def test_cap_disabled_when_zero(fake_redis: fakeredis.FakeRedis, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_DAILY_COST_CAP_USD", "0")
    cap = CostCap(fake_redis)
    assert cap.enabled is False
    # record는 비용 산출만 반환, INCRBY 없음.
    cost = cap.record(input_tokens=100, output_tokens=50, model="gpt-4o")
    assert cost > 0
    assert cap.cumulative_usd() == 0.0
    # check_and_hold는 즉시 return — sleep 없음.
    with patch("detection.src.rate_limit.cost_cap.time.sleep") as mock_sleep:
        cap.check_and_hold()
    mock_sleep.assert_not_called()


def test_estimate_cost_fallback_to_gpt4o() -> None:
    cost_known = estimate_cost_usd("gpt-4o", 1000, 500)
    cost_unknown = estimate_cost_usd("아직-출시-안된-모델", 1000, 500)
    assert cost_known == pytest.approx(cost_unknown, rel=1e-9)


@pytest.mark.parametrize(
    "model, in_rate, out_rate",
    [
        ("gpt-4o-mini", 0.150, 0.600),
        ("o4-mini", 0.550, 2.200),
        ("claude-opus-4-8", 5.00, 25.00),
        ("claude-sonnet-4-6", 3.00, 15.00),
        ("claude-haiku-4-5", 1.00, 5.00),
        ("claude-fable-5", 10.00, 50.00),
        ("deepseek-chat", 0.14, 0.28),
        ("deepseek-v4-pro", 0.435, 0.87),
        ("gemini-2.5-pro", 1.25, 10.00),
        ("gemini-2.5-flash", 0.30, 2.50),
    ],
)
def test_multi_provider_pricing(model: str, in_rate: float, out_rate: float) -> None:
    # 1M in + 1M out → input_rate + output_rate (USD).
    cost = estimate_cost_usd(model, 1_000_000, 1_000_000)
    assert cost == pytest.approx(in_rate + out_rate, rel=1e-9)


def test_unknown_model_warns_once_then_estimates(monkeypatch: pytest.MonkeyPatch) -> None:
    # 미등록 모델 → fallback 추정 + 모델당 1회 경고.
    cost_cap_module._warned_unknown_models.discard("totally-unknown-llm")
    warnings: list[str] = []
    monkeypatch.setattr(
        cost_cap_module._logger, "warning",
        lambda msg, *a, **k: warnings.append(msg % a if a else msg),
    )
    c1 = estimate_cost_usd("totally-unknown-llm", 1000, 500)
    c2 = estimate_cost_usd("totally-unknown-llm", 1000, 500)
    assert c1 == pytest.approx(c2)
    assert c1 == pytest.approx(estimate_cost_usd("gpt-4o", 1000, 500))  # fallback 단가
    assert len(warnings) == 1  # 모델당 1회만 경고


def test_check_and_hold_max_retries_exhausted_allows_call(
    fake_redis: fakeredis.FakeRedis, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # cap 초과 상태를 유지하면 hold 루프가 _HOLD_MAX_RETRIES+1 회 sleep 후 return 해야 한다
    # (무한 차단이 아닌 운영자 책임으로 호출 진행).
    cap = CostCap(fake_redis)
    cap.record(input_tokens=0, output_tokens=500_000, model="gpt-4o")

    sleep_calls: list[float] = []
    monkeypatch.setattr(cost_cap_module.time, "sleep", lambda s: sleep_calls.append(s))

    cap.check_and_hold()  # 예외 없이 반환해야 함

    assert len(sleep_calls) == cost_cap_module._HOLD_MAX_RETRIES + 1


def test_pricing_override_file_path_oserror_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    # 파일 경로 오버라이드인데 파일이 없으면 OSError → 경고 후 베이스 단가표로 fallback.
    monkeypatch.setenv("LLM_PRICING_OVERRIDES_JSON", "/nonexistent/path/pricing.json")
    import importlib
    reloaded = importlib.reload(cost_cap_module)
    try:
        assert reloaded.PRICING["gpt-4o"] == {"input": 2.50, "output": 10.00}
    finally:
        monkeypatch.delenv("LLM_PRICING_OVERRIDES_JSON", raising=False)
        importlib.reload(cost_cap_module)


def test_pricing_override_malformed_entry_skipped(monkeypatch: pytest.MonkeyPatch) -> None:
    # input/output 키가 없는 잘못된 항목은 건너뛰고, 올바른 항목은 정상 등록.
    monkeypatch.setenv(
        "LLM_PRICING_OVERRIDES_JSON",
        '{"bad-entry": {"cost": 1.0}, "valid-entry": {"input": 5.0, "output": 15.0}}',
    )
    import importlib
    reloaded = importlib.reload(cost_cap_module)
    try:
        assert "bad-entry" not in reloaded.PRICING
        assert reloaded.PRICING["valid-entry"] == {"input": 5.0, "output": 15.0}
    finally:
        monkeypatch.delenv("LLM_PRICING_OVERRIDES_JSON", raising=False)
        importlib.reload(cost_cap_module)


def test_pricing_override_via_env_json(monkeypatch: pytest.MonkeyPatch) -> None:
    # 인라인 JSON 오버라이드로 신모델 추가 + 기존 모델 단가 변경 (코드 수정 없이).
    monkeypatch.setenv(
        "LLM_PRICING_OVERRIDES_JSON",
        '{"my-future-model": {"input": 1.0, "output": 2.0}, "gpt-4o": {"input": 9.9, "output": 9.9}}',
    )
    import importlib
    reloaded = importlib.reload(cost_cap_module)
    try:
        assert reloaded.PRICING["my-future-model"] == {"input": 1.0, "output": 2.0}
        assert reloaded.PRICING["gpt-4o"] == {"input": 9.9, "output": 9.9}
        # 오버라이드 안 한 모델은 베이스 단가 유지.
        assert reloaded.PRICING["claude-opus-4-8"] == {"input": 5.00, "output": 25.00}
    finally:
        monkeypatch.delenv("LLM_PRICING_OVERRIDES_JSON", raising=False)
        importlib.reload(cost_cap_module)  # 전역 PRICING 원복
