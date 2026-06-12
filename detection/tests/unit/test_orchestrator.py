"""AgentOrchestrator 단위 테스트 (Story 3-7) — fast path vs escalate-degrade FSM + traces.

LLMMock(트리아지) + LinkTracer(MockTransport) — 외부 네트워크·실제 Redis 0건.
"""

from __future__ import annotations

import fakeredis
import httpx
import pytest

import detection.src.agents.link_fetch_guard as guard_mod
from detection.src.agents.link_tracer import LinkTracer
from detection.src.agents.orchestrator import AgentOrchestrator
from detection.src.agents.triage_agent import TriageAgent
from detection.src.mocks.llm_mock import LLMMock


@pytest.fixture(autouse=True)
def _allow_public_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(guard_mod, "_resolve_all_ips", lambda host: ["93.184.216.34"])


def _ok_html(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200, content=b"<html><title>p</title><body>x</body></html>",
        headers={"content-type": "text/html"},
    )


def _orchestrator(triage_mode: str, link_handler=None) -> AgentOrchestrator:
    triage = TriageAgent(LLMMock(mode=triage_mode), model="gpt-4o-mini")
    redis_client = fakeredis.FakeRedis(decode_responses=True)
    handler = link_handler if link_handler is not None else _ok_html
    tracer = LinkTracer(redis_client, transport=httpx.MockTransport(handler))
    return AgentOrchestrator(triage, tracer)


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
