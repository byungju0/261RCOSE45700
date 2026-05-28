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

# 2026-05-27 PIVOT — OpenAI 멀티모달 LLM 단일 호출 rate limit key.
REDIS_KEY_LLM_RATE_LIMIT_CLASSIFY: str = "llm:rate_limit:classify"

REDIS_CHANNEL_CRAWL_TRIGGER: str = "crawl:trigger"
REDIS_KEY_CRAWL_JOB_PREFIX: str = "crawl:jobs:"
