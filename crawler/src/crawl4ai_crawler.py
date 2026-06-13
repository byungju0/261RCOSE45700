from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import httpx
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
from crawl4ai.async_configs import CacheMode
from crawl4ai.async_dispatcher import MemoryAdaptiveDispatcher, RateLimiter
from crawl4ai.content_filter_strategy import PruningContentFilter
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator

from shared.exceptions.base_exception import CrawlerException
from shared.structured_logger import get_logger

_SERVICE_NAME = os.environ.get("SERVICE_NAME", "crawler")
_logger = get_logger(__name__)


@dataclass
class CrawlResult:
    url: str
    raw_markdown: str
    fit_markdown: str
    images: list[dict] = field(default_factory=list)
    downloaded_images: list[Path] = field(default_factory=list)
    crawl_stats: dict = field(default_factory=dict)

    @property
    def markdown(self) -> str:
        return self.fit_markdown or self.raw_markdown


@dataclass
class CrawlFetchOutcome:
    url: str
    correlation_id: str
    result: CrawlResult | None = None
    error: Exception | None = None


class Crawl4AICrawler:
    """crawl4ai 기반 크롤러 — 봇 탐지 우회 + 텍스트/이미지 추출."""

    _DEFAULT_PAGE_TIMEOUT_MS = 30_000

    def __init__(
        self,
        headless: bool = True,
        output_dir: str = "output/images",
        *,
        proxy: dict | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._headless = headless
        self._default_proxy = proxy
        self._default_headers = headers

        self._browser_config = self._build_browser_config(headers=headers)

        self._base_run_kwargs: dict = dict(
            cache_mode=CacheMode.BYPASS,
            magic=True,
            page_timeout=self._DEFAULT_PAGE_TIMEOUT_MS,
            mean_delay=1.5,
            max_range=1.0,
            remove_consent_popups=True,
            excluded_tags=["nav", "footer", "header"],
            markdown_generator=DefaultMarkdownGenerator(
                content_filter=PruningContentFilter(
                    threshold=0.5,
                    threshold_type="fixed",
                )
            ),
        )

    def _build_browser_config(
        self,
        *,
        headers: dict[str, str] | None,
        user_agent: str | None = None,
        user_agent_mode: str | None = None,
    ) -> BrowserConfig:
        kwargs: dict = dict(
            headless=self._headless,
            verbose=False,
            enable_stealth=True,
            ignore_https_errors=True,
        )
        if headers is not None:
            kwargs["headers"] = headers
        if user_agent is not None:
            kwargs["user_agent"] = user_agent
        if user_agent_mode is not None:
            kwargs["user_agent_mode"] = user_agent_mode
        return BrowserConfig(**kwargs)

    def _build_run_config(
        self,
        *,
        css_selector: str | None,
        wait_for: str | None,
        page_timeout: int | None,
        js_code: list[str] | None = None,
        delay_before_return_html: float | None = None,
        scan_full_page: bool = False,
        scroll_delay: float | None = None,
        virtual_scroll_config: dict | None = None,
        wait_until: str | None = None,
        simulate_user: bool = False,
        override_navigator: bool = False,
        c4a_script: list[str] | None = None,
        exclude_social_media_links: bool = True,
        exclude_external_links: bool | None = None,
        screenshot: bool = False,
        pdf: bool = False,
        proxy_config: dict | str | None = None,
        max_retries: int = 0,
        stream: bool = False,
        session_id: str | None = None,
    ) -> CrawlerRunConfig:
        kwargs = dict(self._base_run_kwargs)
        if css_selector is not None:
            kwargs["css_selector"] = css_selector
        if wait_for is not None:
            kwargs["wait_for"] = wait_for
        if page_timeout is not None:
            kwargs["page_timeout"] = page_timeout
        if js_code is not None:
            kwargs["js_code"] = js_code
        if delay_before_return_html is not None:
            kwargs["delay_before_return_html"] = delay_before_return_html
        if scan_full_page:
            kwargs["scan_full_page"] = True
            if scroll_delay is not None:
                kwargs["scroll_delay"] = scroll_delay
        if virtual_scroll_config is not None:
            kwargs["virtual_scroll_config"] = virtual_scroll_config
        if wait_until is not None:
            kwargs["wait_until"] = wait_until
        if simulate_user:
            kwargs["simulate_user"] = True
        if override_navigator:
            kwargs["override_navigator"] = True
        if c4a_script is not None:
            kwargs["c4a_script"] = c4a_script
        if exclude_social_media_links:
            kwargs["exclude_social_media_links"] = True
        if exclude_external_links is not None:
            kwargs["exclude_external_links"] = exclude_external_links
        if screenshot:
            kwargs["screenshot"] = True
        if pdf:
            kwargs["pdf"] = True
        if proxy_config is not None:
            kwargs["proxy_config"] = proxy_config
        if max_retries:
            kwargs["max_retries"] = max_retries
        if stream:
            kwargs["stream"] = True
        if session_id is not None:
            kwargs["session_id"] = session_id
        return CrawlerRunConfig(**kwargs)

    def _build_dispatcher(
        self,
        *,
        concurrency: int,
        base_delay: tuple[float, float],
        max_retries: int,
    ) -> MemoryAdaptiveDispatcher:
        return MemoryAdaptiveDispatcher(
            memory_threshold_percent=85.0,
            max_session_permit=max(1, concurrency),
            rate_limiter=RateLimiter(
                base_delay=base_delay,
                max_delay=30.0,
                max_retries=max_retries,
            ),
        )

    async def _to_crawl_result(
        self,
        result,
        *,
        source_url: str,
        correlation_id: str,
        download_images: bool,
        output_dir: Path | str | None,
        image_filter: Callable[[dict], bool] | None,
    ) -> CrawlResult:
        md = result.markdown
        if hasattr(md, "raw_markdown"):
            raw_md = md.raw_markdown or ""
            fit_md = md.fit_markdown or ""
        else:
            raw_md = str(md) if md else ""
            fit_md = ""

        all_images = (result.media or {}).get("images") or []
        candidates = [img for img in all_images if img.get("src", "").startswith("http")]

        if image_filter is not None:
            candidates = [img for img in candidates if image_filter(img)]

        save_dir = Path(output_dir) if output_dir else self._output_dir
        save_dir.mkdir(parents=True, exist_ok=True)

        downloaded: list[Path] = []
        if download_images and candidates:
            downloaded = await self._download_images(
                [img["src"] for img in candidates],
                referer=source_url,
                save_dir=save_dir,
                correlation_id=correlation_id,
            )

        return CrawlResult(
            url=source_url,
            raw_markdown=raw_md,
            fit_markdown=fit_md,
            images=candidates,
            downloaded_images=downloaded,
            crawl_stats=getattr(result, "crawl_stats", {}) or {},
        )

    async def fetch(
        self,
        url: str,
        *,
        correlation_id: str,
        download_images: bool = True,
        output_dir: Path | str | None = None,
        css_selector: str | None = None,
        image_filter: Callable[[dict], bool] | None = None,
        cookies: list[dict] | None = None,
        wait_for: str | None = None,
        headers: dict[str, str] | None = None,
        page_timeout: int | None = None,
        proxy: dict | None = None,
        js_code: list[str] | None = None,
        delay_before_return_html: float | None = None,
        # 모던 옵션 (crawl4ai >= 0.8 권장):
        scan_full_page: bool = False,
        scroll_delay: float | None = None,
        virtual_scroll_config: dict | None = None,
        wait_until: str | None = None,
        simulate_user: bool = False,
        override_navigator: bool = False,
        user_agent: str | None = None,
        user_agent_mode: str | None = None,
        c4a_script: list[str] | None = None,
        exclude_social_media_links: bool = True,
        exclude_external_links: bool | None = None,
        screenshot: bool = False,
        pdf: bool = False,
        max_retries: int = 0,
        session_id: str | None = None,
    ) -> CrawlResult:
        _logger.info(
            "크롤링 시작: %s", url,
            extra={"correlation_id": correlation_id, "service": _SERVICE_NAME},
        )

        run_config = self._build_run_config(
            css_selector=css_selector,
            wait_for=wait_for,
            page_timeout=page_timeout,
            js_code=js_code,
            delay_before_return_html=delay_before_return_html,
            scan_full_page=scan_full_page,
            scroll_delay=scroll_delay,
            virtual_scroll_config=virtual_scroll_config,
            wait_until=wait_until,
            simulate_user=simulate_user,
            override_navigator=override_navigator,
            c4a_script=c4a_script,
            exclude_social_media_links=exclude_social_media_links,
            exclude_external_links=exclude_external_links,
            screenshot=screenshot,
            pdf=pdf,
            proxy_config=proxy if proxy is not None else self._default_proxy,
            max_retries=max_retries,
            session_id=session_id,
        )

        # headers / user_agent / user_agent_mode 는 BrowserConfig 영역. proxy 는 최신 Crawl4AI
        # 권장 방식에 맞춰 CrawlerRunConfig.proxy_config 로 전달한다.
        if headers is not None or user_agent is not None or user_agent_mode is not None:
            browser_config = self._build_browser_config(
                headers=headers if headers is not None else self._default_headers,
                user_agent=user_agent,
                user_agent_mode=user_agent_mode,
            )
        else:
            browser_config = self._browser_config

        arun_kwargs: dict = {"url": url, "config": run_config}
        if cookies is not None:
            arun_kwargs["cookies"] = cookies

        async with AsyncWebCrawler(config=browser_config) as crawler:
            result = await crawler.arun(**arun_kwargs)

        if not result.success:
            _logger.error(
                "크롤링 실패: %s — %s", url, result.error_message,
                extra={"correlation_id": correlation_id, "service": _SERVICE_NAME},
            )
            raise CrawlerException(
                f"크롤링 실패: {result.error_message or 'unknown error'}",
                correlation_id=correlation_id,
                crawl_stats=getattr(result, "crawl_stats", {}) or {},
            )

        _logger.info(
            "크롤링 완료: %s", url,
            extra={"correlation_id": correlation_id, "service": _SERVICE_NAME},
        )

        return await self._to_crawl_result(
            result,
            source_url=url,
            correlation_id=correlation_id,
            download_images=download_images,
            output_dir=output_dir,
            image_filter=image_filter,
        )

    async def fetch_many(
        self,
        urls: list[str],
        *,
        correlation_ids: list[str],
        download_images: bool = True,
        output_dir: Path | str | None = None,
        css_selector: str | None = None,
        image_filter: Callable[[dict], bool] | None = None,
        cookies: list[dict] | None = None,
        wait_for: str | None = None,
        headers: dict[str, str] | None = None,
        page_timeout: int | None = None,
        proxy: dict | None = None,
        js_code: list[str] | None = None,
        delay_before_return_html: float | None = None,
        scan_full_page: bool = False,
        scroll_delay: float | None = None,
        virtual_scroll_config: dict | None = None,
        wait_until: str | None = None,
        simulate_user: bool = False,
        override_navigator: bool = False,
        user_agent: str | None = None,
        user_agent_mode: str | None = None,
        c4a_script: list[str] | None = None,
        exclude_social_media_links: bool = True,
        exclude_external_links: bool | None = None,
        screenshot: bool = False,
        pdf: bool = False,
        max_retries: int = 0,
        concurrency: int = 3,
        rate_limit_delay: tuple[float, float] = (1.0, 2.0),
        stream: bool = True,
    ) -> list[CrawlFetchOutcome]:
        if len(urls) != len(correlation_ids):
            raise ValueError("urls 와 correlation_ids 길이가 같아야 합니다")
        if not urls:
            return []

        _logger.info(
            "배치 크롤링 시작: count=%d concurrency=%d", len(urls), concurrency,
            extra={"correlation_id": "", "service": _SERVICE_NAME},
        )

        run_config = self._build_run_config(
            css_selector=css_selector,
            wait_for=wait_for,
            page_timeout=page_timeout,
            js_code=js_code,
            delay_before_return_html=delay_before_return_html,
            scan_full_page=scan_full_page,
            scroll_delay=scroll_delay,
            virtual_scroll_config=virtual_scroll_config,
            wait_until=wait_until,
            simulate_user=simulate_user,
            override_navigator=override_navigator,
            c4a_script=c4a_script,
            exclude_social_media_links=exclude_social_media_links,
            exclude_external_links=exclude_external_links,
            screenshot=screenshot,
            pdf=pdf,
            proxy_config=proxy if proxy is not None else self._default_proxy,
            max_retries=max_retries,
            stream=stream,
        )
        dispatcher = self._build_dispatcher(
            concurrency=concurrency,
            base_delay=rate_limit_delay,
            max_retries=max_retries,
        )

        if headers is not None or user_agent is not None or user_agent_mode is not None:
            browser_config = self._build_browser_config(
                headers=headers if headers is not None else self._default_headers,
                user_agent=user_agent,
                user_agent_mode=user_agent_mode,
            )
        else:
            browser_config = self._browser_config

        arun_kwargs: dict = {
            "urls": urls,
            "config": run_config,
            "dispatcher": dispatcher,
        }
        if cookies is not None:
            arun_kwargs["cookies"] = cookies

        outcomes: list[CrawlFetchOutcome] = []
        try:
            async with AsyncWebCrawler(config=browser_config) as crawler:
                results = await crawler.arun_many(**arun_kwargs)
                if hasattr(results, "__aiter__"):
                    result_list = [result async for result in results]
                else:
                    result_list = list(results)
        except Exception as exc:
            return [
                CrawlFetchOutcome(url=url, correlation_id=cid, error=exc)
                for url, cid in zip(urls, correlation_ids, strict=True)
            ]

        by_result_url: dict[str, object] = {}
        unassigned_results: list[object] = []
        for result in result_list:
            result_url = getattr(result, "url", None)
            if result_url and result_url in urls and result_url not in by_result_url:
                by_result_url[result_url] = result
            else:
                unassigned_results.append(result)

        for url, cid in zip(urls, correlation_ids, strict=True):
            result = by_result_url.get(url)
            if result is None and unassigned_results:
                result = unassigned_results.pop(0)
            if result is None:
                outcomes.append(
                    CrawlFetchOutcome(
                        url=url,
                        correlation_id=cid,
                        error=CrawlerException(
                            "크롤링 실패: batch result missing",
                            correlation_id=cid,
                        ),
                    )
                )
                continue
            if not result.success:
                outcomes.append(
                    CrawlFetchOutcome(
                        url=url,
                        correlation_id=cid,
                        error=CrawlerException(
                            f"크롤링 실패: {result.error_message or 'unknown error'}",
                            correlation_id=cid,
                            crawl_stats=getattr(result, "crawl_stats", {}) or {},
                        ),
                    )
                )
                continue
            outcomes.append(
                CrawlFetchOutcome(
                    url=url,
                    correlation_id=cid,
                    result=await self._to_crawl_result(
                        result,
                        source_url=url,
                        correlation_id=cid,
                        download_images=download_images,
                        output_dir=output_dir,
                        image_filter=image_filter,
                    ),
                )
            )
        return outcomes

    async def _download_images(
        self,
        urls: list[str],
        *,
        referer: str = "",
        save_dir: Path | None = None,
        correlation_id: str = "",
    ) -> list[Path]:
        saved: list[Path] = []
        parsed = urlparse(referer)
        referer_origin = f"{parsed.scheme}://{parsed.netloc}" if referer else ""

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Referer": referer_origin,
        }
        dest_dir = save_dir if save_dir else self._output_dir
        async with httpx.AsyncClient(timeout=15, follow_redirects=True, headers=headers) as client:
            for i, url in enumerate(urls):
                try:
                    ext = Path(url.split("?")[0]).suffix or ".jpg"
                    dest = dest_dir / f"img_{i:03d}{ext}"
                    resp = await client.get(url)
                    resp.raise_for_status()
                    dest.write_bytes(resp.content)
                    saved.append(dest)
                except Exception as exc:
                    _logger.warning(
                        "이미지 다운로드 실패: %s — %s", url, exc,
                        extra={"correlation_id": correlation_id, "service": _SERVICE_NAME},
                    )
        return saved
