"""Bahamut pagination 진단 스크립트.

두 가지를 확인한다:
  1) requests (JS 없음): page 1 vs page 2 정적 HTML에 C.php 링크가 있는지
  2) Crawl4AI (Playwright): page 2에서 실제로 잡히는 링크 샘플 (처음 30개)

사용:
    cd /Users/jmac/Desktop/261RCOSE45700/crawler
    CRAWL4_AI_BASE_DIRECTORY=../output/_crawl4ai_home \
      ../.venv/bin/python scripts/diag_bahamut_pagination.py
"""
from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import requests  # noqa: E402
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig  # noqa: E402
from crawl4ai.async_configs import CacheMode  # noqa: E402

BOARD_PAGE1 = "https://forum.gamer.com.tw/B.php?bsn=842"
BOARD_PAGE2 = "https://forum.gamer.com.tw/B.php?page=2&bsn=842"
C_PHP_RE = re.compile(r"C\.php\?bsn=\d+&snA=\d+")

HEADERS = {
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}


# ──────────────────────────────────────────────
# 1단계: requests (정적 HTML)
# ──────────────────────────────────────────────
def check_static(url: str, label: str) -> None:
    print(f"\n[requests] {label}")
    print(f"  URL: {url}")
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        print(f"  HTTP {r.status_code}  ({len(r.text):,}자)")
        matches = C_PHP_RE.findall(r.text)
        print(f"  C.php 링크 수: {len(matches)}")
        if matches:
            for m in matches[:5]:
                print(f"    {m}")
        else:
            # 링크가 없으면 첫 줄 일부 출력해서 페이지 내용 확인
            first_lines = r.text[:500].replace("\n", " ")
            print(f"  HTML 앞부분: {first_lines!r}")
    except Exception as e:
        print(f"  ❌ {e}")


# ──────────────────────────────────────────────
# 2단계: Crawl4AI (Playwright) — page 2 링크 샘플
# ──────────────────────────────────────────────
async def check_crawl4ai(url: str, label: str) -> None:
    print(f"\n[Crawl4AI/Playwright] {label}")
    print(f"  URL: {url}")

    cfg = BrowserConfig(
        headless=True,
        enable_stealth=True,
        verbose=False,
        headers=HEADERS,
    )
    run = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        page_timeout=35_000,
    )

    async with AsyncWebCrawler(config=cfg) as crawler:
        res = await crawler.arun(url=url, config=run)

    if not res.success:
        print(f"  ❌ 실패: {res.error_message}")
        return

    internal = (res.links.get("internal") or []) if res.links else []
    external = (res.links.get("external") or []) if res.links else []
    all_links = internal + external
    c_php = [lk for lk in all_links if "C.php" in (lk.get("href") or "")]

    print(f"  HTML {len(res.html or ''):,}자  전체 링크 {len(all_links)}개")
    print(f"  C.php 링크: {len(c_php)}개")

    print(f"\n  링크 샘플 (최대 30개):")
    for lk in all_links[:30]:
        href = lk.get("href") or ""
        text = (lk.get("text") or "").strip()[:30]
        print(f"    {href[:80]}  [{text}]")

    if c_php:
        print(f"\n  C.php 링크 목록:")
        for lk in c_php[:10]:
            print(f"    {lk.get('href')}")


async def main() -> None:
    print("=" * 60)
    print("Bahamut pagination 진단")
    print("=" * 60)

    # 1. requests로 정적 HTML 비교
    check_static(BOARD_PAGE1, "page 1 (정적 HTML)")
    check_static(BOARD_PAGE2, "page 2 (정적 HTML)")

    # 2. Crawl4AI로 page 2 링크 덤프
    await check_crawl4ai(BOARD_PAGE2, "page 2 (Playwright)")


if __name__ == "__main__":
    asyncio.run(main())
