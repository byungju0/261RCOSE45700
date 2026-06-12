"""Story 3-7 실사 통합 smoke — agentic 모드 1건 처리 흐름 증명.

production 코드 경로(DETECTION_MODE=agentic)를 그대로 사용하되 Redis만 fakeredis로 in-memory
치환한다. 실제 OpenAI 호출(gpt-4o-mini 트리아지, `OPENAI_API_KEY` 필요)이 수행되어
S0 normalize → S1 triage → (escalate 시) S2b LinkTracer → degrade verdict까지 흐르고,
스테이지별 trace(agent_runs)와 비용이 출력된다.

DB 저장까지 보려면 V10이 적용된 PostgreSQL이 필요하다(운영자 `!` 실행 — 스토리 Task 1 노트 참조).
DB 미가동 시 repository=None으로 분류·trace까지만 검증한다.

Usage:
    DETECTION_MODE=agentic python detection/scripts/smoke_agent_pipeline.py
    # 링크 추적까지 보려면 본문에 외부 URL 포함 (아래 raw_text 기본값에 포함됨)
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv
except ImportError as exc:
    sys.exit(f"[FAIL] python-dotenv 미설치: {exc}")

ENV_PATH = PROJECT_ROOT / "infra" / ".env"
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)

api_key = os.environ.get("OPENAI_API_KEY", "")
if not api_key or api_key.startswith("sk-REPLACE"):
    sys.exit("[FAIL] OPENAI_API_KEY가 placeholder. infra/.env 갱신 필요.")

import fakeredis  # noqa: E402

from detection.src.agents.link_tracer import LinkTracer  # noqa: E402
from detection.src.agents.orchestrator import AgentOrchestrator  # noqa: E402
from detection.src.agents.triage_agent import TriageAgent  # noqa: E402
from detection.src.pipeline.detection_pipeline import DetectionPipeline  # noqa: E402
from detection.src.pipeline.llm_classifier import LLMClassifier  # noqa: E402
from detection.src.pipeline.llm_client import LLMClient  # noqa: E402
from detection.src.pipeline.tier_router import TierRouter  # noqa: E402
from detection.src.rate_limit.cost_cap import CostCap  # noqa: E402
from detection.src.rate_limit.token_bucket import TokenBucket  # noqa: E402
from detection.src.retry.retry_handler import RetryHandler  # noqa: E402
from shared.config.redis_config import (  # noqa: E402
    REDIS_KEY_LLM_RATE_LIMIT_CLASSIFY,
)
from shared.models.crawl_event import CrawlEvent  # noqa: E402

_RAW_TEXT = (
    "리니지M 월핵 최신 버전 팝니다. 탐지 안 됨. "
    "다운로드: https://example.com/down 텔레그램 https://t.me/smoke_test_001"
)


def _pg_reachable() -> bool:
    """PG 5432 소켓 도달 가능 여부 — 30초 pool 타임아웃 회피용 빠른 probe."""
    import socket
    host = os.environ.get("DB_HOST", "localhost")
    port = int(os.environ.get("DB_PORT", "5432"))
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


def _maybe_repository():
    """V10 적용된 PG가 있으면 repository 반환, 없으면 None (분류·trace까지만)."""
    if not os.environ.get("DB_PASSWORD") or not _pg_reachable():
        print(
            "[INFO] PG 미가동/미설정 — repository 없이 분류·trace까지만 검증. "
            "detections+agent_runs 저장은 V10 적용된 PG에서(운영자 ! 실행)."
        )
        return None
    try:
        from detection.src.config.db_config import get_pool
        from detection.src.repository.detection_repository import DetectionRepository
        return DetectionRepository(get_pool())
    except Exception as exc:  # noqa: BLE001
        print(f"[WARN] DB 연결 실패 — repository 없이 진행: {exc}")
        return None


def main() -> int:
    os.environ.setdefault("DETECTION_MODE", "agentic")
    triage_model = os.environ.get("TRIAGE_MODEL", "gpt-4o-mini")
    print(f"[INFO] DETECTION_MODE={os.environ['DETECTION_MODE']} triage_model={triage_model}")
    print(f"[INFO] key=...{api_key[-4:]} (length={len(api_key)})")

    mq = fakeredis.FakeRedis(decode_responses=True)
    rate_limit = fakeredis.FakeRedis(decode_responses=True)
    dedup = fakeredis.FakeRedis(decode_responses=True)

    llm = LLMClient()
    bucket = TokenBucket(
        rate_limit, key=REDIS_KEY_LLM_RATE_LIMIT_CLASSIFY, capacity=10, refill_per_sec=10
    )
    cost_cap = CostCap(rate_limit)
    classifier = LLMClassifier(llm, bucket)
    tier_router = TierRouter()
    retry_handler = RetryHandler(mq)
    repository = _maybe_repository()

    triage_agent = TriageAgent(llm)
    link_tracer = LinkTracer(dedup)
    orchestrator = AgentOrchestrator(triage_agent, link_tracer)

    pipeline = DetectionPipeline(
        classifier, tier_router, cost_cap, retry_handler,
        repository=repository, orchestrator=orchestrator, mode="agentic",
    )

    event = CrawlEvent(
        post_id="smoke_3_7_001",
        source_id="smoke",
        site_name="Story 3-7 smoke",
        raw_text=_RAW_TEXT,
        language="ko",
        detected_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        correlation_id="smoke-3-7-cid-001",
    )

    # orchestrator를 직접 호출해 verdict + trace를 출력 (파이프라인 process는 로그만 남김).
    verdict, traces = orchestrator.run(event.raw_text, correlation_id=event.correlation_id)

    print("\n=== 트리아지 verdict (degrade) ===")
    print(f"  type={verdict.type} confidence={verdict.confidence:.3f} "
          f"image_observed={verdict.image_observed}")
    print(f"  reason_ko={verdict.reason_ko}")
    print(f"  translated_text_ko={verdict.translated_text_ko}")
    print(f"  tokens(in/out)={verdict.input_tokens}/{verdict.output_tokens} "
          f"cost=${verdict.cost_usd:.5f}")

    print("\n=== agent_runs trace ===")
    total_cost = 0.0
    for t in traces:
        total_cost += t.cost_usd
        print(f"  [{t.stage}] model={t.model} cost=${t.cost_usd:.5f} "
              f"latency={t.latency_ms}ms")
        if t.stage == "link_trace" and t.output:
            for link in t.output.get("links", []):
                print(f"      link: kind={link['kind']} status={link['fetch_status']} "
                      f"distribution={link['is_distribution_site']}")
    print(f"  -- total stage cost: ${total_cost:.5f}")

    # 파이프라인 전체 경로(저장 포함)도 1회 실행 — DB 있으면 detections + agent_runs 저장.
    if repository is not None:
        print("\n[INFO] repository 저장 경로 실행 (detections + agent_runs)")
        pipeline.process(event.to_json())
        print("[INFO] 저장 완료 — DB에서 agent_runs 확인 가능")

    tier = tier_router.route(verdict.type)
    print(f"\n[DONE] Story 3-7 agentic smoke 통과 — type={verdict.type} tier={tier}, "
          f"{len(traces)} 스테이지 trace 생성.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
