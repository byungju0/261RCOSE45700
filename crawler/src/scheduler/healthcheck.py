from __future__ import annotations

import sys

import redis

from crawler.src.scheduler.trigger_listener import TRIGGER_LISTENER_HEARTBEAT_KEY
from shared.config.redis_config import REDIS_MQ_DB, get_redis_url, redis_auth_kwargs


def main() -> int:
    redis_url = get_redis_url()
    client = redis.from_url(
        redis_url,
        db=REDIS_MQ_DB,
        decode_responses=True,
        socket_connect_timeout=3,
        socket_timeout=3,
        **redis_auth_kwargs(redis_url),
    )
    try:
        if client.get(TRIGGER_LISTENER_HEARTBEAT_KEY) != "1":
            print("trigger listener heartbeat missing", file=sys.stderr)
            return 1
    except redis.RedisError as exc:
        print(f"redis healthcheck failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
