"""A/B 재분류 + 정확도/비용 실측 (Story 3-9 Task 2/4).

Story 3-5의 `human_label`을 ground truth로, **같은 게시글을 single·agentic 두 모드로 재분류**해
`detections`에 `model_version` 분리로 공존시키고(`(post_id, model_version)` UNIQUE + ON CONFLICT
DO NOTHING → 멱등), agreement/Tier별 Recall·Precision/confusion + agentic 비용 분포(평균·p95·이미지
유/무)를 산출해 `docs/ab-comparison-3-9.md`에 기록한다.

핵심 함정(3-9): human_label은 **원본 행에만 1개** 존재한다 — 재분류한 agentic 행에는 없다.
그래서 `{post_id: human_label}` 맵을 만들고 양 모드 결과를 post_id로 조인한다(ab_metrics).

전제(운영자 `!` 실행): V9(human_label) + V10(agent_runs)가 적용된 PostgreSQL + 실 OPENAI_API_KEY.
로컬 dev DB는 수동 V5 drift라 flyway baseline 정리 후 V6~V10 적용 필요(memory: project_local_db_v5_drift).
실 OpenAI 비용이 발생한다 — `--limit N`으로 표본 크기를, `--dry-run`으로 분류 없이 ground truth
집합만 점검한다. cost_cap 일일 캡($5)이 상한.

Usage:
    python detection/scripts/ab_compare.py --dry-run            # ground truth 집합만 확인(무비용)
    python detection/scripts/ab_compare.py --limit 30           # 30건 표본 A/B
    python detection/scripts/ab_compare.py                      # 전체 라벨셋 A/B
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from detection.scripts.ab_metrics import (  # noqa: E402
    agreement,
    build_label_map,
    cost_summary,
    illegal_detection_rate,
    render_ab_markdown,
    tier_metrics,
)

DOC_PATH = PROJECT_ROOT / "docs" / "ab-comparison-3-9.md"


# ── DB 조회 (write는 DetectionPipeline.save 재사용) ──────────────────────────


def fetch_ground_truth(pool, limit: int | None = None) -> list[dict[str, Any]]:
    """human_label이 부여된(judgeable) 게시글 + 재분류에 필요한 본문·이미지·출처를 조회.

    post당 1행(DISTINCT post_id). human_label은 라벨된 detection 행에서, 본문/이미지는 posts/
    post_images에서 가져온다. unknown은 judgeable 분모 밖이라 제외.
    """
    sql = """
        SELECT p.id                      AS post_id,
               max(d.human_label)        AS human_label,
               s.site_name               AS source_id,
               COALESCE(s.board_name, s.site_name) AS site_name,
               p.post_id_at_source,
               p.body,
               p.language,
               p.post_url,
               COALESCE(
                   array_agg(pi.image_url) FILTER (WHERE pi.image_url IS NOT NULL),
                   '{}'
               ) AS image_urls,
               COALESCE(
                   array_agg(pi.s3_key) FILTER (WHERE pi.s3_key IS NOT NULL),
                   '{}'
               ) AS s3_image_paths
          FROM detections d
          JOIN posts p        ON p.id = d.post_id
          JOIN sources s      ON s.id = p.source_id
          LEFT JOIN post_images pi ON pi.post_id = p.id
         WHERE d.human_label IS NOT NULL
           AND d.human_label <> 'unknown'
         GROUP BY p.id, s.site_name, s.board_name,
                  p.post_id_at_source, p.body, p.language, p.post_url
         ORDER BY p.id
    """
    # GROUP BY에서 d.human_label을 빼고 max()로 집계 — post당 정확히 1행 보장(DISTINCT post_id).
    # 동일 post에 라벨 행이 둘 이상(예: single+agentic 모두 라벨)이어도 중복 행/이중 과금 방지.
    if limit is not None:
        sql += "\n         LIMIT %s"
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (limit,) if limit is not None else None)
            cols = [c.name for c in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]


def fetch_mode_detections(pool, post_ids: list[int], model_version: str) -> list[dict[str, Any]]:
    """한 모드(model_version)의 재분류 결과 — post_id/type/tier/cost_usd."""
    if not post_ids:
        return []
    sql = """
        SELECT post_id, type, tier, cost_usd
          FROM detections
         WHERE model_version = %s AND post_id = ANY(%s)
    """
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (model_version, post_ids))
            cols = [c.name for c in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]


def _build_event(row: dict[str, Any]):
    from shared.models.crawl_event import CrawlEvent

    return CrawlEvent(
        post_id=str(row["post_id_at_source"]),
        source_id=row["source_id"],
        site_name=row["site_name"],
        raw_text=row.get("body") or "",
        language=row.get("language") or "ko",
        detected_at="",  # repository가 NOW() fallback
        correlation_id=f"ab-3-9-{row['post_id']}",
        image_urls=list(row.get("image_urls") or []),
        s3_image_paths=list(row.get("s3_image_paths") or []),
        post_url=row.get("post_url") or "",
    )


def _build_pipelines(pool):
    """single + agentic DetectionPipeline (repository·cost_cap 공유). smoke wiring 재사용."""
    import fakeredis

    from detection.src.agents.image_analyst import ImageAnalyst
    from detection.src.agents.link_tracer import LinkTracer
    from detection.src.agents.orchestrator import AgentOrchestrator
    from detection.src.agents.synthesizer import Synthesizer
    from detection.src.agents.triage_agent import TriageAgent
    from detection.src.pipeline.detection_pipeline import DetectionPipeline
    from detection.src.pipeline.llm_classifier import LLMClassifier
    from detection.src.pipeline.llm_client import LLMClient
    from detection.src.pipeline.tier_router import TierRouter
    from detection.src.rate_limit.cost_cap import CostCap
    from detection.src.rate_limit.token_bucket import TokenBucket
    from detection.src.repository.detection_repository import DetectionRepository
    from detection.src.retry.retry_handler import RetryHandler
    from shared.config.redis_config import REDIS_KEY_LLM_RATE_LIMIT_CLASSIFY

    rate_limit = fakeredis.FakeRedis(decode_responses=True)
    mq = fakeredis.FakeRedis(decode_responses=True)
    dedup = fakeredis.FakeRedis(decode_responses=True)

    llm = LLMClient()
    bucket = TokenBucket(rate_limit, key=REDIS_KEY_LLM_RATE_LIMIT_CLASSIFY, capacity=10, refill_per_sec=10)
    cost_cap = CostCap(rate_limit)
    tier_router = TierRouter()
    retry_handler = RetryHandler(mq)
    repository = DetectionRepository(pool)

    classifier = LLMClassifier(llm, bucket)
    orchestrator = AgentOrchestrator(
        TriageAgent(llm), LinkTracer(dedup),
        image_analyst=ImageAnalyst(llm), synthesizer=Synthesizer(llm),
    )
    single = DetectionPipeline(
        classifier, tier_router, cost_cap, retry_handler, repository=repository, mode="single",
    )
    agentic = DetectionPipeline(
        classifier, tier_router, cost_cap, retry_handler,
        repository=repository, orchestrator=orchestrator, mode="agentic",
    )
    return single, agentic, classifier, orchestrator


def _compose_doc(label_map, single_rows, agentic_rows, agentic_cost_rows, orchestrator, sample_size):
    single_metrics = {
        "agreement": agreement(label_map, single_rows),
        "tier": tier_metrics(label_map, single_rows),
        "illegal": illegal_detection_rate(label_map, single_rows),
    }
    agentic_metrics = {
        "agreement": agreement(label_map, agentic_rows),
        "tier": tier_metrics(label_map, agentic_rows),
        "illegal": illegal_detection_rate(label_map, agentic_rows),
    }
    cost = cost_summary(agentic_cost_rows)
    esc_rate = (
        orchestrator._escalated / orchestrator._posts_total
        if orchestrator._posts_total else None
    )
    return render_ab_markdown(
        single=single_metrics, agentic=agentic_metrics, cost=cost,
        escalation_rate=esc_rate, sample_size=sample_size,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="신·구 A/B 정확도·비용 실측 (Story 3-9)")
    parser.add_argument("--limit", type=int, default=None, help="표본 크기(기본 전체)")
    parser.add_argument("--dry-run", action="store_true", help="분류 없이 ground truth 집합만 점검(무비용)")
    args = parser.parse_args(argv)

    from dotenv import load_dotenv

    env_path = PROJECT_ROOT / "infra" / ".env"
    if env_path.exists():
        load_dotenv(env_path)

    if not args.dry_run:
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key or api_key.startswith("sk-REPLACE"):
            sys.exit("[FAIL] OPENAI_API_KEY가 placeholder. --dry-run으로 집합만 점검하거나 키 설정.")

    from detection.src.config.db_config import close_pool, get_pool

    try:
        pool = get_pool()
        truth_rows = fetch_ground_truth(pool, limit=args.limit)
        label_map = build_label_map(truth_rows)
        post_ids = [r["post_id"] for r in truth_rows if r["post_id"] in label_map]
        print(f"[INFO] ground truth judgeable 게시글: {len(post_ids)}건 (unknown 제외)")
        if not post_ids:
            print("[INFO] 라벨된 게시글 0건 — label_detections.py로 먼저 라벨 수집 필요.")
            return 0
        if args.dry_run:
            from collections import Counter
            by_label = Counter(label_map.values())
            print("[DRY-RUN] human_label 분포:")
            for label, n in by_label.most_common():
                print(f"  - {label}: {n}")
            print("[DRY-RUN] 실 분류·비용 없이 종료. 실행하려면 --dry-run 제거.")
            return 0

        single, agentic, classifier, orchestrator = _build_pipelines(pool)
        single_mv = classifier.model_version
        agentic_mv = orchestrator.model_version
        print(f"[INFO] single model_version  = {single_mv}")
        print(f"[INFO] agentic model_version = {agentic_mv}")

        failures = 0
        for i, row in enumerate(truth_rows, start=1):
            if row["post_id"] not in label_map:
                continue
            event = _build_event(row)
            msg = event.to_json()
            try:
                single.process(msg)
                agentic.process(msg)
            except Exception as exc:  # noqa: BLE001 - 단건 실패가 유료 실행 전체를 중단시키지 않도록 격리
                failures += 1
                print(f"[WARN] post_id={row['post_id']} 재분류 실패 — 건너뜀: {exc!r}")
                continue
            if i % 10 == 0:
                print(f"[INFO] {i}/{len(truth_rows)} 재분류 — "
                      f"escalation율 {orchestrator._escalated}/{orchestrator._posts_total}")
        if failures:
            print(f"[WARN] 재분류 실패 {failures}건 — 메트릭은 성공분만 집계.")

        single_rows = fetch_mode_detections(pool, post_ids, single_mv)
        agentic_rows = fetch_mode_detections(pool, post_ids, agentic_mv)
        # 이미지 유/무: post_images 존재 여부(원본 첨부 기준) — 비용 그룹화.
        has_image = {r["post_id"]: bool(r.get("image_urls") or r.get("s3_image_paths")) for r in truth_rows}
        agentic_cost_rows = [
            {"post_id": r["post_id"], "cost_usd": float(r["cost_usd"] or 0.0),
             "has_image": has_image.get(r["post_id"], False)}
            for r in agentic_rows
        ]

        doc = _compose_doc(label_map, single_rows, agentic_rows, agentic_cost_rows,
                           orchestrator, len(post_ids))
        DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
        DOC_PATH.write_text(doc, encoding="utf-8")
        print(f"\n[DONE] A/B 비교표 작성 → {DOC_PATH}")
        print(f"  single agreement={agreement(label_map, single_rows)['agreement']:.3f} "
              f"agentic agreement={agreement(label_map, agentic_rows)['agreement']:.3f}")
        cs = cost_summary(agentic_cost_rows)["all"]
        if cs["mean"] is not None:
            print(f"  agentic 평균 비용=${cs['mean']:.5f} p95=${cs['p95']:.5f} "
                  f"(PRD 평균 ≤$0.005 · p95 ≤$0.02)")
        return 0
    finally:
        close_pool()


if __name__ == "__main__":
    raise SystemExit(main())
