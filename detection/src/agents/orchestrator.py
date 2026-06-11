"""Agent Orchestrator — 결정론적 멀티 에이전트 파이프라인 (Story 3-7 / 3-8).

순수 Python FSM(LangChain/LLM 라우팅 없음):
  S0 정규화 → S1 트리아지 → FAST PATH | ESCALATE(S2a 이미지 ∥ S2b 링크 → S3 합성).

Story 3-8 완성분:
- S2a ImageAnalyst ∥ S2b LinkTracer를 `ThreadPoolExecutor`(max_workers=2)로 병렬 실행
- S3 Synthesizer가 모든 증거를 통합해 최종 verdict 산출 (escalate 전부 경유)
- 게시글당 예산 가드 `AGENT_POST_BUDGET_USD`(기본 0.02, ≤0 비활성): 각 LLM stage 착수
  **직전** 누적 실비용 ≥ 예산이면 잔여 stage 스킵 → 현재까지의 증거로 degrade 종결.
  `SYNTH_FALLBACK_MODEL` 설정 시 S3만 해당(저비용) 모델로 1회 시도 (opt-in)
- S3 실패 시 트리아지 verdict로 degrade + agent_runs 실패 trace (전수 저장 정책 유지)
- 종결 로그에 path/스테이지 비용·latency/누적 escalation율 (correlation_id 포함)

image_analyst/synthesizer가 None이면 3-7 동작(escalate→트리아지 degrade) 그대로 — 하위호환.
출력: `(LLMResponse verdict, list[AgentRunTrace])`. verdict 토큰/비용은 전 스테이지 합산.
"""

from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from dataclasses import asdict

from detection.src.agents.contracts import AgentRunTrace, ImageEvidence, LinkEvidence, TriageResult
from detection.src.agents.image_analyst import ImageAnalyst
from detection.src.agents.link_tracer import LinkTracer
from detection.src.agents.synthesizer import Synthesizer
from detection.src.agents.triage_agent import TriageAgent
from detection.src.agents.normalizer import normalize
from shared.interfaces.llm import LLMResponse
from shared.structured_logger import get_logger

_SERVICE_NAME = os.environ.get("SERVICE_NAME", "detection")
_logger = get_logger(__name__)

_DEFAULT_FAST_PATH_CONFIDENCE = 0.80
_DEFAULT_POST_BUDGET_USD = 0.02

# model_version 축약 표기 — 변경 제안서 확정 포맷(agentic:v1:mini+4o:YYYY-MM)용.
_MODEL_SHORT_NAMES = {"gpt-4o-mini": "mini", "gpt-4o": "4o"}

# escalation율 경고 임계 (AC #7 — 50% 초과 지속 시 fast-path 임계 하향 조정 신호).
_ESCALATION_WARN_RATE = 0.5
_ESCALATION_WARN_MIN_POSTS = 10


def _now_ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


def _short_model(model: str) -> str:
    return _MODEL_SHORT_NAMES.get(model, model)


class AgentOrchestrator:
    """결정론적 오케스트레이터 — S0→S1→(fast path | S2a∥S2b→S3 | degrade)."""

    def __init__(
        self,
        triage_agent: TriageAgent,
        link_tracer: LinkTracer,
        image_analyst: ImageAnalyst | None = None,
        synthesizer: Synthesizer | None = None,
    ) -> None:
        self._triage = triage_agent
        self._link_tracer = link_tracer
        self._image_analyst = image_analyst
        self._synthesizer = synthesizer
        self._fast_path_conf = float(
            os.environ.get("FAST_PATH_CONFIDENCE", str(_DEFAULT_FAST_PATH_CONFIDENCE))
        )
        self._post_budget = float(
            (os.environ.get("AGENT_POST_BUDGET_USD") or str(_DEFAULT_POST_BUDGET_USD)).strip()
        )
        self._synth_fallback_model = (os.environ.get("SYNTH_FALLBACK_MODEL") or "").strip()
        # 프로세스 단위 escalation율 카운터 (AC #7 — Prometheus 연동은 Epic 5 backlog).
        self._posts_total = 0
        self._escalated = 0
        self._budget_degraded = 0
        self._budget_fallback = 0  # 예산 초과를 SYNTH_FALLBACK_MODEL로 흡수한 건수
        self._s3_failed = 0

    @property
    def model_name(self) -> str:
        """비용 집계 표시용 대표 모델 — 실제 record는 pipeline이 스테이지(trace)별로 수행."""
        return self._triage.model

    @property
    def model_version(self) -> str:
        """single 모드와 분리된 agentic 식별자 — (post_id, model_version) 유니크 공존(3-9 A/B).

        S3 합류(3-8)부터 `agentic:v1:{triage}+{synth}:{YYYY-MM}` (축약: mini+4o, ≤VARCHAR(50)).
        synthesizer 미주입(3-7 구성) 시 기존 포맷 유지.
        """
        release = (os.environ.get("LLM_MODEL_RELEASE_DATE") or "").strip()
        if not release:
            release = datetime.now(timezone.utc).strftime("%Y-%m")
        if self._synthesizer is not None:
            models = f"{_short_model(self._triage.model)}+{_short_model(self._synthesizer.model)}"
        else:
            models = self._triage.model
        version = f"agentic:v1:{models}:{release}"
        if len(version) > 50:
            # 무음 절단 시 :{YYYY-MM} suffix가 소실돼 (post_id, model_version) A/B 변별력이
            # 깨질 수 있다(3-9) — 커스텀 모델명은 _MODEL_SHORT_NAMES 등재 권장.
            _logger.warning(
                "model_version 50자 초과 — 절단됨: %r → %r",
                version, version[:50],
                extra={"correlation_id": "", "service": _SERVICE_NAME},
            )
        return version[:50]

    def run(
        self,
        raw_text: str,
        correlation_id: str = "",
        images: list[str] | None = None,
    ) -> tuple[LLMResponse, list[AgentRunTrace]]:
        traces: list[AgentRunTrace] = []
        # 카운터 증분은 종결 시점(_log_outcome) — RetryHandler가 run() 전체를 재시도하므로
        # 진입 시 증분하면 attempt 단위로 중복 카운트되어 escalation율이 왜곡된다 (AC #7).

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

        if is_fast_path:
            verdict = self._triage_verdict(triage, None, traces)
            self._log_outcome("fast_path", triage, normalized.links, correlation_id, traces)
            return verdict, traces

        # ESCALATE.
        path, verdict = self._run_escalate(
            normalized.text, triage, normalized.links, images or [], correlation_id, traces,
        )
        self._log_outcome(path, triage, normalized.links, correlation_id, traces)
        return verdict, traces

    # ── escalate 경로 ────────────────────────────────────────────────────

    def _run_escalate(
        self,
        text: str,
        triage: TriageResult,
        links: list[str],
        images: list[str],
        correlation_id: str,
        traces: list[AgentRunTrace],
    ) -> tuple[str, LLMResponse]:
        # 예산 체크 ① — S2 착수 전 (트리아지만으로 초과하는 꼬리 케이스).
        if self._budget_exceeded(traces):
            # 실제로 수행 예정이던 stage만 나열 — 이미지/링크 없는 게시글의 과대 계상 방지(3-9 집계).
            skipped = [
                stage for stage, planned in (("image", bool(images)), ("link_trace", bool(links)))
                if planned
            ] + ["synthesize"]
            self._append_budget_skip_trace(traces, skipped)
            self._budget_degraded += 1
            return "escalate_budget_degraded", self._triage_verdict(triage, None, traces)

        # S2a ∥ S2b — ThreadPoolExecutor 병렬 (AC #2). 실패는 stage별 격리.
        image_evidence, link_evidence = self._run_s2_parallel(
            text, links, images, correlation_id, traces,
        )

        # synthesizer 미주입(3-7 구성) — 기존 degrade 동작 유지.
        if self._synthesizer is None:
            return "escalate_degrade", self._triage_verdict(triage, image_evidence, traces)

        # 예산 체크 ② — S3 착수 전. 초과 시 fallback 모델(opt-in) 또는 degrade.
        synth_model: str | None = None
        if self._budget_exceeded(traces):
            if not self._synth_fallback_model:
                self._append_budget_skip_trace(traces, ["synthesize"])
                self._budget_degraded += 1
                return "escalate_budget_degraded", self._triage_verdict(triage, image_evidence, traces)
            synth_model = self._synth_fallback_model
            self._budget_fallback += 1  # 예산 초과 사건 — fallback이어도 종결 로그에서 관측 가능해야 함

        # S3 synthesize — 실패 시 트리아지 degrade (AC #6).
        t3 = time.perf_counter()
        used_model = synth_model or self._synthesizer.model
        try:
            synth_verdict = self._synthesizer.run(
                text, triage, image_evidence, link_evidence, model=synth_model,
            )
        except Exception as exc:  # noqa: BLE001 — verdict 없는 것보다 1차 분류라도 저장
            self._s3_failed += 1
            _logger.warning(
                "S3 합성 실패 — 트리아지 verdict로 degrade: %s", exc,
                extra={"correlation_id": correlation_id, "service": _SERVICE_NAME},
            )
            traces.append(AgentRunTrace(
                stage="synthesize", model=used_model, latency_ms=_now_ms(t3),
                # 검증 실패(AgentResponseError)면 이미 과금된 usage를 보존 — 비용 증발 방지.
                input_tokens=getattr(exc, "input_tokens", 0),
                output_tokens=getattr(exc, "output_tokens", 0),
                cost_usd=getattr(exc, "cost_usd", 0.0),
                output={"error": f"{type(exc).__name__}: {exc}"},
            ))
            return "escalate_s3_failed_degraded", self._triage_verdict(triage, image_evidence, traces)

        traces.append(AgentRunTrace(
            stage="synthesize", model=used_model,
            input_tokens=synth_verdict.input_tokens, output_tokens=synth_verdict.output_tokens,
            cost_usd=synth_verdict.cost_usd, latency_ms=_now_ms(t3),
            output={
                "type": synth_verdict.type, "confidence": synth_verdict.confidence,
                "image_observed": synth_verdict.image_observed,
                "budget_fallback": bool(synth_model),
            },
        ))

        total_in, total_out, total_cost = self._totals(traces)
        verdict = LLMResponse(
            type=synth_verdict.type,
            confidence=synth_verdict.confidence,
            reason_ko=synth_verdict.reason_ko,
            translated_text_ko=synth_verdict.translated_text_ko,
            image_observed=synth_verdict.image_observed,
            input_tokens=total_in,
            output_tokens=total_out,
            cost_usd=total_cost,
        )
        return "escalate_synthesized", verdict

    def _run_s2_parallel(
        self,
        text: str,
        links: list[str],
        images: list[str],
        correlation_id: str,
        traces: list[AgentRunTrace],
    ) -> tuple[ImageEvidence | None, list[LinkEvidence]]:
        """S2a(이미지)·S2b(링크) 병렬 실행. trace는 image → link_trace 순서로 결정론적 추가."""
        image_evidence: ImageEvidence | None = None
        link_evidence: list[LinkEvidence] = []

        # PII 가드(LLM_SEND_IMAGES=false) — S2a 자체 스킵 + trace 기록 (Task 3).
        pii_skipped = bool(images) and self._image_analyst is not None and not self._image_analyst.enabled
        # 부분 주입 구성(analyst 미주입 + 이미지 존재) — 무음 누락 대신 skip trace로 식별 가능하게.
        not_configured = bool(images) and self._image_analyst is None
        run_s2a = bool(images) and self._image_analyst is not None and self._image_analyst.enabled
        run_s2b = bool(links)

        def _timed(fn, *args):
            start = time.perf_counter()
            return fn(*args), _now_ms(start)

        fut_image = fut_link = None
        t2 = time.perf_counter()  # 실패 시 latency 근사용 (submit 시점 ≈ 양 future 공통 시작점)
        if run_s2a or run_s2b:
            with ThreadPoolExecutor(max_workers=2) as pool:
                if run_s2a:
                    fut_image = pool.submit(_timed, self._image_analyst.run, text, images)
                if run_s2b:
                    fut_link = pool.submit(_timed, self._link_tracer.trace, links, correlation_id)
                # with 블록 종료 시 양쪽 완료 대기 — 결과 수집은 아래에서 stage 순서대로.

        # S2a trace (image) — skip/성공/실패 3분기.
        if pii_skipped:
            traces.append(AgentRunTrace(
                stage="image", model=None, output={"skipped": "LLM_SEND_IMAGES=false"},
            ))
        elif not_configured:
            traces.append(AgentRunTrace(
                stage="image", model=None, output={"skipped": "image_analyst_not_configured"},
            ))
        elif fut_image is not None:
            try:
                image_evidence, latency = fut_image.result()
            except Exception as exc:  # noqa: BLE001 — S2a 실패가 S3를 막으면 안 됨 (S2b와 동일 원칙)
                _logger.warning(
                    "S2a 이미지 분석 실패 — 증거 없이 진행: %s", exc,
                    extra={"correlation_id": correlation_id, "service": _SERVICE_NAME},
                )
                traces.append(AgentRunTrace(
                    stage="image", model=self._image_analyst.model,
                    # 검증 실패(AgentResponseError)면 이미 과금된 usage를 보존 — 비용 증발 방지.
                    input_tokens=getattr(exc, "input_tokens", 0),
                    output_tokens=getattr(exc, "output_tokens", 0),
                    cost_usd=getattr(exc, "cost_usd", 0.0),
                    latency_ms=_now_ms(t2),
                    output={"error": f"{type(exc).__name__}: {exc}"},
                ))
            else:
                if image_evidence is None:
                    traces.append(AgentRunTrace(
                        stage="image", model=None, latency_ms=latency,
                        output={"skipped": "no_resolvable_images"},
                    ))
                else:
                    traces.append(AgentRunTrace(
                        stage="image", model=self._image_analyst.model,
                        input_tokens=image_evidence.input_tokens,
                        output_tokens=image_evidence.output_tokens,
                        cost_usd=image_evidence.cost_usd, latency_ms=latency,
                        output={
                            "illegal_indicators": image_evidence.illegal_indicators,
                            "extracted_text": image_evidence.extracted_text[:1000],
                            "summary_ko": image_evidence.summary_ko,
                            "contributes": image_evidence.contributes,
                        },
                    ))

        # S2b trace (link_trace) — trace() 내부에서 링크별 실패 격리 완료.
        if fut_link is not None:
            try:
                link_evidence, latency = fut_link.result()
            except Exception as exc:  # noqa: BLE001 — 방어적 (trace()는 자체 격리하지만 만일을 대비)
                _logger.warning(
                    "S2b 링크 추적 실패 — 증거 없이 진행: %s", exc,
                    extra={"correlation_id": correlation_id, "service": _SERVICE_NAME},
                )
                link_evidence = []
                # S2a와 대칭 — 실패도 trace로 남겨 "링크 없음"과 "추적 실패"를 구분 (전수 trace).
                traces.append(AgentRunTrace(
                    stage="link_trace", model=None, latency_ms=_now_ms(t2),
                    output={"error": f"{type(exc).__name__}: {exc}"},
                ))
            else:
                traces.append(AgentRunTrace(
                    stage="link_trace", model=None, latency_ms=latency,
                    output={"links": [asdict(e) for e in link_evidence]},
                ))

        return image_evidence, link_evidence

    # ── 헬퍼 ────────────────────────────────────────────────────────────

    def _budget_exceeded(self, traces: list[AgentRunTrace]) -> bool:
        if self._post_budget <= 0:
            return False
        return sum(t.cost_usd for t in traces) >= self._post_budget

    def _append_budget_skip_trace(self, traces: list[AgentRunTrace], skipped_stages: list[str]) -> None:
        """예산 degrade 마커 — 3-9가 agent_runs에서 budget degrade 빈도를 셀 수 있게 기록."""
        traces.append(AgentRunTrace(
            stage="synthesize", model=None,
            output={
                "skipped": "budget_exceeded",
                "spent_usd": round(sum(t.cost_usd for t in traces), 6),
                "budget_usd": self._post_budget,
                "skipped_stages": skipped_stages,
            },
        ))

    def _triage_verdict(
        self,
        triage: TriageResult,
        image_evidence: ImageEvidence | None,
        traces: list[AgentRunTrace],
    ) -> LLMResponse:
        """트리아지 결과를 최종 verdict로 (fast path / degrade 공통).

        image_observed는 수집된 S2a contributes 반영(없으면 False). 토큰/비용은 스테이지 합산
        — degrade여도 detections.cost_usd는 실지출을 반영해야 함 (3-9 비용 실측 전제).
        """
        total_in, total_out, total_cost = self._totals(traces)
        return LLMResponse(
            type=triage.type,
            confidence=triage.confidence,
            reason_ko=triage.reason_ko,
            translated_text_ko=triage.translated_text_ko,
            image_observed=bool(image_evidence.contributes) if image_evidence is not None else False,
            input_tokens=total_in,
            output_tokens=total_out,
            cost_usd=total_cost,
        )

    @staticmethod
    def _totals(traces: list[AgentRunTrace]) -> tuple[int, int, float]:
        return (
            sum(t.input_tokens for t in traces),
            sum(t.output_tokens for t in traces),
            sum(t.cost_usd for t in traces),
        )

    def _log_outcome(
        self,
        path: str,
        triage: TriageResult,
        links: list[str],
        correlation_id: str,
        traces: list[AgentRunTrace],
    ) -> None:
        """게시글 종결 로그 — 스테이지 비용·latency + 누적 escalation율 (AC #7).

        카운터 증분도 여기서 수행 — 종결까지 도달한 run만 게시글 1건으로 센다
        (RetryHandler 재시도 attempt는 미집계).
        """
        self._posts_total += 1
        if path != "fast_path":
            self._escalated += 1
        stage_costs = {t.stage: round(t.cost_usd, 6) for t in traces}
        stage_latency = {t.stage: t.latency_ms for t in traces if t.latency_ms is not None}
        total_cost = sum(t.cost_usd for t in traces)
        escalation_rate = self._escalated / self._posts_total if self._posts_total else 0.0
        _logger.info(
            "orchestrator — path=%s type=%s conf=%.3f links=%d needs_image=%s "
            "total_cost=$%.5f escalation_rate=%.2f",
            path, triage.type, triage.confidence, len(links), triage.needs_image,
            total_cost, escalation_rate,
            extra={
                "correlation_id": correlation_id, "service": _SERVICE_NAME,
                "path": path, "triage_type": triage.type,
                "stage_costs": stage_costs, "stage_latency_ms": stage_latency,
                "total_cost_usd": round(total_cost, 6),
                "escalated": path != "fast_path",
                "escalation_rate": round(escalation_rate, 4),
                "budget_degraded_total": self._budget_degraded,
                "budget_fallback_total": self._budget_fallback,
                "s3_failed_total": self._s3_failed,
            },
        )
        # 50% 초과 지속 시 fast-path 임계 하향 조정 신호 (표본 최소치 도달 후).
        if self._posts_total >= _ESCALATION_WARN_MIN_POSTS and escalation_rate > _ESCALATION_WARN_RATE:
            _logger.warning(
                "escalation율 %.0f%% > 50%% — FAST_PATH_CONFIDENCE(%.2f) 하향 조정 검토 신호",
                escalation_rate * 100, self._fast_path_conf,
                extra={
                    "correlation_id": correlation_id, "service": _SERVICE_NAME,
                    "escalation_rate": round(escalation_rate, 4),
                    "fast_path_confidence": self._fast_path_conf,
                },
            )
