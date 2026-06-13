from __future__ import annotations

import os
from urllib.parse import urlsplit

REDIS_MQ_DB: int = 0
REDIS_DEDUP_DB: int = 1
REDIS_RATELIMIT_DB: int = 2
REDIS_CACHE_DB: int = 3

REDIS_KEY_POSTS_QUEUE: str = "posts:queue"
REDIS_KEY_POSTS_PROCESSING: str = "posts:processing"
REDIS_KEY_POSTS_DLQ: str = "posts:dlq"
REDIS_KEY_POSTS_CORRUPT: str = "posts:corrupt"
REDIS_KEY_POSTS_DEDUP: str = "posts:dedup"
REDIS_KEY_SEEN_URLS: str = "posts:seen_urls"

# Story 3-7 — LinkTracer 1-hop fetch 결과 캐시 (DB1, TTL 7일). 키 = prefix + sha256(url).
REDIS_KEY_LINKTRACE_PREFIX: str = "linktrace:"

# 2026-05-27 PIVOT — OpenAI 멀티모달 LLM 단일 호출 rate limit key.
REDIS_KEY_LLM_RATE_LIMIT_CLASSIFY: str = "llm:rate_limit:classify"

REDIS_CHANNEL_CRAWL_TRIGGER: str = "crawl:trigger"
REDIS_KEY_CRAWL_JOB_PREFIX: str = "crawl:jobs:"
REDIS_KEY_CRAWL_STATS_LATEST: str = "crawl:stats:latest"
REDIS_KEY_CRAWL_SOURCE_RUN_PREFIX: str = "crawl:source_runs:"
REDIS_KEY_CRAWLER_RUNNING: str = "crawler:running"


def get_redis_url() -> str:
    return os.environ.get("REDIS_URL", "redis://localhost:6379")


def redis_auth_kwargs(url: str | None = None) -> dict[str, str]:
    """Use REDIS_PASSWORD unless credentials are already embedded in REDIS_URL."""
    redis_url = url or get_redis_url()
    password = os.environ.get("REDIS_PASSWORD", "")
    if not password:
        return {}
    if urlsplit(redis_url).password is not None:
        return {}
    return {"password": password}
