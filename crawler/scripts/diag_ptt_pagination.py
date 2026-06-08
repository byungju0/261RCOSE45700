"""PTT pagination 구조 진단.

PTT URL: index.html, index{N-1}.html, index{N-2}.html ...
이전 페이지 링크(上頁)의 href 구조와 M.* 링크 수 확인.

사용:
    cd /Users/jmac/Desktop/261RCOSE45700/crawler
    CRAWL4_AI_BASE_DIRECTORY=../output/_crawl4ai_home \
      ../.venv/bin/python scripts/diag_ptt_pagination.py
"""
from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
from crawl4ai.async_configs import CacheMode

BOARD_URL = "https://www.ptt.cc/bbs/Lineage/index.html"
HEADERS = {
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
}
# over18 자동 클릭 (PTT 성인 인증 팝업)
JS_OVER18 = "document.querySelector('button[name=yes]')?.click();"

M_RE = re.compile(r"/M\.\d+")


async def check_page(crawler: AsyncWebCrawler, url: str, label: str) -> str | None:
    """한 페이지를 fetch해서 링크 구조 출력. 이전 페이지 href 반환."""
    print(f"\n[{label}] {url}")

    run = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        page_timeout=30_000,
        js_code=[JS_OVER18],
        delay_before_return_html=2.5,
    )
    res = await crawler.arun(url=url, config=run)

    if not res.success:
        print(f"  ❌ 실패: {res.error_message}")
        return None

    html = res.html or ""
    print(f"  HTML {len(html):,}자")

    internal = (res.links.get("internal") or []) if res.links else []
    external = (res.links.get("external") or []) if res.links else []
    all_links = internal + external

    # M.* 게시글 링크
    m_links = [lk for lk in all_links if M_RE.search(lk.get("href") or "")]
    print(f"  M.* 링크: {len(m_links)}개")
    for lk in m_links[:5]:
        print(f"    {lk.get('href')}  [{(lk.get('text') or '').strip()[:40]}]")

    # 페이지 이동 버튼 (上頁 / 下頁)
    nav_links = [
        lk for lk in all_links
        if any(k in (lk.get("text") or "") for k in ["上頁", "下頁", "‹", "›", "最舊", "最新"])
        or "btn-group-paging" in (lk.get("class") or "")
        or (
            re.search(r"/bbs/\w+/index\d*\.html", lk.get("href") or "")
            and not M_RE.search(lk.get("href") or "")
        )
    ]
    print(f"  페이지 이동 링크: {len(nav_links)}개")
    for lk in nav_links:
        print(f"    href={lk.get('href')!r}  text={lk.get('text', '').strip()!r}")

    # 이전 페이지 href 추출 (index 번호가 작은 쪽)
    prev_href = None
    for lk in nav_links:
        href = lk.get("href") or ""
        text = lk.get("text") or ""
        if "上頁" in text or "‹" in text:
            prev_href = href
            break
    # fallback: index{N}.html 중 가장 큰 번호 아닌 것
    if not prev_href:
        indices = []
        for lk in all_links:
            href = lk.get("href") or ""
            m = re.search(r"index(\d+)\.html", href)
            if m:
                indices.append((int(m.group(1)), href))
        if indices:
            indices.sort()
            prev_href = indices[-1][1] if len(indices) == 1 else indices[-2][1]

    if prev_href:
        # 상대 경로면 절대 경로로
        if prev_href.startswith("/"):
            prev_href = f"https://www.ptt.cc{prev_href}"
        print(f"  => 이전 페이지: {prev_href}")
    else:
        print("  => 이전 페이지 링크 못 찾음")

    return prev_href


async def main() -> None:
    print("=" * 60)
    print("PTT pagination 진단 (Lineage 보드)")
    print("=" * 60)

    cfg = BrowserConfig(
        headless=True,
        enable_stealth=True,
        verbose=False,
        headers=HEADERS,
    )

    async with AsyncWebCrawler(config=cfg) as crawler:
        prev = await check_page(crawler, BOARD_URL, "page 1 (index.html)")
        if prev:
            await asyncio.sleep(2)
            prev2 = await check_page(crawler, prev, "page 2 (index{N-1}.html)")
            if prev2:
                await asyncio.sleep(2)
                await check_page(crawler, prev2, "page 3 (index{N-2}.html)")


if __name__ == "__main__":
    asyncio.run(main())
