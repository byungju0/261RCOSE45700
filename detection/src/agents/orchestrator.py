"""Agent Orchestrator — 결정론적 멀티 에이전트 파이프라인 (Story 3-7).

순수 Python FSM(LangChain/LLM 라우팅 없음): S0 정규화 → S1 트리아지 → FAST PATH 또는
ESCALATE(S2b 링크 추적) → degrade 종결. S2a 이미지 분석·S3 합성·게시글당 예산 가드는 Story
3-8 범위이므로, 본 스토리에서 escalate 경로의 최종 verdict는 **트리아지 결과로 degrade**한다
(S2b 증거는 agent_runs에만 기록 → 3-8 Synthesizer가 소비).

출력: `(LLMResponse verdict, list[AgentRunTrace])`. verdict는 single 모드와 동일한 5필드 스키마
(출력 계약 불변, AC #13). traces는 detections와 같은 트랜잭션으로 agent_runs에 저장된다.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from dataclasses import asdict

from detection.src.agents.contracts import AgentRunTrace
from detection.src.agents.link_tracer import LinkTracer
from detection.src.agents.normalizer import normalize
from detection.src.agents.triage_agent import TriageAgent
from shared.interfaces.llm import LLMResponse
from shared.structured_logger import get_logger

_SERVICE_NAME = os.environ.get("SERVICE_NAME", "detection")
_logger = get_logger(__name__)

_DEFAULT_FAST_PATH_CONFIDENCE = 0.80


def _now_ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


class AgentOrchestrator:
    """결정론적 오케스트레이터 — S0→S1→(fast path | escalate→degrade)."""

    def __init__(self, triage_agent: TriageAgent, link_tracer: LinkTracer) -> None:
        self._triage = triage_agent
        self._link_tracer = link_tracer
        self._fast_path_conf = float(
            os.environ.get("FAST_PATH_CONFIDENCE", str(_DEFAULT_FAST_PATH_CONFIDENCE))
        )

    @property
    def model_name(self) -> str:
        """비용 집계용 — 본 스토리의 LLM 비용은 트리아지(gpt-4o-mini) 단일."""
        return self._triage.model

    @property
    def model_version(self) -> str:
        """single 모드와 분리된 agentic 식별자 — (post_id, model_version) 유니크 공존(3-9 A/B)."""
        release = (os.environ.get("LLM_MODEL_RELEASE_DATE") or "").strip()
        if not release:
            release = datetime.now(timezone.utc).strftime("%Y-%m")
        return f"agentic:v1:{self._triage.model}:{release}"

    def run(self, raw_text: str, correlation_id: str = "") -> tuple[LLMResponse, list[AgentRunTrace]]:
        traces: list[AgentRunTrace] = []

        # S0 normalize ($0, LLM 없음).
        t0 = time.perf_counter()
        normalized = normalize(raw_text)
        traces.append(AgentRunTrace(
            stage="normalize", model=None, latency_ms=_now_ms(t0),
            output={"links": normalized.links, "removed_char_count": normalized.removed_char_count},
        ))

        # S1 triage (gpt-4o-mini, 전 게시글).
        t1 = time.perf_counter()
        triage = self._triage.run(normalized.text)
        triage_latency = _now_ms(t1)
        traces.append(AgentRunTrace(
            stage="triage", model=self._triage.model,
            input_tokens=triage.input_tokens, output_tokens=triage.output_tokens,
            cost_usd=triage.cost_usd, latency_ms=triage_latency,
            output={
                "type": triage.type, "confidence": triage.confidence,
                "game_context": triage.game_context,
                "needs_image": triage.needs_image, "needs_link_trace": triage.needs_link_trace,
            },
        ))

        # 분기: FAST PATH vs ESCALATE.
        is_fast_path = (
            triage.type == "기타"
            and triage.confidence >= self._fast_path_conf
            and not normalized.links  # 의심 링크 없음
        )

        if not is_fast_path and normalized.links:
            # ESCALATE — S2b 링크 추적 (1-hop, $0). 증거는 agent_runs에만 (3-7 degrade).
            t2 = time.perf_counter()
            evidence = self._link_tracer.trace(normalized.links, correlation_id=correlation_id)
            traces.append(AgentRunTrace(
                stage="link_trace", model=None, latency_ms=_now_ms(t2),
                output={"links": [asdict(e) for e in evidence]},
            ))

        path = "fast_path" if is_fast_path else "escalate_degrade"
        _logger.info(
            "orchestrator — path=%s type=%s conf=%.3f links=%d needs_image=%s",
            path, triage.type, triage.confidence, len(normalized.links), triage.needs_image,
            extra={
                "correlation_id": correlation_id, "service": _SERVICE_NAME,
                "path": path, "triage_type": triage.type,
            },
        )

        # degrade: 트리아지 결과를 최종 verdict로 (S3 Synthesizer는 Story 3-8).
        # image_observed=False — S2a 이미지 분석은 3-8 범위.
        verdict = LLMResponse(
            type=triage.type,
            confidence=triage.confidence,
            reason_ko=triage.reason_ko,
            translated_text_ko=triage.translated_text_ko,
            image_observed=False,
            input_tokens=triage.input_tokens,
            output_tokens=triage.output_tokens,
            cost_usd=triage.cost_usd,
        )
        return verdict, traces
