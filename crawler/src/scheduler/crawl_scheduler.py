"""APScheduler 기반 크롤링 파이프라인 + 수동 트리거 진입점."""
from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass

import redis
from apscheduler.events import EVENT_JOB_MISSED
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
from crawl4ai.async_configs import CacheMode

from crawler.src.crawl4ai_crawler import Crawl4AICrawler
from crawler.src.preprocessor import language_detector
from crawler.src.preprocessor.dedup_checker import DedupChecker
from crawler.src.preprocessor.serializer import to_crawl_event
from crawler.src.queue.redis_publisher import RedisPublisher
from crawler.src.scheduler.trigger_listener import TriggerListener
from crawler.src.sites.registry import get_enabled_sites
from crawler.src.storage import PostStorage
from shared.config.redis_config import REDIS_DEDUP_DB, REDIS_MQ_DB
from shared.correlation_id import generate
from shared.structured_logger import get_logger

_SERVICE_NAME = os.environ.get("SERVICE_NAME", "crawler")
_logger = get_logger(__name__)
_MAX_POSTS_PER_BOARD = int(os.environ.get("MAX_POSTS_PER_BOARD", "10"))


async def _fetch_post_urls(
    board_url: str, pattern: str, limit: int, *, correlation_id: str = ""
) -> list[str]:
    """게시판 목록 페이지에서 게시글 URL 추출 (stealth 브라우저 + 링크 파싱)."""
    cfg = BrowserConfig(headless=True, enable_stealth=True, verbose=False)
    run = CrawlerRunConfig(cache_mode=CacheMode.BYPASS, page_timeout=20_000)
    try:
        async with AsyncWebCrawler(config=cfg) as crawler:
            result = await crawler.arun(board_url, config=run)
    except Exception as exc:
        _logger.warning(
            "게시판 목록 크롤 예외: %s — %s", board_url, exc,
            extra={"correlation_id": correlation_id, "service": _SERVICE_NAME},
            exc_info=True,
        )
        return []
    if not result.success:
        _logger.warning(
            "게시판 목록 크롤 실패: %s", board_url,
            extra={"correlation_id": correlation_id, "service": _SERVICE_NAME},
        )
        return []
    all_links = (result.links.get("internal") or []) + (result.links.get("external") or [])
    seen: set[str] = set()
    post_urls: list[str] = []
    compiled = re.compile(pattern)
    for link in all_links:
        href = (link.get("href") or "").split("?")[0]
        if compiled.match(href) and href not in seen:
            seen.add(href)
            post_urls.append(href)

    # 고정(공지) 게시글이 상단에 오는 게시판 대응: URL의 마지막 숫자 시퀀스를 post_id로 삼아 내림차순 정렬
    def _url_sort_key(u: str) -> int:
        matches = re.findall(r"/(\d+)", u)
        return int(matches[-1]) if matches else 0

    post_urls.sort(key=_url_sort_key, reverse=True)
    return post_urls[:limit]


@dataclass
class PipelineStats:
    attempted: int = 0
    enqueued: int = 0
    skipped_dedup: int = 0
    skipped_empty: int = 0
    failed: int = 0

    @property
    def success_rate(self) -> float:
        if self.attempted == 0:
            return 1.0
        return (self.attempted - self.failed) / self.attempted


class CrawlPipeline:
    """크롤링 → 전처리 → Redis enqueue 파이프라인."""

    def __init__(
        self,
        crawler: Crawl4AICrawler,
        storage: PostStorage,
        dedup: DedupChecker,
        publisher: RedisPublisher,
    ) -> None:
        self._crawler = crawler
        self._storage = storage
        self._dedup = dedup
        self._publisher = publisher

    async def run(self) -> PipelineStats:
        stats = PipelineStats()
        sites = get_enabled_sites()
        _logger.info(
            "파이프라인 시작: 활성 사이트 %d개", len(sites),
            extra={"correlation_id": "", "service": _SERVICE_NAME},
        )

        for site_id, site in sites.items():
            for board_url in site.board_urls:
                board_cid = generate()
                post_urls = await _fetch_post_urls(
                    board_url, site.post_url_pattern, _MAX_POSTS_PER_BOARD,
                    correlation_id=board_cid,
                )
                for post_url in post_urls:
                    stats.attempted += 1
                    cid = generate()
                    try:
                        result = await self._crawler.fetch(
                            post_url,
                            correlation_id=cid,
                            image_filter=site.image_filter,
                            css_selector=site.css_selector,
                        )
                        if not (result.fit_markdown or "").strip():
                            stats.skipped_empty += 1
                            _logger.warning(
                                "빈 게시글 스킵: %s", post_url,
                                extra={"correlation_id": cid, "service": _SERVICE_NAME},
                            )
                            continue
                        if self._dedup.is_duplicate(result.fit_markdown, correlation_id=cid):
                            stats.skipped_dedup += 1
                            continue
                        language = language_detector.detect(result.fit_markdown, correlation_id=cid)
                        post_id = site.post_id_extractor(post_url)
                        storage_result = self._storage.save(
                            site_id=site_id,
                            post_id=post_id,
                            url=post_url,
                            result=result,
                            correlation_id=cid,
                        )
                        event = to_crawl_event(
                            result,
                            site_id=site_id,
                            site=site,
                            url=post_url,
                            language=language,
                            correlation_id=cid,
                            s3_text_path=storage_result.s3_text_path,
                            s3_image_paths=storage_result.s3_image_paths,
                        )
                        self._publisher.enqueue(event.to_json(), correlation_id=cid)
                        stats.enqueued += 1
                    except Exception as exc:
                        stats.failed += 1
                        _logger.error(
                            "게시글 처리 실패: %s — %s", post_url, exc,
                            extra={"correlation_id": cid, "service": _SERVICE_NAME},
                            exc_info=True,
                        )
                        continue
                    # LPUSH 성공 후 mark_seen — 실패해도 enqueued는 유지(다음 run에서 재발행 허용)
                    try:
                        self._dedup.mark_seen(result.fit_markdown, correlation_id=cid)
                    except Exception as exc:
                        _logger.warning(
                            "dedup mark_seen 실패 (큐에는 이미 발행됨): %s — %s", post_url, exc,
                            extra={"correlation_id": cid, "service": _SERVICE_NAME},
                            exc_info=True,
                        )

        _logger.info(
            "파이프라인 완료: 시도=%d 큐=%d 중복제외=%d 빈게시글=%d 실패=%d",
            stats.attempted,
            stats.enqueued,
            stats.skipped_dedup,
            stats.skipped_empty,
            stats.failed,
            extra={"correlation_id": "", "service": _SERVICE_NAME},
        )
        return stats


class CrawlScheduler:
    """APScheduler + TriggerListener 통합 스케줄러."""

    def __init__(self) -> None:
        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
        mq_client = redis.from_url(redis_url, db=REDIS_MQ_DB, decode_responses=True)
        dedup_client = redis.from_url(redis_url, db=REDIS_DEDUP_DB, decode_responses=True)

        self._pipeline = CrawlPipeline(
            crawler=Crawl4AICrawler(headless=True, output_dir="output/_tmp"),
            storage=PostStorage(),
            dedup=DedupChecker(dedup_client),
            publisher=RedisPublisher(mq_client),
        )
        # scheduled run + 수동 trigger 동시 실행 방지
        self._run_lock = asyncio.Lock()
        self._trigger_listener = TriggerListener(redis_url, self._run_locked)
        self._scheduler = AsyncIOScheduler()

    async def _run_locked(self) -> None:
        # APScheduler 잡 + 수동 trigger 양쪽에서 호출되는 단일 진입점.
        if self._run_lock.locked():
            _logger.info(
                "이미 실행 중 — 이번 호출 스킵",
                extra={"correlation_id": "", "service": _SERVICE_NAME},
            )
            return
        async with self._run_lock:
            await self._pipeline.run()

    def _on_job_missed(self, event) -> None:
        _logger.warning(
            "scheduler_job_missed",
            extra={
                "correlation_id": "",
                "service": _SERVICE_NAME,
                "job_id": event.job_id,
                "scheduled_run_time": str(event.scheduled_run_time),
            },
        )

    def setup_schedule(self) -> None:
        interval = int(os.environ.get("CRAWL_INTERVAL_MINUTES", "60"))
        self._scheduler.add_job(
            self._run_locked,
            trigger="interval",
            minutes=interval,
            max_instances=1,
            misfire_grace_time=60,
            id="crawl_pipeline",
            replace_existing=True,
        )
        self._scheduler.add_listener(self._on_job_missed, EVENT_JOB_MISSED)
        _logger.info(
            "APScheduler 등록: %d분 주기", interval,
            extra={"correlation_id": "", "service": _SERVICE_NAME},
        )

    async def run_forever(self) -> None:
        self.setup_schedule()
        self._scheduler.start()
        try:
            await self._trigger_listener.listen()
        finally:
            self._scheduler.shutdown(wait=False)


async def _async_main() -> None:
    scheduler = CrawlScheduler()
    await scheduler.run_forever()


if __name__ == "__main__":
    asyncio.run(_async_main())
