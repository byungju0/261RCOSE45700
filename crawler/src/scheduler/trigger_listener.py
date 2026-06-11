from __future__ import annotations

import asyncio
import contextlib
import os
from collections.abc import Callable, Coroutine
from typing import Any

import redis.asyncio as aioredis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import TimeoutError as RedisTimeoutError

from crawler.src.scheduler.crawl_job_progress import (
    CrawlTriggerCommand,
    parse_trigger_command,
)
from shared.config.redis_config import (
    REDIS_CHANNEL_CRAWL_TRIGGER,
    REDIS_MQ_DB,
    redis_auth_kwargs,
)
from shared.correlation_id import generate
from shared.structured_logger import get_logger

_SERVICE_NAME = os.environ.get("SERVICE_NAME", "crawler")
_logger = get_logger(__name__)
_RECONNECT_BACKOFF_SECONDS = 5.0
TRIGGER_LISTENER_HEARTBEAT_KEY = "crawler:trigger_listener:heartbeat"
_HEARTBEAT_INTERVAL_SECONDS = 15
_HEARTBEAT_TTL_SECONDS = 45


class TriggerListener:
    """Redis pub/sub crawl:trigger 채널 구독 → 수동 크롤링 즉시 실행."""

    def __init__(
        self,
        redis_url: str,
        pipeline_fn: Callable[[CrawlTriggerCommand], Coroutine[Any, Any, Any]],
    ) -> None:
        self._redis_url = redis_url
        self._run_pipeline = pipeline_fn

    async def listen(self) -> None:
        while True:
            try:
                async with aioredis.from_url(
                    self._redis_url,
                    db=REDIS_MQ_DB,
                    decode_responses=True,
                    socket_timeout=None,
                    socket_connect_timeout=5,
                    health_check_interval=30,
                    **redis_auth_kwargs(self._redis_url),
                ) as client:
                    async with client.pubsub() as pubsub:
                        await pubsub.subscribe(REDIS_CHANNEL_CRAWL_TRIGGER)
                        _logger.info(
                            "%s 채널 구독 시작", REDIS_CHANNEL_CRAWL_TRIGGER,
                            extra={"correlation_id": "", "service": _SERVICE_NAME},
                        )
                        heartbeat_task = asyncio.create_task(
                            self._heartbeat(client)
                        )
                        try:
                            async for message in pubsub.listen():
                                if message.get("type") != "message":
                                    continue
                                command = parse_trigger_command(str(message.get("data") or ""))
                                cid = command.correlation_id or generate()
                                _logger.info(
                                    "수동 트리거 수신 — 즉시 크롤링 시작",
                                    extra={
                                        "correlation_id": cid,
                                        "service": _SERVICE_NAME,
                                        "job_id": command.job_id,
                                    },
                                )
                                try:
                                    await self._run_pipeline(command)
                                except Exception as exc:
                                    _logger.error(
                                        "수동 트리거 파이프라인 실행 실패: %s", exc,
                                        extra={"correlation_id": cid, "service": _SERVICE_NAME},
                                        exc_info=True,
                                    )
                        finally:
                            heartbeat_task.cancel()
                            with contextlib.suppress(asyncio.CancelledError):
                                await heartbeat_task
            except (RedisConnectionError, RedisTimeoutError, OSError) as exc:
                _logger.warning(
                    "pubsub 연결 끊김 — %.1fs 후 재연결: %s", _RECONNECT_BACKOFF_SECONDS, exc,
                    extra={"correlation_id": "", "service": _SERVICE_NAME},
                )
                await asyncio.sleep(_RECONNECT_BACKOFF_SECONDS)

    async def _heartbeat(self, client: aioredis.Redis) -> None:
        while True:
            await client.setex(
                TRIGGER_LISTENER_HEARTBEAT_KEY,
                _HEARTBEAT_TTL_SECONDS,
                "1",
            )
            await asyncio.sleep(_HEARTBEAT_INTERVAL_SECONDS)
