from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime

import redis

from shared.config.redis_config import (
    REDIS_KEY_CRAWL_JOB_PREFIX,
    REDIS_KEY_CRAWL_SOURCE_RUN_PREFIX,
    REDIS_KEY_CRAWL_STATS_LATEST,
    REDIS_KEY_CRAWLER_QUIET,
    REDIS_KEY_CRAWLER_RUNNING,
)

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

    def store_source_run(self, site_id: str, stats: dict[str, int | str]) -> None:
        """source별 마지막 크롤 시도 요약. GET /api/stats 의 Source health 에서 읽는다."""
        if not site_id:
            return
        data = {**stats, "siteName": site_id, "lastCheckedAt": stats.get("lastCheckedAt") or _now()}
        self._redis.set(
            f"{REDIS_KEY_CRAWL_SOURCE_RUN_PREFIX}{site_id}",
            json.dumps(data),
            ex=_JOB_TTL_SECONDS * 7,
        )

    def set_running(self, trigger: str = "schedule") -> None:
        """크롤링 시작 시 호출. deploy.yml 사전 drain 체크에서 이 key를 폴링한다.

        trigger: "manual" | "schedule" — 값 자체에 트리거 종류를 저장해 API가
        구분해서 보여줄 수 있게 한다. deploy.yml 은 값 유무만 보므로 호환된다.
        """
        self._redis.set(REDIS_KEY_CRAWLER_RUNNING, trigger, ex=3600)

    def clear_running(self) -> None:
        self._redis.delete(REDIS_KEY_CRAWLER_RUNNING)

    def is_quiet(self) -> bool:
        """배포 drain 중 새 크롤 사이클 시작을 막기 위한 gate."""
        return bool(self._redis.get(REDIS_KEY_CRAWLER_QUIET))

    def cleanup_orphaned_jobs(self) -> int:
        """컨테이너 재시작 전에 running/queued 상태로 남은 job을 failed로 마킹.

        정상 종료 시에는 mark_succeeded/mark_failed가 먼저 호출되므로 idempotent.
        """
        count = 0
        now = _now()
        for key in self._redis.scan_iter(f"{REDIS_KEY_CRAWL_JOB_PREFIX}*"):
            status = self._redis.hget(key, "status")
            if status in ("running", "queued"):
                self._redis.hset(
                    key,
                    mapping={
                        "status": "failed",
                        "message": "컨테이너 재시작으로 중단됨",
                        "updatedAt": now,
                        "finishedAt": now,
                    },
                )
                count += 1
        return count

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
