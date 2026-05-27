from __future__ import annotations

import os
import traceback
from collections.abc import Callable
from typing import TYPE_CHECKING

import redis

from shared.config.redis_config import (
    REDIS_KEY_POSTS_PROCESSING,
    REDIS_KEY_POSTS_QUEUE,
)
from shared.models.crawl_event import CrawlEvent
from shared.structured_logger import get_logger

from detection.src.consumer.watchdog import processing_time_key, retry_key

if TYPE_CHECKING:
    from detection.src.consumer.watchdog import Watchdog

_SERVICE_NAME = os.environ.get("SERVICE_NAME", "detection")
_BRPOPLPUSH_TIMEOUT = int(os.environ.get("BRPOPLPUSH_TIMEOUT", "30"))
_logger = get_logger(__name__)


class QueueConsumer:
    def __init__(
        self,
        redis_client: redis.Redis,
        process_fn: Callable[[str], None],
        watchdog: "Watchdog | None" = None,
    ) -> None:
        self._redis = redis_client
        self._process = process_fn
        self._watchdog = watchdog

    def run_once(self) -> bool:
        """단일 메시지 소비 시도. 메시지 있으면 True, timeout이면 False 반환."""
        message: str | None = self._redis.brpoplpush(
            REDIS_KEY_POSTS_QUEUE,
            REDIS_KEY_POSTS_PROCESSING,
            timeout=_BRPOPLPUSH_TIMEOUT,
        )
        if message is None:
            return False

        if self._watchdog is not None:
            self._watchdog.mark_processing(message)

        # CrawlEvent 파싱은 best-effort — 실패 시 빈 cid + 키 cleanup 스킵
        # 손상 메시지는 _process에서 실패 → posts:processing 잔류 → Watchdog corrupt-DLQ 격리
        correlation_id = ""
        post_id: str | None = None
        try:
            event = CrawlEvent.from_json(message)
            correlation_id = event.correlation_id
            post_id = event.post_id
        except Exception:
            pass

        try:
            self._process(message)
            self._redis.lrem(REDIS_KEY_POSTS_PROCESSING, 1, message)
            if post_id is not None:
                self._redis.delete(retry_key(post_id))
                self._redis.delete(processing_time_key(post_id))
            _logger.info(
                "메시지 처리 완료",
                extra={"correlation_id": correlation_id, "service": _SERVICE_NAME},
            )
        except Exception as exc:
            _logger.error(
                "메시지 처리 실패 — posts:processing 잔류: %s\ntraceback:\n%s",
                exc, traceback.format_exc(),
                extra={"correlation_id": correlation_id, "service": _SERVICE_NAME},
            )
            # LREM 호출하지 않음 — Watchdog이 stale 감지 후 재투입

        return True

    def run_forever(self) -> None:
        _logger.info(
            "QueueConsumer 시작",
            extra={"correlation_id": "", "service": _SERVICE_NAME},
        )
        while True:
            self.run_once()
