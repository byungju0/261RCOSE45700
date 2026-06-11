"""Story 3-7/3-8 실사 통합 smoke — agentic 모드 1건 처리 흐름 증명 (escalate 전 경로).

production 코드 경로(DETECTION_MODE=agentic)를 그대로 사용하되 Redis만 fakeredis로 in-memory
치환한다. 실제 OpenAI 호출(`OPENAI_API_KEY` 필요)이 수행되어
S0 normalize → S1 triage(gpt-4o-mini) → S2a ImageAnalyst(gpt-4o) ∥ S2b LinkTracer
→ S3 Synthesizer(gpt-4o) verdict까지 흐르고, 스테이지별 trace(agent_runs)와 비용이 출력된다.

이미지: `SMOKE_IMAGE` 환경변수로 로컬 스크린샷 경로를 지정하면 그 이미지를 판독한다(권장 —
핵 판매 스크린샷이면 contributes=true 확인 가능). 미지정 시 합성 PNG(단색)로 S2a 플러밍만
검증한다(contributes=false 예상). 본 스크립트는 S2a 검증을 위해 LLM_SEND_IMAGES=true를
명시 설정한다(스크립트 한정 opt-in — 운영 기본값은 false, PII 법무 검토 전).

DB 저장까지 보려면 V10이 적용된 PostgreSQL이 필요하다(운영자 `!` 실행 — 3-7 Task 1 노트 참조).
DB 미가동 시 repository=None으로 분류·trace까지만 검증한다.

Usage:
    DETECTION_MODE=agentic python detection/scripts/smoke_agent_pipeline.py
    SMOKE_IMAGE=/path/to/hack_screenshot.png python detection/scripts/smoke_agent_pipeline.py
"""

from __future__ import annotations

import os
import sys
import tempfile
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

# S2a 검증을 위한 스크립트 한정 opt-in (운영 기본 false — infra/.env.example 참조).
os.environ["LLM_SEND_IMAGES"] = "true"

import fakeredis  # noqa: E402

from detection.src.agents.image_analyst import ImageAnalyst  # noqa: E402
from detection.src.agents.link_tracer import LinkTracer  # noqa: E402
from detection.src.agents.orchestrator import AgentOrchestrator  # noqa: E402
from detection.src.agents.synthesizer import Synthesizer  # noqa: E402
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
    "리니지M 월핵 최신 버전 팝니다. 탐지 안 됨. 스크린샷 참고. "
    "다운로드: https://example.com/down 텔레그램 https://t.me/smoke_test_001"
)


def _smoke_image() -> str:
    """판독할 이미지 경로 — SMOKE_IMAGE 지정 시 그 경로, 아니면 합성 PNG 생성(플러밍 검증용)."""
    override = os.environ.get("SMOKE_IMAGE", "").strip()
    if override:
        if not Path(override).exists():
            sys.exit(f"[FAIL] SMOKE_IMAGE 파일 없음: {override}")
        print(f"[INFO] SMOKE_IMAGE 사용: {override}")
        return override

    # Pillow 없이 순수 stdlib로 64x64 단색 PNG 생성 — S2a 호출 플러밍만 검증.
    import struct
    import zlib

    width = height = 64
    raw = b"".join(b"\x00" + b"\xc8\x32\x32" * width for _ in range(height))

    def _chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data)) + tag + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    png = (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + _chunk(b"IDAT", zlib.compress(raw))
        + _chunk(b"IEND", b"")
    )
    tmp = Path(tempfile.gettempdir()) / "smoke_3_8_synthetic.png"
    tmp.write_bytes(png)
    print(f"[INFO] SMOKE_IMAGE 미지정 — 합성 PNG로 S2a 플러밍 검증 (contributes=false 예상): {tmp}")
    return str(tmp)


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
    image_model = os.environ.get("IMAGE_ANALYST_MODEL", "gpt-4o")
    synth_model = os.environ.get("SYNTHESIZER_MODEL", "gpt-4o")
    budget = os.environ.get("AGENT_POST_BUDGET_USD", "0.02")
    print(f"[INFO] DETECTION_MODE={os.environ['DETECTION_MODE']} "
          f"triage={triage_model} image={image_model} synth={synth_model} budget=${budget}")
    print(f"[INFO] key=...{api_key[-4:]} (length={len(api_key)})")

    image_path = _smoke_image()

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

    # Story 3-8: S0~S3 full wiring (main.py와 동일 구성).
    triage_agent = TriageAgent(llm)
    link_tracer = LinkTracer(dedup)
    image_analyst = ImageAnalyst(llm)
    synthesizer = Synthesizer(llm)
    orchestrator = AgentOrchestrator(
        triage_agent, link_tracer,
        image_analyst=image_analyst, synthesizer=synthesizer,
    )

    pipeline = DetectionPipeline(
        classifier, tier_router, cost_cap, retry_handler,
        repository=repository, orchestrator=orchestrator, mode="agentic",
    )

    event = CrawlEvent(
        post_id="smoke_3_8_001",
        source_id="smoke",
        site_name="Story 3-8 smoke",
        raw_text=_RAW_TEXT,
        language="ko",
        detected_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        correlation_id="smoke-3-8-cid-001",
        image_urls=[image_path],
    )

    # orchestrator를 직접 호출해 verdict + trace를 출력 (파이프라인 process는 로그만 남김).
    verdict, traces = orchestrator.run(
        event.raw_text, correlation_id=event.correlation_id, images=[image_path],
    )

    print("\n=== 최종 verdict (S3 합성 또는 degrade) ===")
    print(f"  type={verdict.type} confidence={verdict.confidence:.3f} "
          f"image_observed={verdict.image_observed}")
    print(f"  reason_ko={verdict.reason_ko}")
    print(f"  translated_text_ko={verdict.translated_text_ko}")
    print(f"  tokens(in/out)={verdict.input_tokens}/{verdict.output_tokens} "
          f"cost=${verdict.cost_usd:.5f} (스테이지 합산)")

    print("\n=== agent_runs trace ===")
    total_cost = 0.0
    for t in traces:
        total_cost += t.cost_usd
        print(f"  [{t.stage}] model={t.model} cost=${t.cost_usd:.5f} "
              f"latency={t.latency_ms}ms")
        if t.stage == "image" and t.output:
            if "skipped" in t.output:
                print(f"      image: skipped={t.output['skipped']}")
            elif "error" in t.output:
                print(f"      image: error={t.output['error']}")
            else:
                print(f"      image: contributes={t.output['contributes']} "
                      f"indicators={t.output['illegal_indicators']}")
                print(f"      image summary: {t.output['summary_ko']}")
        if t.stage == "link_trace" and t.output:
            for link in t.output.get("links", []):
                print(f"      link: kind={link['kind']} status={link['fetch_status']} "
                      f"distribution={link['is_distribution_site']}")
        if t.stage == "synthesize" and t.output:
            if "skipped" in t.output:
                print(f"      synthesize: skipped={t.output['skipped']} "
                      f"spent=${t.output.get('spent_usd', 0):.5f}")
            elif "error" in t.output:
                print(f"      synthesize: error={t.output['error']}")
    print(f"  -- total stage cost: ${total_cost:.5f} "
          f"(게시글당 예산 ${budget} — PRD 평균 ≤$0.005·p95 ≤$0.02)")

    # 파이프라인 전체 경로(저장 포함)도 1회 실행 — DB 있으면 detections + agent_runs 저장.
    if repository is not None:
        print("\n[INFO] repository 저장 경로 실행 (detections + agent_runs)")
        pipeline.process(event.to_json())
        print("[INFO] 저장 완료 — DB에서 agent_runs 확인 가능")

    tier = tier_router.route(verdict.type)
    synth_ran = any(
        t.stage == "synthesize" and t.output and "error" not in t.output and "skipped" not in t.output
        for t in traces
    )
    print(f"\n[DONE] Story 3-8 agentic smoke 통과 — type={verdict.type} tier={tier} "
          f"synthesized={synth_ran} model_version={orchestrator.model_version}, "
          f"{len(traces)} 스테이지 trace 생성.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
