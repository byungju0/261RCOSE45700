"""1건의 CrawlEvent를 Redis `posts:queue`에 LPUSH 한다 (Story 3-3 AC #10 smoke).

Usage:
    python detection/scripts/seed_one_post.py [--text "본문"] [--post-id custom_id]
"""

from __future__ import annotations

import argparse
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

import redis
from shared.config.redis_config import (
    REDIS_KEY_POSTS_QUEUE,
    REDIS_MQ_DB,
    get_redis_url,
    redis_auth_kwargs,
)
from shared.models.crawl_event import CrawlEvent


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", default="리니지M 핵 팝니다. 즉시 사용 가능. 텔레그램 @hack_seller_test")
    parser.add_argument("--post-id", default="smoke_3_3_001")
    parser.add_argument("--language", default="ko")
    args = parser.parse_args()

    event = CrawlEvent(
        post_id=args.post_id,
        source_id="smoke",
        site_name="Story 3-3 smoke",
        raw_text=args.text,
        language=args.language,
        detected_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        correlation_id=f"smoke-{args.post_id}",
    )

    url = get_redis_url()
    client = redis.from_url(
        url, db=REDIS_MQ_DB, decode_responses=True, **redis_auth_kwargs(url)
    )
    client.lpush(REDIS_KEY_POSTS_QUEUE, event.to_json())
    length = client.llen(REDIS_KEY_POSTS_QUEUE)
    print(f"[OK] posts:queue LPUSH — post_id={args.post_id} length={length}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
