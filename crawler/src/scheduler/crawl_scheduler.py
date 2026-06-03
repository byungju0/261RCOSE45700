"""APScheduler 기반 크롤링 파이프라인 + 수동 트리거 진입점."""
from __future__ import annotations

import asyncio
import os
import random
import re
from collections.abc import Callable
from dataclasses import dataclass

import httpx
import redis
from apscheduler.events import EVENT_JOB_MISSED
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
from crawl4ai.async_configs import CacheMode

from crawler.src.crawl4ai_crawler import Crawl4AICrawler
from crawler.src.preprocessor import content_validator, language_detector
from crawler.src.preprocessor.dedup_checker import DedupChecker
from crawler.src.preprocessor.serializer import to_crawl_event
from crawler.src.preprocessor.url_dedup_checker import UrlDedupChecker
from crawler.src.queue.redis_publisher import RedisPublisher
from crawler.src.scheduler.crawl_job_progress import (
    CrawlJobProgressStore,
    CrawlTriggerCommand,
)
from crawler.src.scheduler.trigger_listener import TriggerListener
from crawler.src.sites.registry import SiteConfig, get_enabled_sites
from crawler.src.storage import PostStorage
from shared.config.redis_config import (
    REDIS_DEDUP_DB,
    REDIS_MQ_DB,
    get_redis_url,
    redis_auth_kwargs,
)
from shared.correlation_id import generate
from shared.structured_logger import get_logger

_SERVICE_NAME = os.environ.get("SERVICE_NAME", "crawler")
_logger = get_logger(__name__)
_MAX_POSTS_PER_BOARD = int(os.environ.get("MAX_POSTS_PER_BOARD", "10"))

# 사이트·보드 간 휴식 — anti-bot rate limit(예: Bahamut ACS-GOTO) 회피용.
# jitter 비율(±25%) 곱해서 인간적 패턴 흉내.
_INTER_SITE_DELAY_SECONDS = float(os.environ.get("INTER_SITE_DELAY_SECONDS", "15"))
_INTER_BOARD_DELAY_SECONDS = float(os.environ.get("INTER_BOARD_DELAY_SECONDS", "3"))


def _jittered(base: float, jitter_ratio: float = 0.25) -> float:
    """base * (1 ± jitter_ratio) 안에서 무작위 값."""
    if base <= 0:
        return 0.0
    return base * (1.0 + random.uniform(-jitter_ratio, jitter_ratio))


@dataclass(frozen=True)
class CrawlOptions:
    cookies: list[dict] | None = None
    wait_for: str | None = None
    headers: dict[str, str] | None = None
    page_timeout: int | None = None
    proxy: dict | None = None
    js_code: list[str] | None = None
    delay_before_return_html: float | None = None
    scan_full_page: bool = False
    scroll_delay: float | None = None
    virtual_scroll_config: dict | None = None
    wait_until: str | None = None
    simulate_user: bool = False
    user_agent_mode: str | None = None
    c4a_script: list[str] | None = None
    exclude_social_media_links: bool = True
    exclude_external_links: bool | None = None
    title_keywords: list[str] | None = None
    css_selector: str | None = None
    image_filter: Callable[[dict], bool] | None = None

    @classmethod
    def from_site(cls, site: SiteConfig) -> "CrawlOptions":
        return cls(
            cookies=site.cookies,
            wait_for=site.wait_for,
            headers=site.headers,
            page_timeout=site.page_timeout,
            proxy=site.proxy,
            js_code=site.js_code,
            delay_before_return_html=site.delay_before_return_html,
            scan_full_page=site.scan_full_page,
            scroll_delay=site.scroll_delay,
            virtual_scroll_config=site.virtual_scroll_config,
            wait_until=site.wait_until,
            simulate_user=site.simulate_user,
            user_agent_mode=site.user_agent_mode,
            c4a_script=site.c4a_script,
            exclude_social_media_links=site.exclude_social_media_links,
            exclude_external_links=site.exclude_external_links,
            title_keywords=site.title_keywords,
            css_selector=site.css_selector,
            image_filter=site.image_filter,
        )

    def browser_kwargs(self) -> dict:
        kwargs: dict = dict(headless=True, enable_stealth=True, verbose=False)
        if self.proxy is not None:
            kwargs["proxy_config"] = self.proxy
        if self.headers is not None:
            kwargs["headers"] = self.headers
        if self.user_agent_mode is not None:
            kwargs["user_agent_mode"] = self.user_agent_mode
        return kwargs

    def listing_run_kwargs(self) -> dict:
        kwargs: dict = dict(
            cache_mode=CacheMode.BYPASS,
            page_timeout=self.page_timeout if self.page_timeout is not None else 20_000,
        )
        if self.wait_for is not None:
            kwargs["wait_for"] = self.wait_for
        if self.js_code is not None:
            kwargs["js_code"] = self.js_code
        if self.delay_before_return_html is not None:
            kwargs["delay_before_return_html"] = self.delay_before_return_html
        if self.scan_full_page:
            kwargs["scan_full_page"] = True
            if self.scroll_delay is not None:
                kwargs["scroll_delay"] = self.scroll_delay
        if self.virtual_scroll_config is not None:
            kwargs["virtual_scroll_config"] = self.virtual_scroll_config
        if self.wait_until is not None:
            kwargs["wait_until"] = self.wait_until
        if self.simulate_user:
            kwargs["simulate_user"] = True
        if self.c4a_script is not None:
            kwargs["c4a_script"] = self.c4a_script
        if self.exclude_social_media_links:
            kwargs["exclude_social_media_links"] = True
        if self.exclude_external_links is not None:
            kwargs["exclude_external_links"] = self.exclude_external_links
        return kwargs

    def arun_kwargs(self, url: str, run: CrawlerRunConfig) -> dict:
        kwargs: dict = {"url": url, "config": run}
        if self.cookies is not None:
            kwargs["cookies"] = self.cookies
        return kwargs

    def fetch_kwargs(self) -> dict:
        return {
            "image_filter": self.image_filter,
            "css_selector": self.css_selector,
            "cookies": self.cookies,
            "wait_for": self.wait_for,
            "headers": self.headers,
            "page_timeout": self.page_timeout,
            "proxy": self.proxy,
            "js_code": self.js_code,
            "delay_before_return_html": self.delay_before_return_html,
            "scan_full_page": self.scan_full_page,
            "scroll_delay": self.scroll_delay,
            "virtual_scroll_config": self.virtual_scroll_config,
            "wait_until": self.wait_until,
            "simulate_user": self.simulate_user,
            "user_agent_mode": self.user_agent_mode,
            "c4a_script": self.c4a_script,
            "exclude_social_media_links": self.exclude_social_media_links,
            "exclude_external_links": self.exclude_external_links,
        }


async def _fetch_post_urls(
    board_url: str,
    pattern: str,
    limit: int,
    *,
    correlation_id: str = "",
    options: CrawlOptions,
) -> list[str]:
    """게시판 목록 페이지에서 게시글 URL 추출 (stealth 브라우저 + 링크 파싱).

    사이트별 옵션(cookies/wait_for/headers/proxy)으로 PTT over18·Dcard SPA·
    Tieba 프록시 등 접근 제어를 통과한다.
    """
    cfg = BrowserConfig(**options.browser_kwargs())
    run = CrawlerRunConfig(**options.listing_run_kwargs())
    arun_kwargs = options.arun_kwargs(board_url, run)

    try:
        async with AsyncWebCrawler(config=cfg) as crawler:
            result = await crawler.arun(**arun_kwargs)
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
    keywords_lower = [k.lower() for k in (options.title_keywords or [])]
    for link in all_links:
        full = (link.get("href") or "")
        href = full.split("?")[0]
        # crawl4ai 가 줄 수 있는 필드: text(앵커 텍스트, 대개 게시글 제목), title, alt
        link_title = (link.get("text") or link.get("title") or "")
        candidate = full if compiled.match(full) else (href if compiled.match(href) else None)
        if not candidate or candidate in seen:
            continue
        if keywords_lower and not any(k in link_title.lower() for k in keywords_lower):
            # 혼합 보드의 비-NC 게시글은 fetch 단계로 보내지 않음.
            continue
        seen.add(candidate)
        post_urls.append(candidate)

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
    skipped_seen_url: int = 0        # cross-run URL dedup: 이미 다른 run 에서 처리됨
    skipped_dedup: int = 0           # 같은 본문 SHA256 중복
    skipped_empty: int = 0
    skipped_sticky: int = 0          # content_validator: 공지/导航/공식 행사 등
    skipped_blocked: int = 0         # auth_wall / captcha / error
    skipped_unknown: int = 0         # 검증자가 사용자 글 마커 못 찾음 (보수적 스킵)
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
        url_dedup: UrlDedupChecker | None = None,
        progress_store: CrawlJobProgressStore | None = None,
    ) -> None:
        self._crawler = crawler
        self._storage = storage
        self._dedup = dedup
        self._publisher = publisher
        # 옵션. None 이면 cross-run URL 체크 안 함 (단위 테스트 호환).
        self._url_dedup = url_dedup
        self._progress_store = progress_store

    async def run(self, *, job_id: str = "") -> PipelineStats:
        stats = PipelineStats()
        sites = get_enabled_sites()
        total_sites = len(sites)
        if self._progress_store is not None and job_id:
            self._progress_store.mark_running(job_id, total_sites=total_sites)
        _logger.info(
            "파이프라인 시작: 활성 사이트 %d개 (site_delay=%.1fs board_delay=%.1fs)",
            len(sites), _INTER_SITE_DELAY_SECONDS, _INTER_BOARD_DELAY_SECONDS,
            extra={"correlation_id": "", "service": _SERVICE_NAME},
        )

        site_items = list(sites.items())
        for site_idx, (site_id, site) in enumerate(site_items):
            await self._process_site(
                stats,
                site_id=site_id,
                site=site,
                site_idx=site_idx,
                total_sites=total_sites,
                job_id=job_id,
            )

        _logger.info(
            "파이프라인 완료: 시도=%d 큐=%d url중복=%d 본문중복=%d 빈=%d 공지=%d 차단=%d 미확인=%d 실패=%d",
            stats.attempted,
            stats.enqueued,
            stats.skipped_seen_url,
            stats.skipped_dedup,
            stats.skipped_empty,
            stats.skipped_sticky,
            stats.skipped_blocked,
            stats.skipped_unknown,
            stats.failed,
            extra={"correlation_id": "", "service": _SERVICE_NAME},
        )
        return stats

    async def _process_site(
        self,
        stats: PipelineStats,
        *,
        site_id: str,
        site: SiteConfig,
        site_idx: int,
        total_sites: int,
        job_id: str,
    ) -> None:
        if self._progress_store is not None and job_id:
            self._progress_store.mark_site_running(
                job_id,
                site_id=site_id,
                completed_sites=site_idx,
                total_sites=total_sites,
            )
        if site_idx > 0:
            delay = _jittered(_INTER_SITE_DELAY_SECONDS)
            _logger.debug(
                "사이트 전환 휴식: %.1fs (다음=%s)", delay, site_id,
                extra={"correlation_id": "", "service": _SERVICE_NAME},
            )
            await asyncio.sleep(delay)

        options = CrawlOptions.from_site(site)
        for board_idx, board_url in enumerate(site.board_urls):
            await self._process_board(
                stats,
                site_id=site_id,
                site=site,
                board_url=board_url,
                board_idx=board_idx,
                options=options,
            )

        if self._progress_store is not None and job_id:
            self._progress_store.mark_site_complete(
                job_id,
                site_id=site_id,
                completed_sites=site_idx + 1,
                total_sites=total_sites,
            )

    async def _process_board(
        self,
        stats: PipelineStats,
        *,
        site_id: str,
        site: SiteConfig,
        board_url: str,
        board_idx: int,
        options: CrawlOptions,
    ) -> None:
        if board_idx > 0:
            await asyncio.sleep(_jittered(_INTER_BOARD_DELAY_SECONDS))
        board_cid = generate()
        post_urls = await _fetch_post_urls(
            board_url, site.post_url_pattern, _MAX_POSTS_PER_BOARD,
            correlation_id=board_cid,
            options=options,
        )
        for post_url in post_urls:
            await self._process_post(
                stats,
                site_id=site_id,
                site=site,
                post_url=post_url,
                options=options,
            )

    async def _process_post(
        self,
        stats: PipelineStats,
        *,
        site_id: str,
        site: SiteConfig,
        post_url: str,
        options: CrawlOptions,
    ) -> None:
        cid = generate()
        if self._url_dedup is not None and self._url_dedup.has_seen(post_url, correlation_id=cid):
            stats.skipped_seen_url += 1
            return
        stats.attempted += 1
        try:
            result = await self._crawler.fetch(
                post_url,
                correlation_id=cid,
                **options.fetch_kwargs(),
            )
            if not (result.fit_markdown or "").strip():
                stats.skipped_empty += 1
                _logger.warning(
                    "빈 게시글 스킵: %s", post_url,
                    extra={"correlation_id": cid, "service": _SERVICE_NAME},
                )
                return

            if self._should_skip_post(stats, site_id, post_url, result.fit_markdown, cid):
                return
            if self._dedup.is_duplicate(result.fit_markdown, correlation_id=cid):
                stats.skipped_dedup += 1
                return

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
            return

        self._mark_successful_enqueue(post_url, result.fit_markdown, cid)

    def _should_skip_post(
        self,
        stats: PipelineStats,
        site_id: str,
        post_url: str,
        markdown: str,
        correlation_id: str,
    ) -> bool:
        validation = content_validator.validate(site_id, markdown, post_url)
        if validation.is_real_user_post:
            return False
        if validation.kind == "sticky":
            stats.skipped_sticky += 1
        elif validation.kind in ("auth_wall", "captcha", "error"):
            stats.skipped_blocked += 1
        elif validation.kind in ("empty", "short"):
            stats.skipped_empty += 1
        else:
            stats.skipped_unknown += 1
        _logger.info(
            "validator 스킵 [%s]: %s — %s",
            validation.kind, post_url, validation.reason,
            extra={"correlation_id": correlation_id, "service": _SERVICE_NAME},
        )
        return True

    def _mark_successful_enqueue(
        self,
        post_url: str,
        markdown: str,
        correlation_id: str,
    ) -> None:
        try:
            self._dedup.mark_seen(markdown, correlation_id=correlation_id)
        except Exception as exc:
            _logger.warning(
                "dedup mark_seen 실패 (큐에는 이미 발행됨): %s — %s", post_url, exc,
                extra={"correlation_id": correlation_id, "service": _SERVICE_NAME},
                exc_info=True,
            )
        if self._url_dedup is None:
            return
        try:
            self._url_dedup.mark_seen(post_url, correlation_id=correlation_id)
        except Exception as exc:
            _logger.warning(
                "url_dedup mark_seen 실패: %s — %s", post_url, exc,
                extra={"correlation_id": correlation_id, "service": _SERVICE_NAME},
                exc_info=True,
            )


class CrawlScheduler:
    """APScheduler + TriggerListener 통합 스케줄러."""

    def __init__(self) -> None:
        redis_url = get_redis_url()
        auth_kwargs = redis_auth_kwargs(redis_url)
        mq_client = redis.from_url(
            redis_url, db=REDIS_MQ_DB, decode_responses=True, **auth_kwargs
        )
        dedup_client = redis.from_url(
            redis_url, db=REDIS_DEDUP_DB, decode_responses=True, **auth_kwargs
        )

        # 같은 ZSET 을 파이프라인과 cleanup 잡이 공유해야 하므로 인스턴스 분리 보관.
        self._url_dedup = UrlDedupChecker(dedup_client)
        self._progress_store = CrawlJobProgressStore(mq_client)
        self._pipeline = CrawlPipeline(
            crawler=Crawl4AICrawler(headless=True, output_dir="output/_tmp"),
            storage=PostStorage(),
            dedup=DedupChecker(dedup_client),
            publisher=RedisPublisher(mq_client),
            url_dedup=self._url_dedup,
            progress_store=self._progress_store,
        )
        # scheduled run + 수동 trigger 동시 실행 방지
        self._run_lock = asyncio.Lock()
        self._trigger_listener = TriggerListener(redis_url, self._run_locked)
        self._scheduler = AsyncIOScheduler()

    async def _run_locked(self, command: CrawlTriggerCommand | None = None) -> None:
        # APScheduler 잡 + 수동 trigger 양쪽에서 호출되는 단일 진입점.
        job_id = command.job_id if command is not None else ""
        if self._run_lock.locked():
            if job_id:
                self._progress_store.mark_skipped(
                    job_id,
                    message="이미 다른 크롤링이 실행 중입니다.",
                )
            _logger.info(
                "이미 실행 중 — 이번 호출 스킵",
                extra={
                    "correlation_id": command.correlation_id if command is not None else "",
                    "service": _SERVICE_NAME,
                },
            )
            return
        activity: tuple[str, str] | None = None
        exc_to_reraise: Exception | None = None
        async with self._run_lock:
            try:
                stats = await self._pipeline.run(job_id=job_id)
                if job_id:
                    self._progress_store.mark_succeeded(job_id)
                trigger = "수동" if job_id else "스케줄"
                activity = (
                    "CRAWL_COMPLETED",
                    f"{trigger} 크롤링 완료 — 큐 {stats.enqueued}건 / 시도 {stats.attempted}건",
                )
            except Exception as exc:
                if job_id:
                    self._progress_store.mark_failed(job_id, message=str(exc))
                activity = ("CRAWL_FAILED", f"크롤링 실패: {exc}")
                exc_to_reraise = exc

        # lock 해제 후 HTTP 호출 — 최대 5초 타임아웃이 다음 크롤 스케줄에 영향 없도록.
        if activity:
            await self._post_activity(*activity)
        if exc_to_reraise is not None:
            raise exc_to_reraise

    async def _post_activity(self, event_type: str, message: str) -> None:
        api_url = os.environ.get("TRACKER_API_URL", "").rstrip("/")
        if not api_url:
            return
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                await client.post(
                    f"{api_url}/api/activity",
                    json={"eventType": event_type, "message": message},
                )
        except Exception as exc:
            _logger.warning(
                "activity POST 실패 (무시): %s", exc,
                extra={"correlation_id": "", "service": _SERVICE_NAME},
            )

    async def _cleanup_url_dedup_job(self) -> None:
        # sync redis 호출을 thread 로 오프로드 — 다른 async 잡(crawl_pipeline) 이벤트 루프 블락 방지.
        await asyncio.to_thread(self._url_dedup.cleanup_older_than)

    def _on_job_missed(self, event) -> None:
        # Story 5-1 운영 가시성 — misfire_grace_time 초과로 스킵된 잡 구조화 로그.
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
            # 다운타임 복귀 시 적체된 missed run 을 모두 실행하지 않고 1회로 합쳐 발화.
            coalesce=True,
            id="crawl_pipeline",
            replace_existing=True,
        )
        # 03:00 UTC = 12:00 KST — 한·중·대만 점심시간으로 게시판 트래픽 최저, fetch 잡과 충돌 확률 최소.
        # timezone="UTC" 명시 — Docker base(python:3.11-slim) 는 UTC 지만 EC2 host TZ 또는 TZ env 변경 시
        # 03:00 이 KST 로 해석돼 12시간 어긋나는 회귀 차단.
        self._scheduler.add_job(
            self._cleanup_url_dedup_job,
            trigger=CronTrigger(hour=3, minute=0, timezone="UTC"),
            max_instances=1,
            misfire_grace_time=3600,
            coalesce=True,
            id="url_dedup_cleanup",
            replace_existing=True,
        )
        self._scheduler.add_listener(self._on_job_missed, EVENT_JOB_MISSED)
        _logger.info(
            "APScheduler 등록: crawl_pipeline %d분 주기 + url_dedup_cleanup 일 1회 03:00 UTC",
            interval,
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
