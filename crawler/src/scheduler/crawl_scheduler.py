"""APScheduler 기반 크롤링 파이프라인 + 수동 트리거 진입점."""
from __future__ import annotations

import asyncio
import json
import os
import random
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import httpx
import redis
from apscheduler.events import EVENT_JOB_MISSED
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
from crawl4ai.async_configs import CacheMode

from crawler.src.crawl4ai_crawler import Crawl4AICrawler, CrawlResult
from crawler.src.preprocessor import content_validator, language_detector
from crawler.src.preprocessor.dedup_checker import DedupChecker
from crawler.src.preprocessor.serializer import to_crawl_event
from crawler.src.preprocessor.url_dedup_checker import UrlDedupChecker
from crawler.src.queue.redis_publisher import RedisPublisher
from crawler.src.scheduler.candidate_scoring import score_listing_candidate
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
from shared.exceptions.base_exception import CrawlerException
from shared.structured_logger import get_logger

_SERVICE_NAME = os.environ.get("SERVICE_NAME", "crawler")
_logger = get_logger(__name__)
_MAX_POSTS_PER_BOARD = int(os.environ.get("MAX_POSTS_PER_BOARD", "30"))
_DRY_RUN = os.environ.get("CRAWL_DRY_RUN", "").lower() in ("1", "true", "yes")
_DRY_RUN_OUTPUT_DIR = Path(os.environ.get("CRAWL_DRY_RUN_OUTPUT_DIR", "output"))
_DRY_RUN_SESSION_TS = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
_PRIORITY_BUDGET_ENABLED = os.environ.get(
    "CRAWL_PRIORITY_BUDGET_ENABLED", "true"
).lower() not in ("0", "false", "no")
_P3_DEFAULT_CAP_PER_BOARD = int(os.environ.get("CRAWL_P3_DEFAULT_CAP_PER_BOARD", "1"))
_P3_MIXED_CAP_PER_BOARD = int(os.environ.get("CRAWL_P3_MIXED_CAP_PER_BOARD", "5"))
_P3_52POJIE_CAP_PER_BOARD = int(os.environ.get("CRAWL_P3_52POJIE_CAP_PER_BOARD", "1"))
_MIXED_PRIORITY_SOURCES = frozenset({"dcard", "dcard_online", "ptt_mobile_game"})
_DETAIL_FETCH_CONCURRENCY = max(1, int(os.environ.get("CRAWL_DETAIL_FETCH_CONCURRENCY", "3")))
_DETAIL_FETCH_SOURCE_CONCURRENCY_DEFAULT = "dcard=1,dcard_online=1,52pojie=1"
_DETAIL_FETCH_STAGGER_SECONDS = max(
    0.0,
    float(os.environ.get("CRAWL_DETAIL_FETCH_STAGGER_SECONDS", "0.25")),
)
_DETAIL_CLOUDFLARE_BACKOFF_SECONDS = max(
    0.0,
    float(os.environ.get("CRAWL_DETAIL_CLOUDFLARE_BACKOFF_SECONDS", "0")),
)
_DETAIL_CLOUDFLARE_BACKOFF_RETRIES = max(
    0,
    int(os.environ.get("CRAWL_DETAIL_CLOUDFLARE_BACKOFF_RETRIES", "0")),
)
_DETAIL_CLOUDFLARE_BACKOFF_SOURCES = {
    item.strip()
    for item in os.environ.get(
        "CRAWL_DETAIL_CLOUDFLARE_BACKOFF_SOURCES",
        "dcard,dcard_online",
    ).split(",")
    if item.strip()
}
_DETAIL_SOURCE_COOLDOWN_SECONDS = max(
    0.0,
    float(os.environ.get("CRAWL_DETAIL_SOURCE_COOLDOWN_SECONDS", "0")),
)
_DETAIL_SOURCE_COOLDOWN_SOURCES = {
    item.strip()
    for item in os.environ.get(
        "CRAWL_DETAIL_SOURCE_COOLDOWN_SOURCES",
        "dcard,dcard_online",
    ).split(",")
    if item.strip()
}
_DETAIL_CHALLENGE_COOLDOWN_SECONDS = max(
    0.0,
    float(os.environ.get("CRAWL_DETAIL_CHALLENGE_COOLDOWN_SECONDS", "0")),
)

# 사이트·보드 간 휴식 — anti-bot rate limit(예: Bahamut ACS-GOTO) 회피용.
# jitter 비율(±25%) 곱해서 인간적 패턴 흉내.
_INTER_SITE_DELAY_SECONDS = float(os.environ.get("INTER_SITE_DELAY_SECONDS", "15"))
_INTER_BOARD_DELAY_SECONDS = float(os.environ.get("INTER_BOARD_DELAY_SECONDS", "3"))


def _jittered(base: float, jitter_ratio: float = 0.25) -> float:
    """base * (1 ± jitter_ratio) 안에서 무작위 값."""
    if base <= 0:
        return 0.0
    return base * (1.0 + random.uniform(-jitter_ratio, jitter_ratio))


def _parse_source_concurrency(raw: str) -> dict[str, int]:
    overrides: dict[str, int] = {}
    for item in raw.split(","):
        if not item.strip() or "=" not in item:
            continue
        site_id, value = item.split("=", 1)
        site_id = site_id.strip()
        if not site_id:
            continue
        try:
            overrides[site_id] = max(1, int(value.strip()))
        except ValueError:
            _logger.warning(
                "source concurrency 설정 무시: %s", item,
                extra={"correlation_id": "", "service": _SERVICE_NAME},
            )
    return overrides


_DETAIL_FETCH_SOURCE_CONCURRENCY = _parse_source_concurrency(
    os.environ.get(
        "CRAWL_DETAIL_SOURCE_CONCURRENCY",
        _DETAIL_FETCH_SOURCE_CONCURRENCY_DEFAULT,
    )
)


def detail_fetch_concurrency_for_site(site_id: str) -> int:
    return _DETAIL_FETCH_SOURCE_CONCURRENCY.get(site_id, _DETAIL_FETCH_CONCURRENCY)


def _is_cloudflare_challenge_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "cloudflare js challenge" in message


def _outcome_has_cloudflare_challenge(outcome: "PostFetchOutcome") -> bool:
    return outcome.error is not None and _is_cloudflare_challenge_error(outcome.error)


def _detail_source_cooldown_seconds(site_id: str) -> float:
    if site_id not in _DETAIL_SOURCE_COOLDOWN_SOURCES:
        return 0.0
    return _DETAIL_SOURCE_COOLDOWN_SECONDS


async def _sleep_after_detail_outcome(
    site_id: str,
    outcome: "PostFetchOutcome",
    *,
    has_next: bool,
) -> None:
    if not has_next:
        return
    delay = _detail_source_cooldown_seconds(site_id)
    if _outcome_has_cloudflare_challenge(outcome):
        delay = max(delay, _DETAIL_CHALLENGE_COOLDOWN_SECONDS)
    if delay <= 0:
        return
    _logger.info(
        "상세 fetch source cooldown: site=%s delay=%.1fs url=%s",
        site_id,
        delay,
        outcome.post_url,
        extra={"correlation_id": outcome.correlation_id, "service": _SERVICE_NAME},
    )
    await asyncio.sleep(delay)


@dataclass(frozen=True)
class CrawlOptions:
    cookies: list[dict] | None = None
    wait_for: str | None = None
    headers: dict[str, str] | None = None
    page_timeout: int | None = None
    proxy: dict | None = None
    max_retries: int = 0
    js_code: list[str] | None = None
    delay_before_return_html: float | None = None
    scan_full_page: bool = False
    scroll_delay: float | None = None
    virtual_scroll_config: dict | None = None
    wait_until: str | None = None
    simulate_user: bool = False
    override_navigator: bool = False
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
            max_retries=site.max_retries,
            js_code=site.js_code,
            delay_before_return_html=site.delay_before_return_html,
            scan_full_page=site.scan_full_page,
            scroll_delay=site.scroll_delay,
            virtual_scroll_config=site.virtual_scroll_config,
            wait_until=site.wait_until,
            simulate_user=site.simulate_user,
            override_navigator=site.override_navigator,
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
        if self.override_navigator:
            kwargs["override_navigator"] = True
        if self.c4a_script is not None:
            kwargs["c4a_script"] = self.c4a_script
        if self.exclude_social_media_links:
            kwargs["exclude_social_media_links"] = True
        if self.exclude_external_links is not None:
            kwargs["exclude_external_links"] = self.exclude_external_links
        if self.proxy is not None:
            kwargs["proxy_config"] = self.proxy
        if self.max_retries:
            kwargs["max_retries"] = self.max_retries
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
            "max_retries": self.max_retries,
            "js_code": self.js_code,
            "delay_before_return_html": self.delay_before_return_html,
            "scan_full_page": self.scan_full_page,
            "scroll_delay": self.scroll_delay,
            "virtual_scroll_config": self.virtual_scroll_config,
            "wait_until": self.wait_until,
            "simulate_user": self.simulate_user,
            "override_navigator": self.override_navigator,
            "user_agent_mode": self.user_agent_mode,
            "c4a_script": self.c4a_script,
            "exclude_social_media_links": self.exclude_social_media_links,
            "exclude_external_links": self.exclude_external_links,
        }


@dataclass(frozen=True)
class PostUrlCandidate:
    url: str
    title: str
    keyword_matched: bool


@dataclass(frozen=True)
class ListingResult:
    urls: list[str]
    discovered_total: int
    keyword_matched: int
    keyword_unmatched: int
    candidates: list[PostUrlCandidate] = field(default_factory=list)
    next_board_url: str | None = None


@dataclass(frozen=True)
class ScoredPostCandidate:
    url: str
    title: str
    score: int
    priority_bucket: str
    score_reasons: list[str]
    keyword_matched: bool


@dataclass(frozen=True)
class PostFetchOutcome:
    post_url: str
    correlation_id: str
    result: CrawlResult | None = None
    error: Exception | None = None


def _post_url_sort_key(candidate: PostUrlCandidate) -> tuple[int, int]:
    """키워드 매칭 후보를 먼저, 같은 그룹 안에서는 최신 post id 우선."""
    matches = re.findall(r"/(\d+)", candidate.url)
    post_id = int(matches[-1]) if matches else 0
    return (1 if candidate.keyword_matched else 0, post_id)


def _extract_post_url_candidates(
    links: list[dict],
    pattern: str,
    *,
    title_keywords: list[str] | None = None,
) -> list[PostUrlCandidate]:
    """listing 링크에서 게시글 후보를 추출한다.

    title_keywords 는 hard filter 가 아니라 우선순위 feature 다. 혼합 보드에서
    관련 제목을 먼저 fetch 하되, 은어/외부 링크 중심 글이 제목 키워드 없이
    등장하는 경우를 보존한다.
    """
    seen: set[str] = set()
    candidates: list[PostUrlCandidate] = []
    compiled = re.compile(pattern)
    keywords_lower = [k.lower() for k in (title_keywords or [])]

    for link in links:
        full = link.get("href") or ""
        href = full.split("?")[0]
        link_title = link.get("text") or link.get("title") or ""
        candidate_url = (
            full if compiled.match(full) else href if compiled.match(href) else None
        )
        if not candidate_url or candidate_url in seen:
            continue
        seen.add(candidate_url)
        title_lower = link_title.lower()
        keyword_matched = bool(
            keywords_lower and any(k in title_lower for k in keywords_lower)
        )
        candidates.append(
            PostUrlCandidate(
                url=candidate_url,
                title=link_title,
                keyword_matched=keyword_matched,
            )
        )

    candidates.sort(key=_post_url_sort_key, reverse=True)
    return candidates


def _p3_cap_for_site(site_id: str) -> int:
    if site_id == "52pojie":
        return _P3_52POJIE_CAP_PER_BOARD
    if site_id in _MIXED_PRIORITY_SOURCES:
        return _P3_MIXED_CAP_PER_BOARD
    return _P3_DEFAULT_CAP_PER_BOARD


def _score_post_candidates(
    *,
    site_id: str,
    board_url: str,
    listing: ListingResult,
    site: SiteConfig,
) -> list[ScoredPostCandidate]:
    scored: list[ScoredPostCandidate] = []
    has_title_keywords = bool(site.title_keywords)
    candidates = listing.candidates or [
        PostUrlCandidate(url=url, title="", keyword_matched=False)
        for url in listing.urls
    ]
    for cand in candidates:
        priority = score_listing_candidate(
            site_id=site_id,
            board_url=board_url,
            title=cand.title,
            keyword_matched=cand.keyword_matched,
            has_title_keywords=has_title_keywords,
        )
        scored.append(
            ScoredPostCandidate(
                url=cand.url,
                title=cand.title,
                score=priority.score,
                priority_bucket=priority.priority_bucket,
                score_reasons=priority.reasons,
                keyword_matched=cand.keyword_matched,
            )
        )
    return scored


def _select_detail_candidates(
    *,
    site_id: str,
    board_url: str,
    listing: ListingResult,
    site: SiteConfig,
    limit: int,
) -> list[ScoredPostCandidate]:
    """운영 상세 fetch 후보를 priority budget으로 고른다.

    P0/P1/P2는 probe에서 real/signal 효율이 좋아 hard limit 안에서 우선
    선택한다. P3는 제목에 드러나지 않는 은어/외부 링크 글을 보존하기 위해
    source별 cap만큼 샘플링한다.
    """
    scored = _score_post_candidates(
        site_id=site_id,
        board_url=board_url,
        listing=listing,
        site=site,
    )
    if not _PRIORITY_BUDGET_ENABLED:
        return scored[:limit]

    high_priority = [c for c in scored if c.priority_bucket != "P3"]
    p3 = [c for c in scored if c.priority_bucket == "P3"]

    high_priority.sort(key=lambda c: (-c.score, c.url))
    p3.sort(key=lambda c: (not c.keyword_matched, -c.score, c.url))

    selected = high_priority + p3[:_p3_cap_for_site(site_id)]
    return selected[:limit]


async def _fetch_post_urls(
    board_url: str,
    pattern: str,
    limit: int,
    *,
    correlation_id: str = "",
    options: CrawlOptions,
    prev_page_link_text: str | None = None,
) -> ListingResult:
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
        return ListingResult(urls=[], discovered_total=0, keyword_matched=0, keyword_unmatched=0)
    if not result.success:
        _logger.warning(
            "게시판 목록 크롤 실패: %s", board_url,
            extra={"correlation_id": correlation_id, "service": _SERVICE_NAME},
        )
        return ListingResult(urls=[], discovered_total=0, keyword_matched=0, keyword_unmatched=0)

    all_links = (result.links.get("internal") or []) + (result.links.get("external") or [])
    candidates = _extract_post_url_candidates(
        all_links,
        pattern,
        title_keywords=options.title_keywords,
    )
    selected = candidates[:limit]
    matched = sum(1 for c in candidates if c.keyword_matched)
    unmatched = len(candidates) - matched

    if options.title_keywords:
        _logger.info(
            "listing 후보 추출: board=%s total=%d selected=%d keyword_matched=%d keyword_unmatched=%d",
            board_url,
            len(candidates),
            len(selected),
            matched,
            unmatched,
            extra={"correlation_id": correlation_id, "service": _SERVICE_NAME},
        )
    next_board_url: str | None = None
    if prev_page_link_text:
        for lk in all_links:
            if prev_page_link_text in (lk.get("text") or ""):
                href = lk.get("href") or ""
                if href:
                    next_board_url = href
                    break
    return ListingResult(
        urls=[c.url for c in selected],
        discovered_total=len(candidates),
        keyword_matched=matched,
        keyword_unmatched=unmatched,
        candidates=candidates,
        next_board_url=next_board_url,
    )


@dataclass
class PipelineStats:
    listing_boards: int = 0
    listing_urls_selected: int = 0
    listing_discovered_total: int = 0   # limit 적용 전 전체 후보 수
    listing_keyword_matched: int = 0    # 키워드 매칭 후보 수 (우선순위 feature)
    listing_keyword_unmatched: int = 0  # 키워드 미매칭 후보 수 (보존된 수)
    selected_p0: int = 0
    selected_p1: int = 0
    selected_p2: int = 0
    selected_p3: int = 0
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


def _expand_page_urls(board_url: str, site: SiteConfig) -> list[str]:
    """board_url + page_url_template 으로 pagination URL 목록 생성.

    max_pages=1 이거나 template 없으면 [board_url] 그대로 반환.
    template 은 {base} (board_url) 와 {page} (2부터 시작) 를 사용한다.
    예: "{base}&page={page}"
    """
    if site.max_pages <= 1 or not site.page_url_template:
        return [board_url]
    urls = [board_url]
    for page in range(2, site.max_pages + 1):
        urls.append(site.page_url_template.format(base=board_url, page=page))
    return urls


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
            "파이프라인 완료: 보드=%d 리스팅발견=%d 리스팅선택=%d"
            " P0=%d P1=%d P2=%d P3=%d kw매칭=%d kw미매칭=%d"
            " 시도=%d 큐=%d url중복=%d 본문중복=%d 빈=%d 공지=%d 상태=%d 미확인=%d 실패=%d",
            stats.listing_boards,
            stats.listing_discovered_total,
            stats.listing_urls_selected,
            stats.selected_p0,
            stats.selected_p1,
            stats.selected_p2,
            stats.selected_p3,
            stats.listing_keyword_matched,
            stats.listing_keyword_unmatched,
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
        if self._progress_store is not None:
            self._progress_store.store_pipeline_stats({
                "listingBoards": stats.listing_boards,
                "listingDiscoveredTotal": stats.listing_discovered_total,
                "listingUrlsSelected": stats.listing_urls_selected,
                "listingKeywordMatched": stats.listing_keyword_matched,
                "listingKeywordUnmatched": stats.listing_keyword_unmatched,
                "selectedP0": stats.selected_p0,
                "selectedP1": stats.selected_p1,
                "selectedP2": stats.selected_p2,
                "selectedP3": stats.selected_p3,
                "attempted": stats.attempted,
                "enqueued": stats.enqueued,
                "skippedSeenUrl": stats.skipped_seen_url,
                "skippedDedup": stats.skipped_dedup,
                "skippedEmpty": stats.skipped_empty,
                "skippedSticky": stats.skipped_sticky,
                "skippedBlocked": stats.skipped_blocked,
                "skippedUnknown": stats.skipped_unknown,
                "failed": stats.failed,
            })
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
        board_idx = 0
        for board_url in site.board_urls:
            if site.prev_page_link_text and site.max_pages > 1:
                # 동적 pagination: 上頁 등 prev-page 링크를 따라 최대 max_pages 페이지.
                current_url: str | None = board_url
                for _ in range(site.max_pages):
                    if current_url is None:
                        break
                    next_url = await self._process_board(
                        stats,
                        site_id=site_id,
                        site=site,
                        board_url=current_url,
                        board_idx=board_idx,
                        options=options,
                    )
                    board_idx += 1
                    current_url = next_url
            else:
                for page_url in _expand_page_urls(board_url, site):
                    await self._process_board(
                        stats,
                        site_id=site_id,
                        site=site,
                        board_url=page_url,
                        board_idx=board_idx,
                        options=options,
                    )
                    board_idx += 1

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
    ) -> str | None:
        if board_idx > 0:
            await asyncio.sleep(_jittered(_INTER_BOARD_DELAY_SECONDS))
        board_cid = generate()
        listing = await _fetch_post_urls(
            board_url, site.post_url_pattern, _MAX_POSTS_PER_BOARD,
            correlation_id=board_cid,
            options=options,
            prev_page_link_text=site.prev_page_link_text,
        )
        selected_candidates = _select_detail_candidates(
            site_id=site_id,
            board_url=board_url,
            listing=listing,
            site=site,
            limit=_MAX_POSTS_PER_BOARD,
        )
        stats.listing_boards += 1
        stats.listing_urls_selected += len(selected_candidates)
        stats.listing_discovered_total += listing.discovered_total
        stats.listing_keyword_matched += listing.keyword_matched
        stats.listing_keyword_unmatched += listing.keyword_unmatched
        stats.selected_p0 += sum(1 for c in selected_candidates if c.priority_bucket == "P0")
        stats.selected_p1 += sum(1 for c in selected_candidates if c.priority_bucket == "P1")
        stats.selected_p2 += sum(1 for c in selected_candidates if c.priority_bucket == "P2")
        stats.selected_p3 += sum(1 for c in selected_candidates if c.priority_bucket == "P3")
        _logger.info(
            "게시판 후보 선택: site=%s board=%s discovered=%d selected=%d"
            " P0=%d P1=%d P2=%d P3=%d kw_matched=%d kw_unmatched=%d limit=%d",
            site_id, board_url,
            listing.discovered_total, len(selected_candidates),
            sum(1 for c in selected_candidates if c.priority_bucket == "P0"),
            sum(1 for c in selected_candidates if c.priority_bucket == "P1"),
            sum(1 for c in selected_candidates if c.priority_bucket == "P2"),
            sum(1 for c in selected_candidates if c.priority_bucket == "P3"),
            listing.keyword_matched, listing.keyword_unmatched,
            _MAX_POSTS_PER_BOARD,
            extra={"correlation_id": board_cid, "service": _SERVICE_NAME},
        )
        if _DRY_RUN:
            self._dump_dry_run_candidates(
                site_id, board_url, listing, site,
                selected_candidates=selected_candidates,
            )
            return listing.next_board_url
        await self._process_selected_posts(
            stats,
            site_id=site_id,
            site=site,
            candidates=selected_candidates,
            options=options,
        )
        return listing.next_board_url

    def _dump_dry_run_candidates(
        self,
        site_id: str,
        board_url: str,
        listing: ListingResult,
        site: SiteConfig,
        *,
        selected_candidates: list[ScoredPostCandidate],
    ) -> None:
        _DRY_RUN_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        path = _DRY_RUN_OUTPUT_DIR / f"dry_run_{_DRY_RUN_SESSION_TS}.jsonl"
        selected_urls = {c.url for c in selected_candidates}
        has_title_keywords = bool(site.title_keywords)
        with path.open("a", encoding="utf-8") as f:
            for cand in listing.candidates:
                priority = score_listing_candidate(
                    site_id=site_id,
                    board_url=board_url,
                    title=cand.title,
                    keyword_matched=cand.keyword_matched,
                    has_title_keywords=has_title_keywords,
                )
                record = {
                    "site_id": site_id,
                    "board_url": board_url,
                    "url": cand.url,
                    "title": cand.title,
                    "has_title_keywords": has_title_keywords,
                    "keyword_matched": cand.keyword_matched,
                    "selected": cand.url in selected_urls,
                    "score": priority.score,
                    "priority_bucket": priority.priority_bucket,
                    "score_reasons": priority.reasons,
                    "source_risk": priority.source_risk,
                    "keyword_signal": priority.keyword_signal,
                    "contact_signal": priority.contact_signal,
                    "download_signal": priority.download_signal,
                    "game_signal": priority.game_signal,
                    "exploration_bonus": priority.exploration_bonus,
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

    async def _process_selected_posts(
        self,
        stats: PipelineStats,
        *,
        site_id: str,
        site: SiteConfig,
        candidates: list[ScoredPostCandidate],
        options: CrawlOptions,
    ) -> None:
        fetch_targets: list[tuple[str, str]] = []
        for candidate in candidates:
            cid = generate()
            post_url = candidate.url
            if self._url_dedup is not None and self._url_dedup.has_seen(
                post_url,
                correlation_id=cid,
            ):
                stats.skipped_seen_url += 1
                continue
            stats.attempted += 1
            fetch_targets.append((post_url, cid))

        if not fetch_targets:
            return

        fetch_many = getattr(self._crawler, "fetch_many", None)
        site_concurrency = detail_fetch_concurrency_for_site(site_id)
        if (
            callable(fetch_many)
            and site_concurrency > 1
            and len(fetch_targets) > 1
        ):
            outcomes = await self._fetch_posts_many(
                fetch_targets,
                options,
                concurrency=site_concurrency,
            )
        elif site_concurrency == 1 or len(fetch_targets) == 1:
            outcomes = []
            for idx, (post_url, cid) in enumerate(fetch_targets):
                outcome = await self._fetch_post(site_id, post_url, cid, options)
                outcomes.append(outcome)
                await _sleep_after_detail_outcome(
                    site_id,
                    outcome,
                    has_next=idx < len(fetch_targets) - 1,
                )
        else:
            _logger.info(
                "상세 fetch 병렬 처리: site=%s count=%d concurrency=%d stagger=%.2fs",
                site_id,
                len(fetch_targets),
                site_concurrency,
                _DETAIL_FETCH_STAGGER_SECONDS,
                extra={"correlation_id": "", "service": _SERVICE_NAME},
            )
            semaphore = asyncio.Semaphore(site_concurrency)

            async def _bounded_fetch(idx: int, post_url: str, cid: str) -> PostFetchOutcome:
                if idx and _DETAIL_FETCH_STAGGER_SECONDS:
                    await asyncio.sleep(_DETAIL_FETCH_STAGGER_SECONDS * idx)
                async with semaphore:
                    return await self._fetch_post(site_id, post_url, cid, options)

            outcomes = await asyncio.gather(*(
                _bounded_fetch(idx, post_url, cid)
                for idx, (post_url, cid) in enumerate(fetch_targets)
            ))

        for outcome in outcomes:
            self._process_fetched_post(stats, site_id, site, outcome)

    async def _fetch_post(
        self,
        site_id: str,
        post_url: str,
        correlation_id: str,
        options: CrawlOptions,
    ) -> PostFetchOutcome:
        attempt = 0
        while True:
            try:
                result = await self._crawler.fetch(
                    post_url,
                    correlation_id=correlation_id,
                    **options.fetch_kwargs(),
                )
                return PostFetchOutcome(
                    post_url=post_url,
                    correlation_id=correlation_id,
                    result=result,
                )
            except Exception as exc:
                if (
                    site_id in _DETAIL_CLOUDFLARE_BACKOFF_SOURCES
                    and _is_cloudflare_challenge_error(exc)
                    and attempt < _DETAIL_CLOUDFLARE_BACKOFF_RETRIES
                ):
                    attempt += 1
                    delay = _DETAIL_CLOUDFLARE_BACKOFF_SECONDS * attempt
                    _logger.warning(
                        "Cloudflare challenge 후 backoff retry: site=%s attempt=%d/%d delay=%.1fs url=%s",
                        site_id,
                        attempt,
                        _DETAIL_CLOUDFLARE_BACKOFF_RETRIES,
                        delay,
                        post_url,
                        extra={"correlation_id": correlation_id, "service": _SERVICE_NAME},
                    )
                    if delay > 0:
                        await asyncio.sleep(delay)
                    continue
                return PostFetchOutcome(
                    post_url=post_url,
                    correlation_id=correlation_id,
                    error=exc,
                )

    async def _fetch_posts_many(
        self,
        fetch_targets: list[tuple[str, str]],
        options: CrawlOptions,
        *,
        concurrency: int,
    ) -> list[PostFetchOutcome]:
        urls = [post_url for post_url, _ in fetch_targets]
        correlation_ids = [cid for _, cid in fetch_targets]
        try:
            outcomes = await self._crawler.fetch_many(
                urls,
                correlation_ids=correlation_ids,
                concurrency=concurrency,
                rate_limit_delay=(
                    _DETAIL_FETCH_STAGGER_SECONDS,
                    max(_DETAIL_FETCH_STAGGER_SECONDS, _DETAIL_FETCH_STAGGER_SECONDS * 2),
                ),
                **options.fetch_kwargs(),
            )
        except Exception as exc:
            return [
                PostFetchOutcome(post_url=post_url, correlation_id=cid, error=exc)
                for post_url, cid in fetch_targets
            ]

        by_url = {outcome.url: outcome for outcome in outcomes}
        normalized: list[PostFetchOutcome] = []
        for post_url, cid in fetch_targets:
            outcome = by_url.get(post_url)
            if outcome is None:
                normalized.append(
                    PostFetchOutcome(
                        post_url=post_url,
                        correlation_id=cid,
                        error=CrawlerException(
                            "크롤링 실패: batch outcome missing",
                            correlation_id=cid,
                        ),
                    )
                )
                continue
            normalized.append(
                PostFetchOutcome(
                    post_url=post_url,
                    correlation_id=cid,
                    result=outcome.result,
                    error=outcome.error,
                )
            )
        return normalized

    def _process_fetched_post(
        self,
        stats: PipelineStats,
        site_id: str,
        site: SiteConfig,
        outcome: PostFetchOutcome,
    ) -> None:
        post_url = outcome.post_url
        cid = outcome.correlation_id
        if outcome.error is not None:
            stats.failed += 1
            _logger.error(
                "게시글 처리 실패: %s — %s", post_url, outcome.error,
                extra={"correlation_id": cid, "service": _SERVICE_NAME},
                exc_info=(
                    type(outcome.error),
                    outcome.error,
                    outcome.error.__traceback__,
                ),
            )
            return

        result = outcome.result
        if result is None:
            stats.failed += 1
            _logger.error(
                "게시글 처리 실패: %s — fetch 결과 없음", post_url,
                extra={"correlation_id": cid, "service": _SERVICE_NAME},
            )
            return

        text = result.markdown
        if not text.strip():
            stats.skipped_empty += 1
            _logger.warning(
                "빈 게시글 스킵: %s", post_url,
                extra={"correlation_id": cid, "service": _SERVICE_NAME},
            )
            return

        if self._should_skip_post(stats, site_id, post_url, text, cid):
            return
        if self._dedup.is_duplicate(text, correlation_id=cid):
            stats.skipped_dedup += 1
            return

        language = language_detector.detect(text, correlation_id=cid)
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
        self._mark_successful_enqueue(post_url, result.markdown, cid)

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
        outcome = await self._fetch_post(site_id, post_url, cid, options)
        self._process_fetched_post(stats, site_id, site, outcome)

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
