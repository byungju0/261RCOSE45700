"""Redis 없이 candidate inventory JSONL dry-run 을 1회 실행한다.

사용:
    cd /Users/jmac/Desktop/261RCOSE45700/crawler
    CRAWL_DRY_RUN=1 CRAWL_DRY_RUN_OUTPUT_DIR=../output \
    CRAWL4_AI_BASE_DIRECTORY=../output/_crawl4ai_home \
      ../.venv/bin/python scripts/dry_run_inventory.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_REPO_ROOT = _PROJECT_ROOT.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# crawl_scheduler 는 import 시점에 CRAWL_DRY_RUN 값을 읽는다.
os.environ.setdefault("CRAWL_DRY_RUN", "1")
os.environ.setdefault("CRAWL_DRY_RUN_OUTPUT_DIR", str(_REPO_ROOT / "output"))

from crawler.src.crawl4ai_crawler import Crawl4AICrawler  # noqa: E402
from crawler.src.preprocessor.dedup_checker import DedupChecker  # noqa: E402
from crawler.src.queue.redis_publisher import RedisPublisher  # noqa: E402
from crawler.src.scheduler.crawl_scheduler import CrawlPipeline  # noqa: E402
from crawler.src.storage import PostStorage  # noqa: E402


class _NoopRedis:
    def sismember(self, *args, **kwargs) -> int:
        return 0

    def sadd(self, *args, **kwargs) -> int:
        return 1

    def lpush(self, *args, **kwargs) -> int:
        return 1


def _latest_dry_run_file(output_dir: Path) -> Path | None:
    files = list(output_dir.glob("dry_run_*.jsonl"))
    if not files:
        return None
    return max(files, key=lambda p: p.stat().st_mtime)


def _print_inventory_summary(path: Path) -> None:
    per_source = defaultdict(lambda: Counter())
    per_bucket = Counter()
    total = Counter()

    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            row = json.loads(line)
            source = row["site_id"]
            bucket = row.get("priority_bucket", "P?")
            selected = bool(row.get("selected"))

            per_source[source]["discovered"] += 1
            per_source[source]["selected"] += int(selected)
            per_source[source]["keyword_matched"] += int(row.get("keyword_matched", False))
            per_source[source]["has_title_keywords"] += int(row.get("has_title_keywords", False))
            per_source[source][f"bucket_{bucket}"] += 1
            per_bucket[bucket] += 1

            total["discovered"] += 1
            total["selected"] += int(selected)
            total["keyword_matched"] += int(row.get("keyword_matched", False))

    print(f"dry-run JSONL: {path}")
    print(
        "priority buckets: "
        + " ".join(f"{bucket}={per_bucket[bucket]}" for bucket in sorted(per_bucket))
    )
    print("source summary:")
    print(
        f"{'site':<28} {'total':>6} {'sel':>5} {'kw':>4} "
        f"{'P0':>4} {'P1':>4} {'P2':>4} {'P3':>4}"
    )
    for source, counts in sorted(
        per_source.items(),
        key=lambda item: (-item[1]["discovered"], item[0]),
    ):
        print(
            f"{source:<28} {counts['discovered']:>6} {counts['selected']:>5} "
            f"{counts['keyword_matched']:>4} {counts['bucket_P0']:>4} "
            f"{counts['bucket_P1']:>4} {counts['bucket_P2']:>4} "
            f"{counts['bucket_P3']:>4}"
        )
    print(
        "summary: "
        f"discovered={total['discovered']} "
        f"selected={total['selected']} "
        f"kw_matched={total['keyword_matched']}"
    )


async def main() -> None:
    noop_redis = _NoopRedis()
    pipeline = CrawlPipeline(
        crawler=Crawl4AICrawler(headless=True, output_dir="output/_tmp"),
        storage=PostStorage(),
        dedup=DedupChecker(noop_redis),
        publisher=RedisPublisher(noop_redis),
    )
    stats = await pipeline.run()
    print(
        "dry-run 완료: "
        f"boards={stats.listing_boards} "
        f"discovered={stats.listing_discovered_total} "
        f"selected={stats.listing_urls_selected} "
        f"P0={stats.selected_p0} "
        f"P1={stats.selected_p1} "
        f"P2={stats.selected_p2} "
        f"P3={stats.selected_p3} "
        f"kw_matched={stats.listing_keyword_matched} "
        f"kw_unmatched={stats.listing_keyword_unmatched}"
    )
    output_dir = Path(os.environ["CRAWL_DRY_RUN_OUTPUT_DIR"])
    latest = _latest_dry_run_file(output_dir)
    if latest is not None:
        _print_inventory_summary(latest)


if __name__ == "__main__":
    asyncio.run(main())
