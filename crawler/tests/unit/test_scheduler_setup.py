"""CrawlScheduler.setup_schedule() 잡 등록 검증.

외부 Redis / Playwright 호출 없이 mock 으로 APScheduler 잡 구성만 본다.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from crawler.src.scheduler import crawl_scheduler as scheduler_module
from crawler.src.scheduler.crawl_scheduler import CrawlScheduler


@pytest.fixture
def scheduler_with_mocked_redis():
    """Redis / Playwright 의존성을 mock 한 CrawlScheduler 인스턴스."""
    with patch("crawler.src.scheduler.crawl_scheduler.redis") as mock_redis, \
         patch("crawler.src.scheduler.crawl_scheduler.Crawl4AICrawler"), \
         patch("crawler.src.scheduler.crawl_scheduler.PostStorage"):
        mock_redis.from_url.return_value = MagicMock()
        scheduler = CrawlScheduler()
        scheduler.setup_schedule()
        yield scheduler


class TestSetupScheduleJobsRegistered:
    def test_two_jobs_registered(self, scheduler_with_mocked_redis):
        jobs = scheduler_with_mocked_redis._scheduler.get_jobs()
        job_ids = sorted(j.id for j in jobs)
        assert job_ids == ["crawl_pipeline", "url_dedup_cleanup"]

    def test_crawl_pipeline_is_interval(self, scheduler_with_mocked_redis):
        job = scheduler_with_mocked_redis._scheduler.get_job("crawl_pipeline")
        assert isinstance(job.trigger, IntervalTrigger)

    def test_crawl_pipeline_coalesce_enabled(self, scheduler_with_mocked_redis):
        # 다운타임 복귀 시 적체된 missed run 을 한 번만 실행하는 운영 의도가 명시되어야 함.
        job = scheduler_with_mocked_redis._scheduler.get_job("crawl_pipeline")
        assert job.coalesce is True

    def test_crawl_pipeline_misfire_grace_unchanged(self, scheduler_with_mocked_redis):
        # 기존 운영 가드 회귀 방지 (60s).
        job = scheduler_with_mocked_redis._scheduler.get_job("crawl_pipeline")
        assert job.misfire_grace_time == 60

    def test_cleanup_job_is_cron_03_utc(self, scheduler_with_mocked_redis):
        job = scheduler_with_mocked_redis._scheduler.get_job("url_dedup_cleanup")
        assert isinstance(job.trigger, CronTrigger)
        # CronTrigger 의 fields 는 [year, month, day, week, day_of_week, hour, minute, second].
        fields = {f.name: str(f) for f in job.trigger.fields}
        assert fields["hour"] == "3"
        assert fields["minute"] == "0"
        # TZ 명시 회귀 가드 — EC2 host 가 KST 면 timezone 안 박으면 12시간 어긋남.
        assert str(job.trigger.timezone) == "UTC"

    def test_cleanup_job_misfire_grace_1h(self, scheduler_with_mocked_redis):
        # 일 1회 잡이라 1시간 여유. 1시간 초과 시 EVENT_JOB_MISSED 로 가시화.
        job = scheduler_with_mocked_redis._scheduler.get_job("url_dedup_cleanup")
        assert job.misfire_grace_time == 3600

    def test_cleanup_job_coalesce_enabled(self, scheduler_with_mocked_redis):
        job = scheduler_with_mocked_redis._scheduler.get_job("url_dedup_cleanup")
        assert job.coalesce is True


class TestOperationalDefaults:
    def test_crawler_operational_defaults_match_ec2_profile(self):
        assert scheduler_module._MAX_POSTS_PER_BOARD == 30
        assert scheduler_module._PRIORITY_BUDGET_ENABLED is True
        assert scheduler_module._P3_DEFAULT_CAP_PER_BOARD == 1
        assert scheduler_module._P3_MIXED_CAP_PER_BOARD == 5
        assert scheduler_module._P3_52POJIE_CAP_PER_BOARD == 1
        assert scheduler_module._DETAIL_FETCH_CONCURRENCY == 3
        assert scheduler_module._DETAIL_FETCH_SOURCE_CONCURRENCY == {
            "dcard": 1,
            "dcard_online": 1,
            "52pojie": 1,
        }
        assert scheduler_module._DETAIL_FETCH_STAGGER_SECONDS == 0.25
        assert scheduler_module._DETAIL_CLOUDFLARE_BACKOFF_RETRIES == 0
        assert scheduler_module._DETAIL_CLOUDFLARE_BACKOFF_SECONDS == 0
        assert scheduler_module._DETAIL_SOURCE_COOLDOWN_SECONDS == 0
        assert scheduler_module._DETAIL_CHALLENGE_COOLDOWN_SECONDS == 0
        assert scheduler_module._INTER_SITE_DELAY_SECONDS == 15
        assert scheduler_module._INTER_BOARD_DELAY_SECONDS == 3


class TestCleanupHandler:
    async def test_cleanup_handler_calls_url_dedup(self):
        """_cleanup_url_dedup_job 이 UrlDedupChecker.cleanup_older_than 을 1회 호출."""
        with patch("crawler.src.scheduler.crawl_scheduler.redis") as mock_redis, \
             patch("crawler.src.scheduler.crawl_scheduler.Crawl4AICrawler"), \
             patch("crawler.src.scheduler.crawl_scheduler.PostStorage"):
            mock_redis.from_url.return_value = MagicMock()
            scheduler = CrawlScheduler()

        scheduler._url_dedup = MagicMock()
        scheduler._url_dedup.cleanup_older_than.return_value = 42

        await scheduler._cleanup_url_dedup_job()

        scheduler._url_dedup.cleanup_older_than.assert_called_once_with()


class TestUrlDedupSharedInstance:
    def test_pipeline_and_scheduler_share_url_dedup(self):
        """파이프라인 mark_seen 과 cleanup 잡이 같은 ZSET 을 참조해야 함."""
        with patch("crawler.src.scheduler.crawl_scheduler.redis") as mock_redis, \
             patch("crawler.src.scheduler.crawl_scheduler.Crawl4AICrawler"), \
             patch("crawler.src.scheduler.crawl_scheduler.PostStorage"):
            mock_redis.from_url.return_value = MagicMock()
            scheduler = CrawlScheduler()

        assert scheduler._url_dedup is scheduler._pipeline._url_dedup
