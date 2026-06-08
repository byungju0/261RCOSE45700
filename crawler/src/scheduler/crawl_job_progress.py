from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime

import redis

from shared.config.redis_config import REDIS_KEY_CRAWL_JOB_PREFIX, REDIS_KEY_CRAWL_STATS_LATEST

_JOB_TTL_SECONDS = 6 * 60 * 60


@dataclass(frozen=True)
class CrawlTriggerCommand:
    job_id: str
    correlation_id: str
    requested_at: str = ""


def parse_trigger_command(payload: str) -> CrawlTriggerCommand:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return CrawlTriggerCommand(job_id="", correlation_id=payload)

    if not isinstance(data, dict):
        return CrawlTriggerCommand(job_id="", correlation_id=payload)

    return CrawlTriggerCommand(
        job_id=str(data.get("jobId") or ""),
        correlation_id=str(data.get("correlationId") or ""),
        requested_at=str(data.get("requestedAt") or ""),
    )


class CrawlJobProgressStore:
    def __init__(self, redis_client: redis.Redis) -> None:
        self._redis = redis_client

    def mark_running(self, job_id: str, *, total_sites: int) -> None:
        now = _now()
        self._update(
            job_id,
            status="running",
            totalSites=str(total_sites),
            completedSites="0",
            percent="0",
            currentSite="",
            message="크롤링 시작",
            startedAt=now,
            updatedAt=now,
        )

    def mark_site_running(
        self,
        job_id: str,
        *,
        site_id: str,
        completed_sites: int,
        total_sites: int,
    ) -> None:
        self._update(
            job_id,
            status="running",
            completedSites=str(completed_sites),
            totalSites=str(total_sites),
            percent=str(_percent(completed_sites, total_sites)),
            currentSite=site_id,
            message=f"{site_id} 처리 중",
            updatedAt=_now(),
        )

    def mark_site_complete(
        self,
        job_id: str,
        *,
        site_id: str,
        completed_sites: int,
        total_sites: int,
    ) -> None:
        self._update(
            job_id,
            status="running",
            completedSites=str(completed_sites),
            totalSites=str(total_sites),
            percent=str(_percent(completed_sites, total_sites)),
            currentSite=site_id,
            message=f"{site_id} 완료",
            updatedAt=_now(),
        )

    def mark_succeeded(self, job_id: str) -> None:
        now = _now()
        self._update(
            job_id,
            status="succeeded",
            percent="100",
            currentSite="",
            message="크롤링 완료",
            updatedAt=now,
            finishedAt=now,
        )

    def mark_failed(self, job_id: str, *, message: str) -> None:
        now = _now()
        self._update(
            job_id,
            status="failed",
            message=message,
            updatedAt=now,
            finishedAt=now,
        )

    def mark_skipped(self, job_id: str, *, message: str) -> None:
        now = _now()
        self._update(
            job_id,
            status="skipped",
            message=message,
            updatedAt=now,
            finishedAt=now,
        )

    def store_pipeline_stats(self, stats: dict[str, int | str]) -> None:
        """파이프라인 완료 후 funnel 통계를 Redis에 저장. GET /api/crawl/stats 에서 읽는다."""
        data = {**stats, "recordedAt": stats.get("recordedAt") or _now()}
        self._redis.set(REDIS_KEY_CRAWL_STATS_LATEST, json.dumps(data), ex=_JOB_TTL_SECONDS * 7)

    def _update(self, job_id: str, **fields: str) -> None:
        if not job_id:
            return
        key = f"{REDIS_KEY_CRAWL_JOB_PREFIX}{job_id}"
        self._redis.hset(key, mapping=fields)
        self._redis.expire(key, _JOB_TTL_SECONDS)


def _percent(completed_sites: int, total_sites: int) -> int:
    if total_sites <= 0:
        return 0
    return min(100, round((completed_sites / total_sites) * 100))


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
