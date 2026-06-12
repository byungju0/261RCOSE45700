"""Daily Cost Cap — OpenAI 일일 비용 추적 + cap 도달 시 Hold (Story 3-3, 2026-05-27 PIVOT).

Redis(DB2, `llm:cost:YYYY-MM-DD` 키, TTL 48h)에 누적 비용을 micro-USD 정수로 INCRBY 한다.
float 누적 오차 회피 + 다중 worker 안전성 보장.

`LLM_DAILY_COST_CAP_USD`(기본 $5) 도달 시 sleep loop로 hold. 자정 KST 넘어가면 키 만료 → 자동 재개.
`LLM_DAILY_COST_CAP_USD=0` 또는 unset이면 cap 비활성.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone

import redis

from shared.structured_logger import get_logger

_SERVICE_NAME = os.environ.get("SERVICE_NAME", "detection")
_logger = get_logger(__name__)

# 모델별 토큰 단가 (USD per 1M tokens, input/output). 2026-06 기준 — 멀티 프로바이더.
# 값은 정적 시드일 뿐, `LLM_PRICING_OVERRIDES_JSON`(파일 경로 또는 인라인 JSON)으로 코드 수정
# 없이 추가·갱신할 수 있다. 프로바이더의 캐시 할인·컨텍스트 길이 차등·이미지 타일 단가는
# 반영하지 않은 표준(cache-miss/base-tier) 단가의 근사다 — cap·예산 추정용.
_BASE_PRICING: dict[str, dict[str, float]] = {
    # --- OpenAI (platform.openai.com/api/pricing) ---
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-2024-08-06": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.150, "output": 0.600},
    "gpt-4.1": {"input": 2.00, "output": 8.00},
    "gpt-4.1-mini": {"input": 0.400, "output": 1.600},
    "gpt-4.1-nano": {"input": 0.100, "output": 0.400},
    "o3": {"input": 2.00, "output": 8.00},
    "o4-mini": {"input": 0.550, "output": 2.200},
    # --- Anthropic Claude (platform.claude.com/docs pricing) ---
    "claude-fable-5": {"input": 10.00, "output": 50.00},
    "claude-opus-4-8": {"input": 5.00, "output": 25.00},
    "claude-opus-4-7": {"input": 5.00, "output": 25.00},
    "claude-opus-4-6": {"input": 5.00, "output": 25.00},
    "claude-sonnet-4-6": {"input": 3.00, "output": 15.00},
    "claude-haiku-4-5": {"input": 1.00, "output": 5.00},
    # --- DeepSeek (api-docs.deepseek.com/quick_start/pricing, cache-miss 입력) ---
    # deepseek-chat/reasoner는 v4-flash로 라우팅(2026-07-24 deprecation 예정).
    "deepseek-chat": {"input": 0.14, "output": 0.28},
    "deepseek-reasoner": {"input": 0.14, "output": 0.28},
    "deepseek-v4-flash": {"input": 0.14, "output": 0.28},
    "deepseek-v4-pro": {"input": 0.435, "output": 0.87},
    # --- Google Gemini (cloud.google.com/vertex-ai pricing, ≤200k base tier) ---
    "gemini-2.5-pro": {"input": 1.25, "output": 10.00},
    "gemini-2.5-flash": {"input": 0.30, "output": 2.50},
    "gemini-2.5-flash-lite": {"input": 0.10, "output": 0.40},
}


def _load_pricing() -> dict[str, dict[str, float]]:
    """베이스 단가표 + `LLM_PRICING_OVERRIDES_JSON` 병합.

    오버라이드는 (1) 파일 경로 또는 (2) 인라인 JSON 문자열 둘 다 허용.
    `{"model": {"input": x, "output": y}}` 형식. 동일 모델 키는 오버라이드가 우선 —
    프로바이더가 가격을 바꾸거나 신모델을 추가할 때 코드 수정 없이 반영한다.
    파싱 실패는 경고 후 베이스로 fallback (cap이 조용히 0이 되지 않도록).
    """
    pricing = {k: dict(v) for k, v in _BASE_PRICING.items()}
    raw = os.environ.get("LLM_PRICING_OVERRIDES_JSON", "").strip()
    if not raw:
        return pricing
    try:
        if raw.startswith("{"):
            overrides = json.loads(raw)
        else:
            with open(raw, encoding="utf-8") as f:
                overrides = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        _logger.warning(
            "LLM_PRICING_OVERRIDES_JSON 로드 실패 — 베이스 단가표 사용: %s", exc,
            extra={"correlation_id": "", "service": _SERVICE_NAME},
        )
        return pricing
    for model, rate in overrides.items():
        if isinstance(rate, dict) and "input" in rate and "output" in rate:
            pricing[model] = {"input": float(rate["input"]), "output": float(rate["output"])}
        else:
            _logger.warning(
                "LLM_PRICING_OVERRIDES_JSON 항목 무시 — input/output 누락: model=%s", model,
                extra={"correlation_id": "", "service": _SERVICE_NAME},
            )
    return pricing


PRICING: dict[str, dict[str, float]] = _load_pricing()

# 단가 미등록 모델에 적용할 fallback 모델 (조용한 추정 대신 경고와 함께).
_FALLBACK_MODEL = os.environ.get("LLM_PRICING_FALLBACK_MODEL", "gpt-4o")
# 미등록 모델 경고를 모델당 1회만 — 로그 폭주 방지.
_warned_unknown_models: set[str] = set()

_KEY_TTL_SEC = 48 * 3600  # 48시간 — 자정 넘어가도 어제 키 잔존 시 정상 만료
_HOLD_SLEEP_SEC = int(os.environ.get("COST_CAP_HOLD_SLEEP_SEC", "60"))
_HOLD_MAX_RETRIES = int(os.environ.get("COST_CAP_HOLD_MAX_RETRIES", "5"))


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    """모델별 토큰 단가로 비용 추정 (USD).

    등록된 모델이면 정확한 단가, 미등록이면 `_FALLBACK_MODEL`(기본 gpt-4o) 단가로 추정하되
    **모델당 1회 경고를 남긴다** — 조용한 잘못된 추정(특히 타 프로바이더 모델)을 가시화.
    """
    rate = PRICING.get(model)
    if rate is None:
        if model not in _warned_unknown_models:
            _warned_unknown_models.add(model)
            _logger.warning(
                "단가 미등록 모델 — %s 단가로 추정(부정확 가능). PRICING 또는 "
                "LLM_PRICING_OVERRIDES_JSON에 model=%s 추가 권장.",
                _FALLBACK_MODEL, model,
                extra={"correlation_id": "", "service": _SERVICE_NAME, "unknown_model": model},
            )
        rate = PRICING.get(_FALLBACK_MODEL) or {"input": 2.50, "output": 10.00}
    return (input_tokens * rate["input"] + output_tokens * rate["output"]) / 1_000_000


def _today_key() -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"llm:cost:{today}"


class CostCap:
    def __init__(self, redis_client: redis.Redis) -> None:
        self._redis = redis_client
        self._cap_usd = float(os.environ.get("LLM_DAILY_COST_CAP_USD", "5"))

    @property
    def enabled(self) -> bool:
        return self._cap_usd > 0

    def cumulative_usd(self) -> float:
        if not self.enabled:
            return 0.0
        raw = self._redis.get(_today_key())
        if raw is None:
            return 0.0
        return int(raw) / 1_000_000.0

    def record(self, input_tokens: int, output_tokens: int, model: str) -> float:
        """OpenAI 호출 직후 호출. 산출 비용을 누적 + 반환."""
        cost_usd = estimate_cost_usd(model, input_tokens, output_tokens)
        if not self.enabled:
            return cost_usd
        # 비용이 0보다 크면 최소 1 micro-USD로 올림 — 극소 비용의 silent 누락 방지.
        micro = max(1, int(round(cost_usd * 1_000_000))) if cost_usd > 0 else 0
        if micro <= 0:
            return cost_usd
        key = _today_key()
        new_total = self._redis.incrby(key, micro)
        self._redis.expire(key, _KEY_TTL_SEC)
        _logger.debug(
            "cost recorded — model=%s cost=$%.5f cumulative=$%.4f",
            model, cost_usd, new_total / 1_000_000.0,
            extra={"correlation_id": "", "service": _SERVICE_NAME},
        )
        return cost_usd

    def check_and_hold(self) -> None:
        """OpenAI 호출 직전 호출. cap 도달 시 sleep loop로 hold."""
        if not self.enabled:
            return
        for _ in range(_HOLD_MAX_RETRIES + 1):
            cumulative = self.cumulative_usd()
            if cumulative < self._cap_usd:
                return
            _logger.warning(
                "일일 비용 cap 도달 — hold cumulative=$%.4f cap=$%.2f sleep=%ds",
                cumulative, self._cap_usd, _HOLD_SLEEP_SEC,
                extra={
                    "correlation_id": "",
                    "service": _SERVICE_NAME,
                    "cumulative_usd": cumulative,
                    "cap_usd": self._cap_usd,
                },
            )
            time.sleep(_HOLD_SLEEP_SEC)
        # max retries 초과 후에도 cap 미해소 — 호출 진행 허용(operations 책임).
        _logger.error(
            "일일 비용 cap hold 한계 초과 — 호출 진행 (운영자 조치 필요)",
            extra={"correlation_id": "", "service": _SERVICE_NAME},
        )
