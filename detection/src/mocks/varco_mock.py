from __future__ import annotations

import json
import time
from pathlib import Path

from shared.interfaces.varco import ClassificationResult

# detection/src/mocks/ → parents[3] == 프로젝트 루트
_FIXTURES = Path(__file__).parents[3] / "tests" / "fixtures" / "varco"
_VALID_MODES = {"clean", "illegal", "rate_limited", "timeout"}


class RateLimitError(Exception):
    def __init__(self, retry_after: int = 30):
        self.retry_after = retry_after
        super().__init__(f"Rate limit exceeded. Retry after {retry_after}s")


class VarcoMock:
    """VarcoInterface Protocol 구현체 — 통합 테스트 전용"""

    def __init__(self, mode: str = "clean", latency_ms: int = 0) -> None:
        if mode not in _VALID_MODES:
            raise ValueError(f"unsupported VARCO mock mode: {mode}")
        self._mode = mode
        self._latency_ms = latency_ms
        self._data: dict = self._load(mode)

    def _load(self, mode: str) -> dict:
        path = _FIXTURES / f"mock_response_{mode}.json"
        with path.open(encoding="utf-8") as f:
            return json.load(f)

    def simulate_latency(self, ms: int) -> None:
        self._latency_ms = ms

    def _sleep(self) -> None:
        if self._latency_ms > 0:
            time.sleep(self._latency_ms / 1000)

    def translate(self, text: str) -> str:
        self._sleep()
        if self._mode == "rate_limited":
            raise RateLimitError(self._data.get("retry_after_seconds", 30))
        if self._mode == "timeout":
            raise TimeoutError("VARCO API timeout")
        return self._data.get("translated_text", text)

    def classify(self, text: str) -> ClassificationResult:
        self._sleep()
        if self._mode == "rate_limited":
            raise RateLimitError(self._data.get("retry_after_seconds", 30))
        if self._mode == "timeout":
            raise TimeoutError("VARCO API timeout")
        c = self._data["classification"]
        return ClassificationResult(
            is_illegal=c["is_illegal"],
            type=c["type"],
            confidence=c["confidence"],
            reason=c["reason"],
        )
