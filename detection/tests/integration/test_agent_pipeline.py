"""Agentic 파이프라인 통합 + 출력 계약 불변 (Story 3-7 / 3-8).

DETECTION_MODE=agentic E2E를 LLMMock + LinkTracer(MockTransport) + fakeredis + MagicMock repo로
검증한다. 외부 OpenAI·실제 Redis·실제 PG 0건.
3-7: agentic E2E + single 회귀 + 출력 계약 불변. 3-8: escalate 전 경로(S2a∥S2b→S3) +
예산 degrade + S3 실패 fallback (AC #8).
"""

from __future__ import annotations

from dataclasses import fields
from unittest.mock import MagicMock

import fakeredis
import httpx
import pytest

import detection.src.agents.link_fetch_guard as guard_mod
from detection.src.agents.image_analyst import ImageAnalyst
from detection.src.agents.link_tracer import LinkTracer
from detection.src.agents.orchestrator import AgentOrchestrator
from detection.src.agents.synthesizer import Synthesizer
from detection.src.agents.triage_agent import TriageAgent
from detection.src.mocks.llm_mock import LLMMock
from detection.src.pipeline.detection_pipeline import DetectionPipeline
from detection.src.pipeline.llm_classifier import LLMClassifier
from detection.src.pipeline.tier_router import TierRouter
from detection.src.rate_limit.cost_cap import CostCap
from detection.src.rate_limit.token_bucket import TokenBucket
from detection.src.retry.retry_handler import RetryHandler
from shared.interfaces.llm import LLMResponse
from shared.models.crawl_event import CrawlEvent


@pytest.fixture(autouse=True)
def _env_setup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_DAILY_COST_CAP_USD", "0")
    monkeypatch.setenv("RETRY_BACKOFF_BASE_SEC", "0")
    monkeypatch.setenv("AGENT_POST_BUDGET_USD", "0")  # 예산 테스트에서 개별 설정
    monkeypatch.setattr(guard_mod, "_resolve_all_ips", lambda host: ["93.184.216.34"])


@pytest.fixture
def mq_redis() -> fakeredis.FakeRedis:
    return fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture
def rl_redis() -> fakeredis.FakeRedis:
    return fakeredis.FakeRedis(decode_responses=True)


def _event(raw_text: str, post_id: str = "p_001", image_urls: list[str] | None = None) -> CrawlEvent:
    return CrawlEvent(
        post_id=post_id, source_id="bahamut_lineage", site_name="Bahamut",
        raw_text=raw_text, language="zh-TW", detected_at="2026-06-11T00:00:00Z",
        correlation_id=f"cid-{post_id}", image_urls=image_urls or [],
    )


_MODEL_VERSION = "openai:gpt-4o:2024-08-06"


def _default_link_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200, content=b"<html><title>Sale</title><body>download price</body></html>",
        headers={"content-type": "text/html"},
    )


def _classifier(mode, rl_redis) -> LLMClassifier:
    bucket = TokenBucket(rl_redis, capacity=100, refill_per_sec=100)
    return LLMClassifier(LLMMock(mode=mode), bucket, model_version=_MODEL_VERSION)


def _agentic_pipeline(triage_mode, mq_redis, rl_redis, repo, link_handler=None, synth_llm=None):
    """3-8 full wiring (S0~S3). synth_llm으로 S3 실패 모드 주입 가능."""
    mock_llm = LLMMock(mode=triage_mode)
    triage = TriageAgent(mock_llm, model="gpt-4o-mini")
    handler = link_handler if link_handler is not None else _default_link_handler
    tracer = LinkTracer(
        fakeredis.FakeRedis(decode_responses=True),
        transport=httpx.MockTransport(handler),
    )
    image_analyst = ImageAnalyst(mock_llm, model="gpt-4o")
    synthesizer = Synthesizer(synth_llm or mock_llm, model="gpt-4o")
    orchestrator = AgentOrchestrator(
        triage, tracer, image_analyst=image_analyst, synthesizer=synthesizer,
    )
    return DetectionPipeline(
        classifier=_classifier(triage_mode, rl_redis),
        tier_router=TierRouter(),
        cost_cap=CostCap(rl_redis),
        retry_handler=RetryHandler(mq_redis),
        repository=repo,
        orchestrator=orchestrator,
        mode="agentic",
    )


def _single_pipeline(llm_mode, mq_redis, rl_redis, repo):
    return DetectionPipeline(
        classifier=_classifier(llm_mode, rl_redis),
        tier_router=TierRouter(),
        cost_cap=CostCap(rl_redis),
        retry_handler=RetryHandler(mq_redis),
        repository=repo,
        mode="single",
    )


def test_agentic_fast_path_saves_detection_without_link_trace(mq_redis, rl_redis) -> None:
    repo = MagicMock()
    repo.save.return_value = 1
    pipeline = _agentic_pipeline("clean", mq_redis, rl_redis, repo)

    pipeline.process(_event("정상 게임 공략입니다.").to_json())

    repo.save.assert_called_once()
    kwargs = repo.save.call_args.kwargs
    assert kwargs["tier"] == "T4"  # 기타 → T4
    assert kwargs["response"].type == "기타"
    assert kwargs["model_version"].startswith("agentic:v1:")
    # fast path → agent_runs는 normalize + triage 2건 (link_trace 없음).
    stages = [t.stage for t in kwargs["agent_runs"]]
    assert stages == ["normalize", "triage"]


def test_agentic_escalate_saves_link_trace_and_synthesizes(mq_redis, rl_redis) -> None:
    # 3-8: escalate 경로가 degrade가 아니라 S3 합성으로 종결된다.
    repo = MagicMock()
    repo.save.return_value = 2
    pipeline = _agentic_pipeline("illegal", mq_redis, rl_redis, repo)

    pipeline.process(_event("매크로 팝니다 https://evil.example/m").to_json())

    kwargs = repo.save.call_args.kwargs
    assert kwargs["response"].type == "매크로_판매"  # synth fixture verdict
    assert kwargs["tier"] == "T1"  # 매크로_판매 → T1
    assert kwargs["model_version"].startswith("agentic:v1:mini+4o:")
    stages = [t.stage for t in kwargs["agent_runs"]]
    assert stages == ["normalize", "triage", "link_trace", "synthesize"]


def test_agentic_escalate_full_path_with_images(mq_redis, rl_redis, monkeypatch) -> None:
    # AC #1~#3 E2E: 이미지 포함 escalate → S2a∥S2b → S3, agent_runs 5 stage.
    monkeypatch.setenv("LLM_SEND_IMAGES", "true")
    repo = MagicMock()
    repo.save.return_value = 4
    pipeline = _agentic_pipeline("illegal", mq_redis, rl_redis, repo)

    pipeline.process(
        _event(
            "매크로 팝니다 https://evil.example/m",
            post_id="p_img",
            image_urls=["https://example.com/macro_shot.jpg"],
        ).to_json()
    )

    kwargs = repo.save.call_args.kwargs
    stages = [t.stage for t in kwargs["agent_runs"]]
    assert stages == ["normalize", "triage", "image", "link_trace", "synthesize"]
    response = kwargs["response"]
    assert response.type == "매크로_판매"
    assert response.image_observed is True  # S2a contributes=true (fixture)
    # 비용 합산: triage 0.00118 + image 0.0058 + synth 0.008 (link_trace $0).
    assert response.cost_usd == pytest.approx(0.00118 + 0.0058 + 0.008)
    image_trace = next(t for t in kwargs["agent_runs"] if t.stage == "image")
    assert image_trace.model == "gpt-4o"
    assert image_trace.output["contributes"] is True


def test_agentic_budget_degrade_still_saves(mq_redis, rl_redis, monkeypatch) -> None:
    # AC #5 E2E: 예산 초과 → degrade 종결이어도 전수 저장 정책 유지.
    monkeypatch.setenv("AGENT_POST_BUDGET_USD", "0.000001")
    repo = MagicMock()
    repo.save.return_value = 5
    pipeline = _agentic_pipeline("illegal", mq_redis, rl_redis, repo)

    pipeline.process(_event("매크로 팝니다 https://evil.example/m", post_id="p_budget").to_json())

    repo.save.assert_called_once()  # 저장은 항상 수행
    kwargs = repo.save.call_args.kwargs
    assert kwargs["response"].type == "매크로_판매"  # 트리아지 degrade
    synth_trace = next(t for t in kwargs["agent_runs"] if t.stage == "synthesize")
    assert synth_trace.output["skipped"] == "budget_exceeded"
    stages = [t.stage for t in kwargs["agent_runs"]]
    assert "link_trace" not in stages  # 잔여 stage 스킵


def test_agentic_s3_failure_falls_back_to_triage(mq_redis, rl_redis) -> None:
    # AC #6 E2E: S3 실패 → 트리아지 결과로 degrade 저장 + 실패 trace.
    repo = MagicMock()
    repo.save.return_value = 6
    pipeline = _agentic_pipeline(
        "illegal", mq_redis, rl_redis, repo, synth_llm=LLMMock(mode="timeout"),
    )

    pipeline.process(_event("매크로 팝니다 https://evil.example/m", post_id="p_s3f").to_json())

    repo.save.assert_called_once()
    kwargs = repo.save.call_args.kwargs
    assert kwargs["response"].type == "매크로_판매"  # 트리아지 degrade (fixture와 동일 type)
    assert kwargs["response"].confidence == 0.95     # 트리아지 confidence (synth 0.97 아님)
    synth_trace = next(t for t in kwargs["agent_runs"] if t.stage == "synthesize")
    assert "TimeoutError" in synth_trace.output["error"]


def test_single_mode_unaffected_no_agent_runs(mq_redis, rl_redis) -> None:
    # single 모드 회귀: agent_runs=None으로 저장 (기존 동작 보존).
    repo = MagicMock()
    repo.save.return_value = 3
    pipeline = _single_pipeline("clean", mq_redis, rl_redis, repo)

    pipeline.process(_event("정상 글").to_json())

    kwargs = repo.save.call_args.kwargs
    assert kwargs["agent_runs"] is None
    assert kwargs["model_version"] == "openai:gpt-4o:2024-08-06"


def test_output_contract_invariant_single_vs_agentic(mq_redis, rl_redis) -> None:
    """single·agentic 두 모드가 detections에 채우는 필드 집합이 동일해야 한다 (AC #13).

    repository.save에 전달되는 response(LLMResponse) 필드 + tier/is_illegal 파생이 같은 계약인지
    검증 — 스키마/DTO/프론트 계약이 깨지면 CI에서 즉시 실패.
    """
    repo_single = MagicMock()
    repo_single.save.return_value = 1
    repo_agentic = MagicMock()
    repo_agentic.save.return_value = 1

    _single_pipeline("clean", mq_redis, rl_redis, repo_single).process(
        _event("정상 글", "ps").to_json()
    )
    _agentic_pipeline("clean", mq_redis, rl_redis, repo_agentic).process(
        _event("정상 글", "pa").to_json()
    )

    single_resp: LLMResponse = repo_single.save.call_args.kwargs["response"]
    agentic_resp: LLMResponse = repo_agentic.save.call_args.kwargs["response"]

    # 1) 동일 dataclass 타입 + 동일 필드 집합 (5필드 + 토큰/비용).
    assert type(single_resp) is type(agentic_resp) is LLMResponse
    detection_fields = {"type", "confidence", "reason_ko", "translated_text_ko", "image_observed"}
    resp_field_names = {f.name for f in fields(LLMResponse)}
    assert detection_fields <= resp_field_names

    # 2) save 호출 키 집합 동일 (agent_runs 포함 — single은 None, agentic은 list).
    assert set(repo_single.save.call_args.kwargs) == set(repo_agentic.save.call_args.kwargs)

    # 3) 두 모드 모두 동일 tier 파생 (기타 → T4).
    assert repo_single.save.call_args.kwargs["tier"] == repo_agentic.save.call_args.kwargs["tier"] == "T4"
