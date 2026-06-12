from __future__ import annotations

import os

import redis

from shared.config.redis_config import (
    REDIS_DEDUP_DB,
    REDIS_MQ_DB,
    REDIS_RATELIMIT_DB,
    get_redis_url,
    redis_auth_kwargs,
)


def _mq_socket_timeout_sec() -> float:
    block_timeout_sec = float(os.environ.get("BRPOPLPUSH_TIMEOUT", "30"))
    return float(
        os.environ.get("REDIS_MQ_SOCKET_TIMEOUT_SEC", str(block_timeout_sec + 10))
    )


def get_mq_client() -> redis.Redis:
    url = get_redis_url()
    return redis.from_url(
        url,
        db=REDIS_MQ_DB,
        decode_responses=True,
        socket_timeout=_mq_socket_timeout_sec(),
        socket_connect_timeout=5,
        health_check_interval=30,
        **redis_auth_kwargs(url),
    )


def get_rate_limit_client() -> redis.Redis:
    url = get_redis_url()
    return redis.from_url(
        url, db=REDIS_RATELIMIT_DB, decode_responses=True, **redis_auth_kwargs(url)
    )


def get_dedup_client() -> redis.Redis:
    """링크 추적 캐시(linktrace:*) 등에 쓰는 DB1 클라이언트 (Story 3-7)."""
    url = get_redis_url()
    return redis.from_url(
        url, db=REDIS_DEDUP_DB, decode_responses=True, **redis_auth_kwargs(url)
    )
