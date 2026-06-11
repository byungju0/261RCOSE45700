"""AgentOrchestrator 단위 테스트 (Story 3-7 / 3-8) — FSM + S2a∥S2b + S3 + 예산 가드.

LLMMock(트리아지) + LinkTracer(MockTransport) + 스텁 에이전트 — 외부 네트워크·실제 Redis 0건.
"""

from __future__ import annotations

import fakeredis
import httpx
import pytest

import detection.src.agents.link_fetch_guard as guard_mod
from detection.src.agents.contracts import AgentResponseError, ImageEvidence
from detection.src.agents.link_tracer import LinkTracer
from detection.src.agents.orchestrator import AgentOrchestrator
from detection.src.agents.triage_agent import TriageAgent
from detection.src.mocks.llm_mock import LLMMock
from shared.interfaces.llm import LLMResponse


@pytest.fixture(autouse=True)
def _allow_public_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(guard_mod, "_resolve_all_ips", lambda host: ["93.184.216.34"])
    # 예산 가드 기본 비활성 — 예산 테스트에서 개별 설정.
    monkeypatch.setenv("AGENT_POST_BUDGET_USD", "0")


def _ok_html(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200, content=b"<html><title>p</title><body>x</body></html>",
        headers={"content-type": "text/html"},
    )


class _StubAnalyst:
    """S2a ImageAnalyst 스텁 — enabled/run 인터페이스만."""

    model = "gpt-4o"

    def __init__(self, evidence: ImageEvidence | None, enabled: bool = True, error: Exception | None = None) -> None:
        self._evidence = evidence
        self._enabled = enabled
        self._error = error
        self.calls: list[tuple[str, list[str]]] = []

    @property
    def enabled(self) -> bool:
        return self._enabled

    def run(self, text: str, images: list[str]) -> ImageEvidence | None:
        self.calls.append((text, images))
        if self._error is not None:
            raise self._error
        return self._evidence


class _StubSynth:
    """S3 Synthesizer 스텁 — run(model=...) 캡처."""

    model = "gpt-4o"

    def __init__(self, verdict: LLMResponse | None = None, error: Exception | None = None) -> None:
        self._verdict = verdict or _synth_verdict()
        self._error = error
        self.calls: list[dict] = []

    def run(self, text, triage, image_evidence, link_evidence, model=None) -> LLMResponse:
        self.calls.append({
            "image_evidence": image_evidence, "link_evidence": link_evidence, "model": model,
        })
        if self._error is not None:
            raise self._error
        return self._verdict


def _synth_verdict(**overrides) -> LLMResponse:
    base = dict(
        type="핵_치트", confidence=0.97,
        reason_ko="링크 추적 결과 다운로드 페이지 확인.", translated_text_ko=None,
        image_observed=True, input_tokens=1500, output_tokens=80, cost_usd=0.008,
    )
    base.update(overrides)
    return LLMResponse(**base)


def _image_evidence(contributes: bool = True) -> ImageEvidence:
    return ImageEvidence(
        illegal_indicators=["핵 UI 오버레이"], extracted_text="ESP aimbot",
        summary_ko="핵 실행 화면.", contributes=contributes,
        input_tokens=900, output_tokens=60, cost_usd=0.0058,
    )


def _orchestrator(triage_mode: str, link_handler=None, image_analyst=None, synthesizer=None) -> AgentOrchestrator:
    triage = TriageAgent(LLMMock(mode=triage_mode), model="gpt-4o-mini")
    redis_client = fakeredis.FakeRedis(decode_responses=True)
    handler = link_handler if link_handler is not None else _ok_html
    tracer = LinkTracer(redis_client, transport=httpx.MockTransport(handler))
    return AgentOrchestrator(triage, tracer, image_analyst=image_analyst, synthesizer=synthesizer)


def test_fast_path_no_links_skips_link_trace() -> None:
    # clean mock: type=기타 conf=0.92 ≥0.80, 본문에 링크 없음 → fast path.
    orch = _orchestrator("clean")
    verdict, traces = orch.run("정상 게임 공략 공유합니다.")

    assert verdict.type == "기타"
    assert verdict.image_observed is False
    stages = [t.stage for t in traces]
    assert stages == ["normalize", "triage"]  # link_trace 없음


def test_escalate_traces_links_and_degrades_to_triage() -> None:
    # illegal mock: type=매크로_판매 → fast path 아님. 본문에 링크 → escalate, S2b 추적.
    calls: list[str] = []

    def _handler(r: httpx.Request) -> httpx.Response:
        calls.append(str(r.url))
        return httpx.Response(
            200, content=b"<html><title>Macro Sale</title><body>download price 5000</body></html>",
            headers={"content-type": "text/html"},
        )

    orch = _orchestrator("illegal", _handler)
    verdict, traces = orch.run("매크로 팝니다 https://evil.example/macro 연락주세요")

    # degrade: 최종 verdict = 트리아지 결과 (S3 Synthesizer 없음).
    assert verdict.type == "매크로_판매"
    assert verdict.image_observed is False
    stages = [t.stage for t in traces]
    assert stages == ["normalize", "triage", "link_trace"]
    # 링크가 실제 추적됐는지 (1회 fetch).
    assert len(calls) == 1
    link_trace = next(t for t in traces if t.stage == "link_trace")
    assert link_trace.output["links"][0]["kind"] == "web"


def test_high_conf_기타_with_link_escalates() -> None:
    # type=기타 high conf이지만 링크가 있으면 fast path 아님 → 링크 추적.
    orch = _orchestrator("clean")
    verdict, traces = orch.run("정상 글 https://evil.example/x 보세요")
    assert verdict.type == "기타"
    stages = [t.stage for t in traces]
    assert "link_trace" in stages


def test_traces_carry_triage_cost_and_model() -> None:
    orch = _orchestrator("illegal")
    _, traces = orch.run("매크로 팝니다 https://evil.example/m")
    triage_trace = next(t for t in traces if t.stage == "triage")
    assert triage_trace.model == "gpt-4o-mini"
    assert triage_trace.cost_usd > 0
    normalize_trace = next(t for t in traces if t.stage == "normalize")
    assert normalize_trace.model is None  # LLM 미사용


def test_model_version_is_agentic_namespaced(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_MODEL_RELEASE_DATE", "2026-06")
    orch = _orchestrator("clean")
    assert orch.model_version == "agentic:v1:gpt-4o-mini:2026-06"
    assert orch.model_name == "gpt-4o-mini"


# ── Story 3-8: S2a∥S2b + S3 + 예산 가드 ──────────────────────────────────


def test_escalate_full_path_synthesized() -> None:
    # AC #1~#3: escalate → S2a∥S2b 증거 수집 → S3 통합 verdict (5필드).
    analyst = _StubAnalyst(_image_evidence())
    synth = _StubSynth()
    orch = _orchestrator("illegal", image_analyst=analyst, synthesizer=synth)

    verdict, traces = orch.run(
        "매크로 팝니다 https://evil.example/m",
        images=["https://example.com/shot.jpg"],
    )

    # S3 verdict 채택 + image_observed = S2a contributes.
    assert verdict.type == "핵_치트"
    assert verdict.confidence == 0.97
    assert verdict.image_observed is True
    # 결정론적 trace 순서.
    stages = [t.stage for t in traces]
    assert stages == ["normalize", "triage", "image", "link_trace", "synthesize"]
    # 토큰/비용은 스테이지 합산 (triage 0.00118 + image 0.0058 + synth 0.008).
    assert verdict.cost_usd == pytest.approx(0.00118 + 0.0058 + 0.008)
    assert verdict.input_tokens == 150 + 900 + 1500
    # S3가 증거를 실제로 소비.
    assert synth.calls[0]["image_evidence"] is not None
    assert len(synth.calls[0]["link_evidence"]) == 1


def test_escalate_without_images_runs_s2b_and_s3_only() -> None:
    synth = _StubSynth()
    orch = _orchestrator("illegal", image_analyst=_StubAnalyst(_image_evidence()), synthesizer=synth)
    verdict, traces = orch.run("매크로 팝니다 https://evil.example/m", images=None)

    stages = [t.stage for t in traces]
    assert stages == ["normalize", "triage", "link_trace", "synthesize"]
    assert verdict.type == "핵_치트"
    assert synth.calls[0]["image_evidence"] is None  # 이미지 없음 → S2a 미실행


def test_escalate_no_links_no_images_still_synthesizes() -> None:
    # escalate 전부 S3 경유 (비용 모델: S3 적용률 = escalate 100%).
    synth = _StubSynth()
    orch = _orchestrator("illegal", synthesizer=synth)
    _, traces = orch.run("매크로 팝니다 연락주세요")  # 링크 없음 + 이미지 없음

    stages = [t.stage for t in traces]
    assert stages == ["normalize", "triage", "synthesize"]
    assert len(synth.calls) == 1


def test_pii_disabled_records_image_skip_trace() -> None:
    # AC 연계 Task 3: LLM_SEND_IMAGES=false → S2a skip + trace 기록.
    analyst = _StubAnalyst(_image_evidence(), enabled=False)
    synth = _StubSynth()
    orch = _orchestrator("illegal", image_analyst=analyst, synthesizer=synth)

    _, traces = orch.run("매크로 팝니다 https://evil.example/m", images=["https://example.com/a.jpg"])

    image_trace = next(t for t in traces if t.stage == "image")
    assert image_trace.model is None
    assert image_trace.output["skipped"] == "LLM_SEND_IMAGES=false"
    assert analyst.calls == []  # LLM 호출 0
    assert synth.calls[0]["image_evidence"] is None


def test_unresolvable_images_records_skip_trace() -> None:
    analyst = _StubAnalyst(None)  # run이 None 반환 (resolve 실패 시나리오)
    synth = _StubSynth()
    orch = _orchestrator("illegal", image_analyst=analyst, synthesizer=synth)

    _, traces = orch.run("매크로 팝니다 https://evil.example/m", images=["s3://bucket/x.jpg"])

    image_trace = next(t for t in traces if t.stage == "image")
    assert image_trace.output["skipped"] == "no_resolvable_images"
    assert synth.calls[0]["image_evidence"] is None


def test_s2a_failure_does_not_block_s3() -> None:
    # AC #6 정신: S2a 실패는 격리 — 이미지 증거 없이 S3 진행.
    analyst = _StubAnalyst(None, error=RuntimeError("vision api down"))
    synth = _StubSynth()
    orch = _orchestrator("illegal", image_analyst=analyst, synthesizer=synth)

    verdict, traces = orch.run("매크로 팝니다 https://evil.example/m", images=["https://example.com/a.jpg"])

    image_trace = next(t for t in traces if t.stage == "image")
    assert "error" in image_trace.output
    assert len(synth.calls) == 1
    assert synth.calls[0]["image_evidence"] is None
    assert verdict.type == "핵_치트"  # S3 verdict 정상 채택


def test_budget_exceeded_after_triage_skips_s2_and_s3(monkeypatch: pytest.MonkeyPatch) -> None:
    # AC #5: 누적 비용 ≥ 예산 → 잔여 stage 스킵, 트리아지 verdict degrade. 저장은 항상 수행.
    monkeypatch.setenv("AGENT_POST_BUDGET_USD", "0.000001")  # triage 0.00118가 즉시 초과
    analyst = _StubAnalyst(_image_evidence())
    synth = _StubSynth()
    orch = _orchestrator("illegal", image_analyst=analyst, synthesizer=synth)

    verdict, traces = orch.run("매크로 팝니다 https://evil.example/m", images=["https://example.com/a.jpg"])

    assert verdict.type == "매크로_판매"  # 트리아지 degrade
    assert analyst.calls == [] and synth.calls == []  # S2a/S3 스킵
    stages = [t.stage for t in traces]
    assert "link_trace" not in stages  # S2b도 스킵
    synth_trace = next(t for t in traces if t.stage == "synthesize")
    assert synth_trace.model is None
    assert synth_trace.output["skipped"] == "budget_exceeded"
    assert synth_trace.output["spent_usd"] == pytest.approx(0.00118)


def test_budget_exceeded_before_s3_degrades_with_collected_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    # AC #5: S2 증거 수집 후 예산 초과 → S3 스킵, "현재까지의 증거로" degrade.
    monkeypatch.setenv("AGENT_POST_BUDGET_USD", "0.002")  # triage 0.00118 < 0.002 < +image 0.0058
    analyst = _StubAnalyst(_image_evidence(contributes=True))
    synth = _StubSynth()
    orch = _orchestrator("illegal", image_analyst=analyst, synthesizer=synth)

    verdict, traces = orch.run("매크로 팝니다 https://evil.example/m", images=["https://example.com/a.jpg"])

    assert len(analyst.calls) == 1  # S2a는 실행됨
    assert synth.calls == []        # S3 스킵
    assert verdict.type == "매크로_판매"          # 트리아지 degrade
    assert verdict.image_observed is True          # 수집된 S2a contributes 반영
    synth_trace = next(t for t in traces if t.stage == "synthesize")
    assert synth_trace.output["skipped"] == "budget_exceeded"
    # degrade여도 비용 합산은 실비용 반영 (triage + image).
    assert verdict.cost_usd == pytest.approx(0.00118 + 0.0058)


def test_synth_fallback_model_on_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    # AC #5 "S3-mini" opt-in: SYNTH_FALLBACK_MODEL 설정 시 예산 초과에도 mini로 1회 합성.
    monkeypatch.setenv("AGENT_POST_BUDGET_USD", "0.002")
    monkeypatch.setenv("SYNTH_FALLBACK_MODEL", "gpt-4o-mini")
    analyst = _StubAnalyst(_image_evidence())
    synth = _StubSynth()
    orch = _orchestrator("illegal", image_analyst=analyst, synthesizer=synth)

    verdict, traces = orch.run("매크로 팝니다 https://evil.example/m", images=["https://example.com/a.jpg"])

    assert len(synth.calls) == 1
    assert synth.calls[0]["model"] == "gpt-4o-mini"
    assert verdict.type == "핵_치트"  # 합성 verdict 채택
    synth_trace = next(t for t in traces if t.stage == "synthesize")
    assert synth_trace.model == "gpt-4o-mini"


def test_s3_failure_degrades_to_triage_with_failure_trace() -> None:
    # AC #6: S3 실패 → 트리아지 degrade 저장 + agent_runs 실패 trace.
    analyst = _StubAnalyst(_image_evidence(contributes=True))
    synth = _StubSynth(error=TimeoutError("synthesis timeout"))
    orch = _orchestrator("illegal", image_analyst=analyst, synthesizer=synth)

    verdict, traces = orch.run("매크로 팝니다 https://evil.example/m", images=["https://example.com/a.jpg"])

    assert verdict.type == "매크로_판매"  # 트리아지 degrade
    assert verdict.image_observed is True  # 수집된 증거는 유지
    synth_trace = next(t for t in traces if t.stage == "synthesize")
    assert synth_trace.model == "gpt-4o"
    assert "TimeoutError" in synth_trace.output["error"]


def test_fast_path_bypasses_s3() -> None:
    synth = _StubSynth()
    orch = _orchestrator("clean", synthesizer=synth)
    verdict, traces = orch.run("정상 게임 공략 공유합니다.")
    assert synth.calls == []
    assert [t.stage for t in traces] == ["normalize", "triage"]
    assert verdict.type == "기타"


def test_model_version_with_synthesizer(monkeypatch: pytest.MonkeyPatch) -> None:
    # 변경 제안서 확정 포맷: agentic:v1:mini+4o:{YYYY-MM} (VARCHAR(50) 이내).
    monkeypatch.setenv("LLM_MODEL_RELEASE_DATE", "2026-06")
    orch = _orchestrator("clean", synthesizer=_StubSynth())
    assert orch.model_version == "agentic:v1:mini+4o:2026-06"
    assert len(orch.model_version) <= 50


# ── 2026-06-11 code review 패치 회귀 (Story 3-8) ──────────────────────────


def test_validation_failure_preserves_spent_cost() -> None:
    # 리뷰 MAJOR: LLM 호출 성공(과금) 후 검증 raise 시 실지출이 trace·verdict 합산에 보존돼야 함.
    err = AgentResponseError("invalid image payload", input_tokens=900, output_tokens=60, cost_usd=0.0058)
    analyst = _StubAnalyst(None, error=err)
    synth = _StubSynth()
    orch = _orchestrator("illegal", image_analyst=analyst, synthesizer=synth)

    verdict, traces = orch.run("매크로 팝니다 https://evil.example/m", images=["https://example.com/a.jpg"])

    image_trace = next(t for t in traces if t.stage == "image")
    assert "AgentResponseError" in image_trace.output["error"]
    assert image_trace.cost_usd == pytest.approx(0.0058)
    assert image_trace.input_tokens == 900
    # verdict 비용 합산(전 스테이지)에도 실지출 포함 — 예산 가드·cost_cap·detections.cost_usd 정합.
    assert verdict.cost_usd == pytest.approx(sum(t.cost_usd for t in traces))
    assert image_trace.cost_usd <= verdict.cost_usd


def test_s2b_failure_records_error_trace() -> None:
    # 리뷰 MAJOR: S2b future 실패도 trace로 남겨 "링크 없음"과 "추적 실패"를 구분 (S2a 대칭).
    class _BoomTracer:
        def trace(self, links, correlation_id=""):
            raise RuntimeError("tracer crashed")

    triage = TriageAgent(LLMMock(mode="illegal"), model="gpt-4o-mini")
    orch = AgentOrchestrator(triage, _BoomTracer(), synthesizer=_StubSynth())

    verdict, traces = orch.run("매크로 팝니다 https://evil.example/m")

    link_trace = next(t for t in traces if t.stage == "link_trace")
    assert "RuntimeError" in link_trace.output["error"]
    assert link_trace.latency_ms is not None
    assert verdict.type == "핵_치트"  # 실패 격리 — S3 verdict는 정상 채택


def test_counters_count_completed_posts_not_attempts() -> None:
    # 리뷰 MAJOR: RetryHandler가 run() 전체를 재시도하므로 중도 abort된 attempt는 미집계여야 함.
    orch = _orchestrator("illegal", synthesizer=_StubSynth())

    def _boom(text):
        raise TimeoutError("triage down")

    original_run = orch._triage.run
    orch._triage.run = _boom  # 1차 attempt — 트리아지 단계에서 abort
    with pytest.raises(TimeoutError):
        orch.run("매크로 팝니다 https://evil.example/m")
    assert orch._posts_total == 0 and orch._escalated == 0

    orch._triage.run = original_run  # 재시도 attempt — 정상 종결
    orch.run("매크로 팝니다 https://evil.example/m")
    assert orch._posts_total == 1 and orch._escalated == 1
