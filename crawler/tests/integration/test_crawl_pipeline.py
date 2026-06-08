"""CrawlPipeline 통합 테스트.

외부 Redis / S3 / 브라우저 호출 없이 mock 으로 파이프라인 전체 흐름을 검증한다.
"""
from __future__ import annotations

import asyncio
import contextlib
from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from crawler.src.crawl4ai_crawler import CrawlFetchOutcome, CrawlResult
from crawler.src.preprocessor.dedup_checker import DedupChecker
from crawler.src.queue.redis_publisher import RedisPublisher
from crawler.src.scheduler.crawl_scheduler import (
    CrawlPipeline,
    CrawlOptions,
    ListingResult,
    PostUrlCandidate,
    detail_fetch_concurrency_for_site,
    _extract_post_url_candidates,
    _select_detail_candidates,
)
from crawler.src.scheduler import crawl_scheduler as scheduler_module
from crawler.src.sites.registry import SITES
from crawler.src.storage import StorageResult
from shared.exceptions.base_exception import CrawlerException
from shared.models.crawl_event import CrawlEvent

# validator 는 inven 마커(EXP / 인벤쪽지) + 50자 이상을 요구.
# 후속 langdetect 가 'ko' 로 잡히도록 한국어 비중 충분히 유지.
_KEYWORD_TEXT = (
    "# 게시글 제목 EXP 1234 / 2000 인벤쪽지 보내기 "
    "안녕하세요 오늘 게임 사냥터 추천 게시글입니다. 본문 본문 본문 "
    "이 정도면 검증과 언어 감지 둘 다 통과할 만한 한국어 텍스트가 됩니다."
)
_TEST_URL = "https://www.inven.co.kr/board/maple/2298/123"
_TEST_URL2 = "https://www.inven.co.kr/board/maple/2298/456"
_TEST_URL3 = "https://www.inven.co.kr/board/maple/2298/789"


def _make_crawl_result(text: str = _KEYWORD_TEXT) -> CrawlResult:
    return CrawlResult(
        url=_TEST_URL,
        raw_markdown=text,
        fit_markdown=text,
        images=[],
        downloaded_images=[],
    )


@contextlib.contextmanager
def _isolated_sites():
    """단일 사이트(inven_maple)만 활성화한 상태로 패치 — site fanout 으로 인한 lpush 다중 호출 방지."""
    inven = _single_page_site(SITES["inven_maple"])
    with patch(
        "crawler.src.scheduler.crawl_scheduler.get_enabled_sites",
        return_value={"inven_maple": inven},
    ):
        yield


def _single_page_site(site):
    """기존 pipeline 단위 테스트는 페이지네이션이 아닌 post 처리 1회를 검증한다."""
    return replace(site, max_pages=1, page_url_template=None, prev_page_link_text=None)


def _make_pipeline(
    *,
    crawl_result: CrawlResult | None = None,
    is_duplicate: bool = False,
    s3_text_path: str = "",
) -> tuple[CrawlPipeline, MagicMock, MagicMock]:
    if crawl_result is None:
        crawl_result = _make_crawl_result()

    mock_crawler = AsyncMock()
    mock_crawler.fetch.return_value = crawl_result
    mock_crawler.fetch_many = None

    mock_redis_dedup = MagicMock()
    mock_redis_dedup.sismember.return_value = 1 if is_duplicate else 0
    mock_redis_dedup.sadd = MagicMock()

    mock_redis_mq = MagicMock()
    mock_redis_mq.lpush = MagicMock()

    mock_storage = MagicMock()
    mock_storage.save.return_value = StorageResult(
        local_path=Path("/tmp/test"),
        s3_text_path=s3_text_path,
        s3_image_paths=[],
    )

    pipeline = CrawlPipeline(
        crawler=mock_crawler,
        storage=mock_storage,
        dedup=DedupChecker(mock_redis_dedup),
        publisher=RedisPublisher(mock_redis_mq),
    )
    return pipeline, mock_redis_mq, mock_redis_dedup


class _SetBackedRedis:
    def __init__(self) -> None:
        self.values: set[str] = set()

    def sismember(self, _key: str, value: str) -> int:
        return 1 if value in self.values else 0

    def sadd(self, _key: str, value: str) -> int:
        before = len(self.values)
        self.values.add(value)
        return len(self.values) - before


async def test_pipeline_enqueues_post():
    """비중복·비빈 게시글은 posts:queue에 LPUSH된다."""
    pipeline, mock_mq, _ = _make_pipeline(crawl_result=_make_crawl_result(_KEYWORD_TEXT))

    with _isolated_sites(), patch(
        "crawler.src.scheduler.crawl_scheduler._fetch_post_urls",
        return_value=ListingResult(urls=[_TEST_URL], discovered_total=1, keyword_matched=0, keyword_unmatched=1),
    ):
        stats = await pipeline.run()

    assert stats.enqueued == 1
    assert stats.listing_boards == 1
    assert stats.listing_urls_selected == 1
    assert stats.attempted == 1
    assert stats.skipped_dedup == 0
    assert stats.skipped_empty == 0
    mock_mq.lpush.assert_called_once()
    assert mock_mq.lpush.call_args[0][0] == "posts:queue"


async def test_pipeline_skips_duplicate_post():
    """중복 게시글(dedup 히트)은 LPUSH 없이 건너뛴다."""
    pipeline, mock_mq, _ = _make_pipeline(
        crawl_result=_make_crawl_result(_KEYWORD_TEXT),
        is_duplicate=True,
    )

    with _isolated_sites(), patch(
        "crawler.src.scheduler.crawl_scheduler._fetch_post_urls",
        return_value=ListingResult(urls=[_TEST_URL], discovered_total=1, keyword_matched=0, keyword_unmatched=1),
    ):
        stats = await pipeline.run()

    assert stats.enqueued == 0
    assert stats.skipped_dedup == 1
    mock_mq.lpush.assert_not_called()


async def test_pipeline_skips_empty_post():
    """raw/fit 모두 비어있는 게시글은 LPUSH 없이 건너뛴다 (큐 오염 방지)."""
    empty_result = CrawlResult(
        url=_TEST_URL, raw_markdown="", fit_markdown="   ",
        images=[], downloaded_images=[],
    )
    pipeline, mock_mq, _ = _make_pipeline(crawl_result=empty_result)

    with _isolated_sites(), patch(
        "crawler.src.scheduler.crawl_scheduler._fetch_post_urls",
        return_value=ListingResult(urls=[_TEST_URL], discovered_total=1, keyword_matched=0, keyword_unmatched=1),
    ):
        stats = await pipeline.run()

    assert stats.enqueued == 0
    assert stats.skipped_empty == 1
    mock_mq.lpush.assert_not_called()


async def test_pipeline_uses_raw_markdown_when_fit_empty():
    """fit_markdown 이 비어도 raw_markdown 이 있으면 실제 글로 처리한다."""
    raw_only_result = CrawlResult(
        url=_TEST_URL,
        raw_markdown=_KEYWORD_TEXT,
        fit_markdown="",
        images=[],
        downloaded_images=[],
    )
    pipeline, mock_mq, mock_dedup = _make_pipeline(crawl_result=raw_only_result)

    with _isolated_sites(), patch(
        "crawler.src.scheduler.crawl_scheduler._fetch_post_urls",
        return_value=ListingResult(urls=[_TEST_URL], discovered_total=1, keyword_matched=0, keyword_unmatched=1),
    ):
        stats = await pipeline.run()

    assert stats.enqueued == 1
    assert stats.skipped_empty == 0
    mock_mq.lpush.assert_called_once()
    mock_dedup.sadd.assert_called_once()
    assert mock_dedup.sadd.call_args[0][1]


async def test_pipeline_individual_failure_continues():
    """개별 게시글 크롤 실패 시 예외 로그 후 다음 게시글로 진행한다."""
    mock_crawler = AsyncMock()
    mock_crawler.fetch.side_effect = Exception("크롤 실패")
    mock_crawler.fetch_many = None

    mock_redis_dedup = MagicMock()
    mock_redis_dedup.sismember.return_value = 0

    mock_redis_mq = MagicMock()

    pipeline = CrawlPipeline(
        crawler=mock_crawler,
        storage=MagicMock(),
        dedup=DedupChecker(mock_redis_dedup),
        publisher=RedisPublisher(mock_redis_mq),
    )

    with _isolated_sites(), patch(
        "crawler.src.scheduler.crawl_scheduler._fetch_post_urls",
        return_value=ListingResult(
            urls=[_TEST_URL, _TEST_URL2],
            discovered_total=2,
            keyword_matched=0,
            keyword_unmatched=2,
            candidates=[
                PostUrlCandidate(_TEST_URL, "macro loader download", False),
                PostUrlCandidate(_TEST_URL2, "cheat bypass discord", False),
            ],
        ),
    ):
        stats = await pipeline.run()

    assert stats.failed == 2
    assert stats.attempted == 2
    mock_redis_mq.lpush.assert_not_called()


async def test_pipeline_fetches_details_with_bounded_concurrency():
    """상세 fetch 는 bounded concurrency 로 병렬화하되 전체 후처리는 완료된다."""
    active = 0
    max_active = 0

    async def fetch_side_effect(url: str, **_kwargs):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0.01)
        active -= 1
        return _make_crawl_result(_KEYWORD_TEXT + f" 고유 본문 {url}")

    mock_crawler = AsyncMock()
    mock_crawler.fetch.side_effect = fetch_side_effect
    mock_crawler.fetch_many = None
    mock_mq = MagicMock()
    fake_redis = _SetBackedRedis()
    pipeline = CrawlPipeline(
        crawler=mock_crawler,
        storage=MagicMock(save=MagicMock(return_value=StorageResult(
            local_path=Path("/tmp/test"),
            s3_text_path="",
            s3_image_paths=[],
        ))),
        dedup=DedupChecker(fake_redis),  # type: ignore[arg-type]
        publisher=RedisPublisher(mock_mq),
    )

    listing = ListingResult(
        urls=[],
        discovered_total=3,
        keyword_matched=0,
        keyword_unmatched=3,
        candidates=[
            PostUrlCandidate(_TEST_URL, "매크로 loader download", False),
            PostUrlCandidate(_TEST_URL2, "discord cheat bypass", False),
            PostUrlCandidate(_TEST_URL3, "undetected macro tool", False),
        ],
    )

    with _isolated_sites(), patch(
        "crawler.src.scheduler.crawl_scheduler._DETAIL_FETCH_CONCURRENCY", 2,
    ), patch(
        "crawler.src.scheduler.crawl_scheduler._DETAIL_FETCH_STAGGER_SECONDS", 0.0,
    ), patch(
        "crawler.src.scheduler.crawl_scheduler._fetch_post_urls",
        return_value=listing,
    ):
        stats = await pipeline.run()

    assert max_active == 2
    assert stats.attempted == 3
    assert stats.enqueued == 3
    assert mock_mq.lpush.call_count == 3


async def test_pipeline_parallel_fetch_preserves_sequential_body_dedup():
    """fetch 는 병렬이어도 본문 dedup/queue 발행은 순차 처리해 중복 enqueue 를 막는다."""
    mock_crawler = AsyncMock()
    mock_crawler.fetch.return_value = _make_crawl_result(_KEYWORD_TEXT)
    mock_crawler.fetch_many = None
    mock_mq = MagicMock()
    fake_redis = _SetBackedRedis()
    pipeline = CrawlPipeline(
        crawler=mock_crawler,
        storage=MagicMock(save=MagicMock(return_value=StorageResult(
            local_path=Path("/tmp/test"),
            s3_text_path="",
            s3_image_paths=[],
        ))),
        dedup=DedupChecker(fake_redis),  # type: ignore[arg-type]
        publisher=RedisPublisher(mock_mq),
    )

    listing = ListingResult(
        urls=[],
        discovered_total=2,
        keyword_matched=0,
        keyword_unmatched=2,
        candidates=[
            PostUrlCandidate(_TEST_URL, "매크로 loader download", False),
            PostUrlCandidate(_TEST_URL2, "discord cheat bypass", False),
        ],
    )

    with _isolated_sites(), patch(
        "crawler.src.scheduler.crawl_scheduler._DETAIL_FETCH_CONCURRENCY", 2,
    ), patch(
        "crawler.src.scheduler.crawl_scheduler._DETAIL_FETCH_STAGGER_SECONDS", 0.0,
    ), patch(
        "crawler.src.scheduler.crawl_scheduler._fetch_post_urls",
        return_value=listing,
    ):
        stats = await pipeline.run()

    assert stats.attempted == 2
    assert stats.enqueued == 1
    assert stats.skipped_dedup == 1
    mock_mq.lpush.assert_called_once()


async def test_pipeline_uses_crawler_fetch_many_when_available():
    """실제 Crawl4AICrawler 래퍼가 있으면 상세 fetch 는 arun_many 기반 batch 경로를 탄다."""
    mock_crawler = AsyncMock()
    mock_crawler.fetch_many = AsyncMock(return_value=[
        CrawlFetchOutcome(
            url=_TEST_URL,
            correlation_id="cid-1",
            result=_make_crawl_result(_KEYWORD_TEXT + " 첫 번째"),
        ),
        CrawlFetchOutcome(
            url=_TEST_URL2,
            correlation_id="cid-2",
            result=_make_crawl_result(_KEYWORD_TEXT + " 두 번째"),
        ),
    ])
    mock_mq = MagicMock()
    fake_redis = _SetBackedRedis()
    pipeline = CrawlPipeline(
        crawler=mock_crawler,
        storage=MagicMock(save=MagicMock(return_value=StorageResult(
            local_path=Path("/tmp/test"),
            s3_text_path="",
            s3_image_paths=[],
        ))),
        dedup=DedupChecker(fake_redis),  # type: ignore[arg-type]
        publisher=RedisPublisher(mock_mq),
    )

    listing = ListingResult(
        urls=[],
        discovered_total=2,
        keyword_matched=0,
        keyword_unmatched=2,
        candidates=[
            PostUrlCandidate(_TEST_URL, "매크로 loader download", False),
            PostUrlCandidate(_TEST_URL2, "discord cheat bypass", False),
        ],
    )

    with _isolated_sites(), patch(
        "crawler.src.scheduler.crawl_scheduler._DETAIL_FETCH_CONCURRENCY", 2,
    ), patch(
        "crawler.src.scheduler.crawl_scheduler._DETAIL_FETCH_STAGGER_SECONDS", 0.1,
    ), patch(
        "crawler.src.scheduler.crawl_scheduler._fetch_post_urls",
        return_value=listing,
    ):
        stats = await pipeline.run()

    mock_crawler.fetch.assert_not_called()
    mock_crawler.fetch_many.assert_called_once()
    kwargs = mock_crawler.fetch_many.call_args.kwargs
    assert kwargs["concurrency"] == 2
    assert kwargs["rate_limit_delay"] == (0.1, 0.2)
    assert stats.enqueued == 2
    assert mock_mq.lpush.call_count == 2


def test_detail_fetch_concurrency_defaults_keep_dcard_serial():
    """Dcard/52pojie는 concurrency=3 실측에서 차단 위험이 커 기본 순차 처리한다."""
    assert detail_fetch_concurrency_for_site("dcard") == 1
    assert detail_fetch_concurrency_for_site("dcard_online") == 1
    assert detail_fetch_concurrency_for_site("52pojie") == 1
    assert detail_fetch_concurrency_for_site("inven_maple") >= 2


async def test_pipeline_keeps_dcard_serial_even_when_fetch_many_available():
    """Dcard는 fetch_many가 있어도 source override 때문에 순차 fetch로 처리한다."""
    dcard_site = replace(SITES["dcard"], max_pages=1)
    mock_crawler = AsyncMock()
    mock_crawler.fetch.return_value = CrawlResult(
        url="https://www.dcard.tw/f/game/p/1",
        raw_markdown="Dcard 본문입니다. " * 20,
        fit_markdown="Dcard 본문입니다. " * 20,
        images=[],
        downloaded_images=[],
    )
    mock_crawler.fetch_many = AsyncMock()
    mock_mq = MagicMock()
    fake_redis = _SetBackedRedis()
    pipeline = CrawlPipeline(
        crawler=mock_crawler,
        storage=MagicMock(save=MagicMock(return_value=StorageResult(
            local_path=Path("/tmp/test"),
            s3_text_path="",
            s3_image_paths=[],
        ))),
        dedup=DedupChecker(fake_redis),  # type: ignore[arg-type]
        publisher=RedisPublisher(mock_mq),
    )
    listing = ListingResult(
        urls=[],
        discovered_total=2,
        keyword_matched=0,
        keyword_unmatched=2,
        candidates=[
            PostUrlCandidate("https://www.dcard.tw/f/game/p/1", "잡담 1", False),
            PostUrlCandidate("https://www.dcard.tw/f/game/p/2", "잡담 2", False),
        ],
    )

    with patch(
        "crawler.src.scheduler.crawl_scheduler.get_enabled_sites",
        return_value={"dcard": dcard_site},
    ), patch(
        "crawler.src.scheduler.crawl_scheduler._fetch_post_urls",
        return_value=listing,
    ):
        await pipeline.run()

    mock_crawler.fetch_many.assert_not_called()
    assert mock_crawler.fetch.call_count == 2


async def test_pipeline_can_apply_dcard_source_cooldown_between_serial_fetches():
    """옵션을 켜면 Dcard 상세 요청 사이에 source-level cooldown을 둔다."""
    dcard_site = replace(SITES["dcard"], max_pages=1)
    mock_crawler = AsyncMock()
    mock_crawler.fetch.side_effect = [
        CrawlResult(
            url="https://www.dcard.tw/f/game/p/1",
            raw_markdown="Dcard 첫 번째 본문입니다. " * 20,
            fit_markdown="Dcard 첫 번째 본문입니다. " * 20,
            images=[],
            downloaded_images=[],
        ),
        CrawlResult(
            url="https://www.dcard.tw/f/game/p/2",
            raw_markdown="Dcard 두 번째 본문입니다. " * 20,
            fit_markdown="Dcard 두 번째 본문입니다. " * 20,
            images=[],
            downloaded_images=[],
        ),
    ]
    mock_crawler.fetch_many = AsyncMock()
    mock_mq = MagicMock()
    fake_redis = _SetBackedRedis()
    pipeline = CrawlPipeline(
        crawler=mock_crawler,
        storage=MagicMock(save=MagicMock(return_value=StorageResult(
            local_path=Path("/tmp/test"),
            s3_text_path="",
            s3_image_paths=[],
        ))),
        dedup=DedupChecker(fake_redis),  # type: ignore[arg-type]
        publisher=RedisPublisher(mock_mq),
    )
    listing = ListingResult(
        urls=[],
        discovered_total=2,
        keyword_matched=0,
        keyword_unmatched=2,
        candidates=[
            PostUrlCandidate("https://www.dcard.tw/f/game/p/1", "잡담 1", False),
            PostUrlCandidate("https://www.dcard.tw/f/game/p/2", "잡담 2", False),
        ],
    )
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    with patch(
        "crawler.src.scheduler.crawl_scheduler.get_enabled_sites",
        return_value={"dcard": dcard_site},
    ), patch(
        "crawler.src.scheduler.crawl_scheduler._fetch_post_urls",
        return_value=listing,
    ), patch.object(
        scheduler_module,
        "_DETAIL_SOURCE_COOLDOWN_SECONDS",
        9.0,
    ), patch.object(
        scheduler_module,
        "_DETAIL_SOURCE_COOLDOWN_SOURCES",
        {"dcard"},
    ), patch.object(
        scheduler_module.asyncio,
        "sleep",
        side_effect=fake_sleep,
    ):
        await pipeline.run()

    mock_crawler.fetch_many.assert_not_called()
    assert mock_crawler.fetch.call_count == 2
    assert sleeps == [9.0]


async def test_fetch_post_can_backoff_retry_cloudflare_challenge_for_dcard():
    pipeline, _, _ = _make_pipeline(crawl_result=_make_crawl_result(_KEYWORD_TEXT))
    mock_crawler = pipeline._crawler
    mock_crawler.fetch.side_effect = [
        CrawlerException(
            "크롤링 실패: Blocked by anti-bot protection: Cloudflare JS challenge"
        ),
        _make_crawl_result(_KEYWORD_TEXT),
    ]

    with patch.object(scheduler_module, "_DETAIL_CLOUDFLARE_BACKOFF_RETRIES", 1), patch.object(
        scheduler_module,
        "_DETAIL_CLOUDFLARE_BACKOFF_SECONDS",
        0.0,
    ), patch.object(
        scheduler_module,
        "_DETAIL_CLOUDFLARE_BACKOFF_SOURCES",
        {"dcard", "dcard_online"},
    ):
        outcome = await pipeline._fetch_post(
            "dcard",
            "https://www.dcard.tw/f/game/p/1",
            "cid-dcard",
            CrawlOptions.from_site(SITES["dcard"]),
        )

    assert outcome.error is None
    assert outcome.result is not None
    assert mock_crawler.fetch.call_count == 2


async def test_pipeline_s3_paths_propagated_to_event():
    """PostStorage의 s3_text_path가 CrawlEvent에 전파된다."""
    s3_path = "s3://my-bucket/raw/inven_maple/2026-04-28/123.md"
    pipeline, mock_mq, _ = _make_pipeline(
        crawl_result=_make_crawl_result(_KEYWORD_TEXT),
        s3_text_path=s3_path,
    )

    with _isolated_sites(), patch(
        "crawler.src.scheduler.crawl_scheduler._fetch_post_urls",
        return_value=ListingResult(urls=[_TEST_URL], discovered_total=1, keyword_matched=0, keyword_unmatched=1),
    ):
        await pipeline.run()

    mock_mq.lpush.assert_called_once()
    event_json = mock_mq.lpush.call_args[0][1]
    event = CrawlEvent.from_json(event_json)
    assert event.s3_text_path == s3_path


async def test_pipeline_event_json_roundtrip():
    """LPUSH된 CrawlEvent JSON이 from_json()으로 역직렬화된다 (스키마 정합성)."""
    pipeline, mock_mq, _ = _make_pipeline(crawl_result=_make_crawl_result(_KEYWORD_TEXT))

    with _isolated_sites(), patch(
        "crawler.src.scheduler.crawl_scheduler._fetch_post_urls",
        return_value=ListingResult(urls=[_TEST_URL], discovered_total=1, keyword_matched=0, keyword_unmatched=1),
    ):
        stats = await pipeline.run()

    assert stats.enqueued == 1
    event_json = mock_mq.lpush.call_args[0][1]

    event = CrawlEvent.from_json(event_json)
    assert event.site_name == "인벤 (메이플스토리)"
    assert event.source_id == "inven_maple"
    assert event.language in {"ko", "zh-CN", "zh-TW"}
    assert isinstance(event.image_urls, list)
    assert event.s3_text_path == ""


async def test_pipeline_passes_title_keywords_to_url_extractor():
    """site.title_keywords 가 listing options 로 전달되는지."""
    custom_site = _single_page_site(replace(
        SITES["inven_maple"],
        title_keywords=["天堂", "Lineage", "리니지"],
    ))

    pipeline, _, _ = _make_pipeline(crawl_result=_make_crawl_result(_KEYWORD_TEXT))

    with patch(
        "crawler.src.scheduler.crawl_scheduler.get_enabled_sites",
        return_value={"inven_maple": custom_site},
    ), patch(
        "crawler.src.scheduler.crawl_scheduler._fetch_post_urls",
        return_value=ListingResult(urls=[_TEST_URL], discovered_total=1, keyword_matched=0, keyword_unmatched=1),
    ) as mock_fpu:
        await pipeline.run()

    options = mock_fpu.call_args.kwargs["options"]
    assert options.title_keywords == ["天堂", "Lineage", "리니지"]


def test_listing_keywords_prioritize_without_filtering_candidates():
    """혼합 보드 제목 키워드는 hard filter 가 아니라 우선순위로만 동작한다."""
    links = [
        {"href": "https://example.com/post/101", "text": "잡담 글"},
        {"href": "https://example.com/post/102", "text": "Lineage 매크로 의심"},
        {"href": "https://example.com/post/103", "text": "다른 게임 거래"},
    ]

    candidates = _extract_post_url_candidates(
        links,
        r"https://example\.com/post/\d+$",
        title_keywords=["Lineage"],
    )

    assert [c.url for c in candidates] == [
        "https://example.com/post/102",
        "https://example.com/post/103",
        "https://example.com/post/101",
    ]
    assert [c.keyword_matched for c in candidates] == [True, False, False]


def test_priority_budget_selects_high_priority_and_caps_p3_for_mixed_source():
    """운영 budget은 P0/P1/P2를 우선 선택하고 P3는 혼합 보드 cap만큼만 샘플링한다."""
    site = replace(SITES["dcard"], title_keywords=["Lineage"])
    listing = ListingResult(
        urls=[],
        discovered_total=8,
        keyword_matched=0,
        keyword_unmatched=8,
        candidates=[
            PostUrlCandidate(
                url=f"https://www.dcard.tw/f/game/p/{idx}",
                title=title,
                keyword_matched=False,
            )
            for idx, title in enumerate([
                "undetected cheat loader download",
                "discord macro bypass",
                "잡담 1",
                "잡담 2",
                "잡담 3",
                "잡담 4",
                "잡담 5",
                "잡담 6",
            ], start=1)
        ],
    )

    selected = _select_detail_candidates(
        site_id="dcard",
        board_url="https://www.dcard.tw/f/game",
        listing=listing,
        site=site,
        limit=30,
    )

    assert sum(1 for c in selected if c.priority_bucket != "P3") == 2
    assert [c.priority_bucket for c in selected].count("P3") == 5
    assert len(selected) == 7


def test_priority_budget_keeps_52pojie_p3_cap_low():
    """52pojie는 source risk만으로 전수 fetch하지 않고 P3 cap을 낮게 유지한다."""
    site = SITES["52pojie"]
    listing = ListingResult(
        urls=[],
        discovered_total=6,
        keyword_matched=0,
        keyword_unmatched=6,
        candidates=[
            PostUrlCandidate(
                url=f"https://www.52pojie.cn/thread-{idx}-1-1.html",
                title=f"普通讨论 {idx}",
                keyword_matched=False,
            )
            for idx in range(1, 7)
        ],
    )

    selected = _select_detail_candidates(
        site_id="52pojie",
        board_url="https://www.52pojie.cn/forum-16-2.html",
        listing=listing,
        site=site,
        limit=30,
    )

    assert len(selected) == 1
    assert {c.priority_bucket for c in selected} == {"P3"}


async def test_pipeline_skips_already_seen_url_before_fetch():
    """UrlDedupChecker.has_seen 이 True 면 fetch 자체를 안 함."""
    from crawler.src.preprocessor.url_dedup_checker import UrlDedupChecker

    mock_url_dedup = MagicMock(spec=UrlDedupChecker)
    mock_url_dedup.has_seen.return_value = True   # 이미 본 URL 시뮬

    pipeline, _, _ = _make_pipeline(crawl_result=_make_crawl_result(_KEYWORD_TEXT))
    pipeline._url_dedup = mock_url_dedup
    mock_crawler = pipeline._crawler

    with _isolated_sites(), patch(
        "crawler.src.scheduler.crawl_scheduler._fetch_post_urls",
        return_value=ListingResult(urls=[_TEST_URL], discovered_total=1, keyword_matched=0, keyword_unmatched=1),
    ):
        stats = await pipeline.run()

    # fetch 호출이 한 번도 없어야 한다 (URL 이 이미 처리됨).
    mock_crawler.fetch.assert_not_called()
    assert stats.skipped_seen_url == 1
    assert stats.attempted == 0     # has_seen=True 면 attempted 도 증가 안 함


async def test_pipeline_marks_seen_url_after_successful_enqueue():
    """성공 enqueue 후 UrlDedupChecker.mark_seen 호출 — 다음 run 재처리 방지."""
    from crawler.src.preprocessor.url_dedup_checker import UrlDedupChecker

    mock_url_dedup = MagicMock(spec=UrlDedupChecker)
    mock_url_dedup.has_seen.return_value = False

    pipeline, _, _ = _make_pipeline(crawl_result=_make_crawl_result(_KEYWORD_TEXT))
    pipeline._url_dedup = mock_url_dedup

    with _isolated_sites(), patch(
        "crawler.src.scheduler.crawl_scheduler._fetch_post_urls",
        return_value=ListingResult(urls=[_TEST_URL], discovered_total=1, keyword_matched=0, keyword_unmatched=1),
    ):
        await pipeline.run()

    mock_url_dedup.mark_seen.assert_called_once()
    assert mock_url_dedup.mark_seen.call_args.args[0] == _TEST_URL


async def test_pipeline_passes_site_options_to_crawler_fetch():
    """site.cookies / wait_for / headers / page_timeout / proxy 가 crawler.fetch 로 전달되는지."""
    custom_site = SITES["inven_maple"]
    custom_site = _single_page_site(replace(
        custom_site,
        cookies=[{"name": "session", "value": "abc"}],
        wait_for="css:.foo",
        headers={"Accept-Language": "ko"},
        page_timeout=33_000,
        proxy={"server": "http://p.example:8080"},
        max_retries=2,
        override_navigator=True,
    ))

    pipeline, _, _ = _make_pipeline(crawl_result=_make_crawl_result(_KEYWORD_TEXT))
    mock_crawler = pipeline._crawler  # AsyncMock from helper

    with patch(
        "crawler.src.scheduler.crawl_scheduler.get_enabled_sites",
        return_value={"inven_maple": custom_site},
    ), patch(
        "crawler.src.scheduler.crawl_scheduler._fetch_post_urls",
        return_value=ListingResult(urls=[_TEST_URL], discovered_total=1, keyword_matched=0, keyword_unmatched=1),
    ):
        await pipeline.run()

    mock_crawler.fetch.assert_called_once()
    kwargs = mock_crawler.fetch.call_args.kwargs
    assert kwargs["cookies"] == [{"name": "session", "value": "abc"}]
    assert kwargs["wait_for"] == "css:.foo"
    assert kwargs["headers"] == {"Accept-Language": "ko"}
    assert kwargs["page_timeout"] == 33_000
    assert kwargs["proxy"] == {"server": "http://p.example:8080"}
    assert kwargs["max_retries"] == 2
    assert kwargs["override_navigator"] is True


async def test_pipeline_dedup_mark_seen_called_after_enqueue():
    """LPUSH 성공 후 dedup mark_seen(sadd)이 호출되며, 호출 순서를 보장한다 (Anti-Pattern #6)."""
    call_log: list[str] = []

    pipeline, mock_mq, mock_redis_dedup = _make_pipeline(
        crawl_result=_make_crawl_result(_KEYWORD_TEXT)
    )
    mock_mq.lpush.side_effect = lambda *a, **kw: call_log.append("lpush")
    mock_redis_dedup.sadd.side_effect = lambda *a, **kw: call_log.append("sadd")

    with _isolated_sites(), patch(
        "crawler.src.scheduler.crawl_scheduler._fetch_post_urls",
        return_value=ListingResult(urls=[_TEST_URL], discovered_total=1, keyword_matched=0, keyword_unmatched=1),
    ):
        await pipeline.run()

    mock_mq.lpush.assert_called_once()
    mock_redis_dedup.sadd.assert_called_once()
    assert call_log == ["lpush", "sadd"], (
        f"Anti-Pattern #6: mark_seen 은 LPUSH 이후에 호출되어야 함. 실제 순서: {call_log}"
    )
