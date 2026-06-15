from crawler.scripts.detail_priority_probe import (
    ProbeCandidate,
    _choose_probe_candidates,
    _can_parallelize_site_group,
    _probe_concurrency_for_site,
    _probe_site_batch,
)
from crawler.src.crawl4ai_crawler import CrawlFetchOutcome, CrawlResult
from shared.exceptions.base_exception import CrawlerException


def _candidate(
    *,
    site_id: str,
    url: str,
    selected: bool,
    bucket: str,
    score: int,
) -> ProbeCandidate:
    return ProbeCandidate(
        site_id=site_id,
        board_url=f"https://example.com/{site_id}",
        url=url,
        title=url.rsplit("/", 1)[-1],
        selected=selected,
        has_title_keywords=False,
        keyword_matched=False,
        score=score,
        priority_bucket=bucket,
        score_reasons=[],
        sample_reason="",
    )


def test_choose_probe_candidates_selected_only_uses_dry_run_selection_and_dedupes():
    candidates = [
        _candidate(
            site_id="ptt_mobile_game",
            url="https://example.com/high",
            selected=True,
            bucket="P2",
            score=30,
        ),
        _candidate(
            site_id="ptt_mobile_game",
            url="https://example.com/high",
            selected=True,
            bucket="P2",
            score=30,
        ),
        _candidate(
            site_id="ptt_mobile_game",
            url="https://example.com/low-selected",
            selected=True,
            bucket="P3",
            score=5,
        ),
        _candidate(
            site_id="bahamut_aion",
            url="https://example.com/unselected",
            selected=False,
            bucket="P2",
            score=50,
        ),
    ]

    chosen = _choose_probe_candidates(candidates, selected_only=True)

    assert [c.url for c in chosen] == [
        "https://example.com/high",
        "https://example.com/low-selected",
    ]
    assert {c.sample_reason for c in chosen} == {"selected_budget"}


def test_choose_probe_candidates_default_probe_can_include_unselected_high_priority():
    candidates = [
        _candidate(
            site_id="bahamut_aion",
            url="https://example.com/unselected-high",
            selected=False,
            bucket="P2",
            score=50,
        ),
        _candidate(
            site_id="ptt_mobile_game",
            url="https://example.com/selected-low",
            selected=True,
            bucket="P3",
            score=5,
        ),
    ]

    chosen = _choose_probe_candidates(candidates, selected_only=False)

    assert chosen[0].url == "https://example.com/unselected-high"
    assert chosen[0].sample_reason == "P2_all"


async def test_probe_site_batch_uses_fetch_many_with_site_options():
    class FakeCrawler:
        def __init__(self) -> None:
            self.calls = []

        async def fetch_many(self, urls, **kwargs):
            self.calls.append((urls, kwargs))
            return [
                CrawlFetchOutcome(
                    url=url,
                    correlation_id=cid,
                    result=CrawlResult(
                        url=url,
                        raw_markdown=(
                            "# 게시글 제목 EXP 1234 / 2000 인벤쪽지 보내기 "
                            "안녕하세요 게임 매크로 다운로드 의심 본문입니다. "
                            "한국어 본문 본문 본문 본문 본문 본문 본문 본문"
                        ),
                        fit_markdown="",
                    ),
                )
                for url, cid in zip(urls, kwargs["correlation_ids"], strict=True)
            ]

    candidates = [
        _candidate(
            site_id="inven_lineage_classic",
            url="https://www.inven.co.kr/board/lineageclassic/6482/1",
            selected=True,
            bucket="P2",
            score=20,
        ),
        _candidate(
            site_id="inven_lineage_classic",
            url="https://www.inven.co.kr/board/lineageclassic/6482/2",
            selected=True,
            bucket="P3",
            score=5,
        ),
    ]
    crawler = FakeCrawler()

    rows = await _probe_site_batch(crawler, "inven_lineage_classic", candidates)

    assert [row["url"] for row in rows] == [c.url for c in candidates]
    assert all(row["ok"] for row in rows)
    assert len(crawler.calls) == 1
    urls, kwargs = crawler.calls[0]
    assert urls == [c.url for c in candidates]
    assert kwargs["download_images"] is False
    assert kwargs["concurrency"] >= 1


def test_probe_concurrency_defaults_keep_sensitive_sources_serial():
    assert _probe_concurrency_for_site("52pojie") == 1
    assert _probe_concurrency_for_site("inven_maple") >= 2


def test_probe_group_parallelism_excludes_sensitive_sources():
    assert _can_parallelize_site_group("52pojie") is False
    assert _can_parallelize_site_group("inven_maple") is True


def test_probe_fast_mode_does_not_override_source_concurrency(monkeypatch):
    from crawler.scripts import detail_priority_probe as probe_module

    monkeypatch.setattr(probe_module, "_PROBE_FAST_MODE", True)
    monkeypatch.setattr(probe_module, "_PROBE_CONCURRENCY", 3)
    monkeypatch.setattr(probe_module, "_PROBE_SOURCE_CONCURRENCY_OVERRIDES", {})

    assert probe_module._probe_concurrency_for_site("inven_maple") >= 2
    assert probe_module._probe_concurrency_for_site("52pojie") == 1


async def test_probe_site_batch_keeps_sensitive_source_on_single_fetch_path():
    class FakeCrawler:
        def __init__(self) -> None:
            self.fetch_calls = []
            self.fetch_many_calls = []

        async def fetch(self, url, **kwargs):
            self.fetch_calls.append((url, kwargs))
            return CrawlResult(
                url=url,
                raw_markdown="52pojie 게시글 본문입니다. " * 20,
                fit_markdown="52pojie 게시글 본문입니다. " * 20,
            )

        async def fetch_many(self, urls, **kwargs):
            self.fetch_many_calls.append((urls, kwargs))
            return []

    candidates = [
        _candidate(
            site_id="52pojie",
            url="https://www.52pojie.cn/thread-1-1-1.html",
            selected=True,
            bucket="P3",
            score=5,
        ),
        _candidate(
            site_id="52pojie",
            url="https://www.52pojie.cn/thread-2-1-1.html",
            selected=True,
            bucket="P3",
            score=5,
        ),
    ]
    crawler = FakeCrawler()

    rows = await _probe_site_batch(crawler, "52pojie", candidates)

    assert len(rows) == 2
    assert len(crawler.fetch_calls) == 2
    assert crawler.fetch_many_calls == []


async def test_probe_site_batch_can_apply_source_cooldown(monkeypatch):
    from crawler.scripts import detail_priority_probe as probe_module

    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(probe_module, "_DELAY_SECONDS", 0.0)
    monkeypatch.setattr(probe_module, "_PROBE_SOURCE_COOLDOWN_SECONDS", 7.0)
    monkeypatch.setattr(probe_module, "_PROBE_SOURCE_COOLDOWN_SOURCES", {"52pojie"})
    monkeypatch.setattr(probe_module, "_PROBE_CHALLENGE_COOLDOWN_SECONDS", 0.0)
    monkeypatch.setattr(probe_module.asyncio, "sleep", fake_sleep)

    class FakeCrawler:
        async def fetch(self, url, **kwargs):
            return CrawlResult(
                url=url,
                raw_markdown="52pojie 게시글 본문입니다. " * 20,
                fit_markdown="52pojie 게시글 본문입니다. " * 20,
            )

    candidates = [
        _candidate(
            site_id="52pojie",
            url="https://www.52pojie.cn/thread-1-1-1.html",
            selected=True,
            bucket="P3",
            score=5,
        ),
        _candidate(
            site_id="52pojie",
            url="https://www.52pojie.cn/thread-2-1-1.html",
            selected=True,
            bucket="P3",
            score=5,
        ),
    ]

    rows = await _probe_site_batch(FakeCrawler(), "52pojie", candidates)

    assert len(rows) == 2
    assert sleeps == [7.0]


async def test_probe_site_batch_can_apply_challenge_cooldown(monkeypatch):
    from crawler.scripts import detail_priority_probe as probe_module

    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(probe_module, "_DELAY_SECONDS", 0.0)
    monkeypatch.setattr(probe_module, "_PROBE_SOURCE_COOLDOWN_SECONDS", 0.0)
    monkeypatch.setattr(probe_module, "_PROBE_SOURCE_COOLDOWN_SOURCES", {"52pojie"})
    monkeypatch.setattr(probe_module, "_PROBE_CHALLENGE_COOLDOWN_SECONDS", 11.0)
    monkeypatch.setattr(probe_module, "_PROBE_CLOUDFLARE_BACKOFF_RETRIES", 0)
    monkeypatch.setattr(probe_module.asyncio, "sleep", fake_sleep)

    class FakeCrawler:
        def __init__(self) -> None:
            self.calls = 0

        async def fetch(self, url, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise CrawlerException(
                    "크롤링 실패: Blocked by anti-bot protection: Cloudflare JS challenge"
                )
            return CrawlResult(
                url=url,
                raw_markdown="52pojie 게시글 본문입니다. " * 20,
                fit_markdown="52pojie 게시글 본문입니다. " * 20,
            )

    candidates = [
        _candidate(
            site_id="52pojie",
            url="https://www.52pojie.cn/thread-1-1-1.html",
            selected=True,
            bucket="P3",
            score=5,
        ),
        _candidate(
            site_id="52pojie",
            url="https://www.52pojie.cn/thread-2-1-1.html",
            selected=True,
            bucket="P3",
            score=5,
        ),
    ]

    rows = await _probe_site_batch(FakeCrawler(), "52pojie", candidates)

    assert rows[0]["ok"] is False
    assert rows[1]["ok"] is True
    assert sleeps == [11.0]
