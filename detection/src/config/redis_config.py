from __future__ import annotations

import redis

from shared.config.redis_config import (
    REDIS_MQ_DB,
    REDIS_RATELIMIT_DB,
    get_redis_url,
    redis_auth_kwargs,
)


def get_mq_client() -> redis.Redis:
    url = get_redis_url()
    return redis.from_url(
        url, db=REDIS_MQ_DB, decode_responses=True, **redis_auth_kwargs(url)
    )


def get_rate_limit_client() -> redis.Redis:
    url = get_redis_url()
    return redis.from_url(
        url, db=REDIS_RATELIMIT_DB, decode_responses=True, **redis_auth_kwargs(url)
    )
