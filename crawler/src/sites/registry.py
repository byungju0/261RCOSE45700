"""
크롤링 대상 사이트 레지스트리 (게시판형).

새 사이트 추가 방법:
  1. 아래 SITES 딕셔너리에 SiteConfig 항목 추가
  2. enabled=True 로 활성화
  3. 필요 시 image_filter 함수 작성

타겟 (FR1):
  inven_maple, inven_lineage_classic (KR) — 인벤 자유게시판 두 곳
  ptt, dcard, bahamut (TW)               — 대만 BBS / Dcard / 巴哈姆特
  52pojie, nga, tieba (CN)                — 중국 크랙·게임·百度貼吧

검색엔진형(sogou/bing/baidu/duckduckgo_cn/bilibili/github/reddit/facebook)은
별도 추상화(SearchEngineConfig)에서 다룬다 — 본 파일 범위 밖.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field  # noqa: F401


def _env_enabled(name: str) -> bool:
    return os.environ.get(name, "").lower() in ("1", "true", "yes")


def _dcard_wait_until() -> str | None:
    return "load" if _env_enabled("CRAWL_DCARD_WAIT_UNTIL_LOAD") else None


# ──────────────────────────────────────────────
# post_id 추출기 (사이트별)
# ──────────────────────────────────────────────
# storage._SAFE_ID_RE = ^[A-Za-z0-9_\-]+$ 통과하는 post_id 만 storage 가 허용한다.
# URL 마지막 세그먼트를 그대로 쓰는 기본 lambda 는 querystring (?bsn=…&snA=…) 이나
# 파일 확장자 (.html), 점/슬래시 포함 토큰에 대해 ValueError 를 던지므로
# 아래 사이트들은 명시적 extractor 가 필요하다.

_PTT_POST_ID_RE = re.compile(r"/M\.(\d+)(?:\.[A-Z]\.[0-9A-F]+)?\.html$")
_PJ_POST_ID_RE = re.compile(r"/thread-(\d+)-(\d+)-(\d+)\.html$")
_BAHAMUT_BSN_RE = re.compile(r"[?&]bsn=(\d+)")
_BAHAMUT_SNA_RE = re.compile(r"[?&]snA=(\d+)")
_NGA_POST_ID_RE = re.compile(r"tid=(\d+)")


def _ptt_post_id(url: str) -> str:
    m = _PTT_POST_ID_RE.search(url)
    if not m:
        raise ValueError(f"PTT URL 에서 post_id 추출 실패: {url!r}")
    return m.group(1)  # M.<timestamp>


def _pojie_post_id(url: str) -> str:
    m = _PJ_POST_ID_RE.search(url)
    if not m:
        raise ValueError(f"52pojie URL 에서 post_id 추출 실패: {url!r}")
    return f"{m.group(1)}_{m.group(2)}_{m.group(3)}"  # thread-A-B-C


def _bahamut_post_id(url: str) -> str:
    bsn_m = _BAHAMUT_BSN_RE.search(url)
    sna_m = _BAHAMUT_SNA_RE.search(url)
    if not bsn_m or not sna_m:
        raise ValueError(f"Bahamut URL 에서 post_id 추출 실패: {url!r}")
    return f"bsn{bsn_m.group(1)}_snA{sna_m.group(1)}"  # bsn842_snA12345


def _nga_post_id(url: str) -> str:
    m = _NGA_POST_ID_RE.search(url)
    if not m:
        raise ValueError(f"NGA URL 에서 post_id 추출 실패: {url!r}")
    return m.group(1)  # tid 만 — 도메인은 site_id 로 구분


def _brightdata_cn_proxy() -> dict | None:
    """Bright Data residential proxy (CN zone).

    환경변수 미설정 시 None — proxy 미사용으로 동작.
    PoC 단계에서만 사용. 운영 결정 후 별도 시크릿 매니저로 이전 권장.
    """
    username = os.environ.get("BRIGHTDATA_CN_USERNAME")
    password = os.environ.get("BRIGHTDATA_CN_PASSWORD")
    if not (username and password):
        return None
    return {
        "server": "http://brd.superproxy.io:33335",
        "username": username,
        "password": password,
    }


@dataclass
class SiteConfig:
    name: str                                           # 표시 이름
    description: str                                    # 사이트 설명
    board_urls: list[str]                               # 크롤링할 게시판 URL 목록
    post_url_pattern: str                               # 게시글 URL 정규식 패턴
    image_filter: Callable[[dict], bool] | None = None  # 사용자 업로드 이미지 필터 (None = score 기준만 사용)
    css_selector: str | None = None                     # 본문 영역 CSS 셀렉터 (이미지 추출 범위도 제한)
    post_id_extractor: Callable[[str], str] = field(
        default=lambda url: url.rstrip("/").split("/")[-1]
    )                                                   # URL → post_id (기본: 마지막 경로 세그먼트)
    # ── 사이트별 fetch 옵션 ──
    cookies: list[dict] | None = None                   # AsyncWebCrawler.arun(cookies=...) 로 전달
    wait_for: str | None = None                         # CrawlerRunConfig.wait_for (Dcard 등 SPA)
    headers: dict[str, str] | None = None               # CrawlerRunConfig.headers (User-Agent 등)
    page_timeout: int | None = None                     # ms 단위. None → Crawl4AICrawler 기본값
    proxy: dict | None = None                           # CrawlerRunConfig.proxy_config
    max_retries: int = 0                                # anti-bot block 감지 시 retry round
    # 페이지 로드 후 실행할 JS. PTT over18 인터스티셜 자동 클릭 등.
    # 네비게이션 트리거 JS 는 wait_for 대신 delay_before_return_html 과 함께 쓴다.
    js_code: list[str] | None = None
    delay_before_return_html: float | None = None
    # ── 공식 권장 모던 옵션 (crawl4ai >= 0.8) ──
    scan_full_page: bool = False                        # 무한스크롤 자동 회수 (Dcard 등)
    scroll_delay: float | None = None                   # scan_full_page 시 스크롤 간격(초)
    virtual_scroll_config: dict | None = None           # 가상 스크롤 컨테이너 (Twitter/IG식)
    wait_until: str | None = None                       # "networkidle" / "domcontentloaded"
    simulate_user: bool = False                         # 마우스 움직임 흉내 (약한 anti-bot)
    override_navigator: bool = False                    # navigator fingerprint 완화 (anti-bot)
    user_agent_mode: str | None = None                  # "random" 등 — BrowserConfig 측
    c4a_script: list[str] | None = None                 # crawl4ai DSL 스크립트 (login 폼 등)
    # 기본 False 로 둠 — 일부 사이트(52pojie 등)는 본문이 링크 기반이라
    # 켜면 본문이 텅 비어버리는 사례 실측 확인. 사이트별로 필요시 명시 활성화.
    exclude_social_media_links: bool = False
    exclude_external_links: bool | None = None          # None → crawl4ai 기본 (False)
    # 게시판 listing → 게시글 URL 추출 시 link.text(=제목) 에 적용할 우선순위 키워드.
    # hard filter 가 아니라 관련 제목 후보를 먼저 fetch 하기 위한 scoring feature 다.
    # None / 빈 리스트 → 모든 패턴-매칭 URL 이 같은 우선순위.
    title_keywords: list[str] | None = None
    # ── pagination ──
    # max_pages=1 (기본) 이면 board_urls 의 각 URL 을 단일 페이지로 처리.
    # max_pages > 1 이고 page_url_template 이 설정되면 {base}/{page} 로 추가 페이지 생성.
    max_pages: int = 1
    page_url_template: str | None = None               # 예: "{base}&page={page}"
    # 동적 이전 페이지 탐색: link.text 에 이 문자열이 포함된 링크를 다음 board_url 로 사용.
    # PTT 上頁 처럼 URL 을 미리 알 수 없는 파일시스템 기반 pagination 에 사용.
    prev_page_link_text: str | None = None
    enabled: bool = True
    note: str = ""                                      # 접근 제한·특이사항


# ──────────────────────────────────────────────
# 사이트별 이미지 필터 함수
# ──────────────────────────────────────────────

def _inven_image_filter(img: dict) -> bool:
    """인벤: upload2/3.inven.co.kr/upload/.../bbs/ 경로만 허용."""
    src = img.get("src", "")
    return (
        ("upload2.inven.co.kr/upload" in src or "upload3.inven.co.kr/upload" in src)
        and "/bbs/" in src
    )


def _dcard_image_filter(img: dict) -> bool:
    """Dcard: images.dcard.tw 또는 megapx.dcard.tw 도메인만 허용."""
    src = img.get("src", "")
    return "dcard.tw" in src and ("images." in src or "megapx." in src)


def _bahamut_image_filter(img: dict) -> bool:
    """바하무트: p2.bahamut.com.tw (자체 첨부) + i.imgur.com (자주 사용) 허용."""
    src = img.get("src", "")
    return (
        "p2.bahamut.com.tw" in src
        or "i.imgur.com" in src
        or "i2.bahamut.com.tw" in src
    )


def _tieba_image_filter(img: dict) -> bool:
    """바이두 티에바: tiebapic.baidu.com 또는 imgsrc.baidu.com 도메인만 허용."""
    src = img.get("src", "")
    return "tiebapic.baidu.com" in src or "imgsrc.baidu.com" in src


def _pojie_image_filter(img: dict) -> bool:
    """52pojie: attach.52pojie.cn 또는 img.52pojie.cn 도메인만 허용."""
    src = img.get("src", "")
    return "52pojie.cn" in src and ("attach." in src or "img." in src)


def _nga_image_filter(img: dict) -> bool:
    """NGA: img.nga.178.com 또는 img2.nga.178.com 도메인만 허용."""
    src = img.get("src", "")
    return "nga.178.com" in src and "img" in src


# ──────────────────────────────────────────────
# 공통 헤더 — Accept-Language 만 지정. User-Agent 는 stealth 가 생성하는 값을
# 그대로 둬야 fingerprint 일관성 유지 (이전 회차에서 UA 명시가 Cloudflare 의심을
# 유발해 52pojie 가 막힌 사례 확인).
# ──────────────────────────────────────────────

_CN_HEADERS = {
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}
_TW_HEADERS = {
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
}


# ──────────────────────────────────────────────
# NC 게임 키워드 — 혼합 보드의 제목 필터에 사용 (한·중번·중간·영)
# ──────────────────────────────────────────────
_NC_GAME_KEYWORDS: list[str] = [
    # 리니지 시리즈 (전 NC 시리즈 중 가장 변형 많음)
    "天堂", "Lineage", "리니지",
    # 아이온
    "永恆", "永恒", "Aion", "아이온",
    # 블레이드 앤 소울
    "劍靈", "剑灵", "Blade", "BNS", "블레이드", "블소",
    # 쓰론 앤 리버티 (TL)
    "王權", "王权", "Throne", "Liberty", "쓰론", "리버티",
    # 길드워
    "激戰", "Guild War", "길드워",
    # NC 자체 / 사설서버·매크로 일반어
    "NCsoft", "NCSOFT", "엔씨", "사설서버", "매크로", "외挂", "외掛", "外挂",
]


# Bahamut NC 게임 보드 헬퍼 — 모두 같은 selector·image_filter·헤더를 공유.
def _make_bahamut_nc_site(name_zh: str, bsn: int) -> SiteConfig:
    # post_url_pattern: page 2+ 링크는 bPage=N 파라미터가 앞에 붙음. lookahead로 처리.
    # last=1("마지막 댓글로" 링크) 제외 — bsn+snA 로 dedup 불가해서 candidate 에서 배제.
    return SiteConfig(
        name=f"巴哈姆特 ({name_zh})",
        description=f"바하무트 NC 게임 전용 보드 — {name_zh}",
        board_urls=[f"https://forum.gamer.com.tw/B.php?bsn={bsn}"],
        post_url_pattern=(
            r"https://forum\.gamer\.com\.tw/C\.php\?"
            r"(?!.*[&]last=\d)"
            r"(?=.*\bbsn=\d+)"
            r"(?=.*\bsnA=\d+)"
        ),
        post_id_extractor=_bahamut_post_id,
        css_selector=".c-article__content, .c-post__body",
        image_filter=_bahamut_image_filter,
        headers=_TW_HEADERS,
        page_timeout=35_000,
        max_pages=3,
        page_url_template=f"https://forum.gamer.com.tw/B.php?bsn={bsn}&page={{page}}",
        enabled=True,
        note=f"NC 게임 {name_zh} 전용 보드 (bsn={bsn}) — 100% NC 관련.",
    )


# ──────────────────────────────────────────────
# 사이트 레지스트리
# ──────────────────────────────────────────────

SITES: dict[str, SiteConfig] = {

    # ── 한국 (비교/보존용 — 인벤 두 곳) ──────────────────────────────────
    "inven_maple": SiteConfig(
        name="인벤 (메이플스토리)",
        description="인벤 메이플스토리 자유게시판 — 비교군(NEXON, NC 아님)",
        board_urls=[
            "https://www.inven.co.kr/board/maple/2298",
        ],
        post_url_pattern=r"https://www\.inven\.co\.kr/board/maple/2298/\d+$",
        css_selector=".articleMain",
        image_filter=_inven_image_filter,
        max_pages=3,
        page_url_template="{base}?p={page}",
        enabled=True,
        note="NEXON. 비교 데이터로 유지.",
    ),

    "inven_lineage_classic": SiteConfig(
        name="인벤 (리니지 클래식)",
        description="인벤 리니지 클래식 — NC 게임",
        board_urls=[
            "https://www.inven.co.kr/board/lineageclassic/6482",
        ],
        post_url_pattern=r"https://www\.inven\.co\.kr/board/lineageclassic/6482/\d+$",
        css_selector=".articleMain",
        image_filter=_inven_image_filter,
        max_pages=3,
        page_url_template="{base}?p={page}",
        enabled=True,
    ),

    # ── 대만 PTT — Lineage 보드(순수 NC) + Mobile-game(혼합) ────────────
    "ptt": SiteConfig(
        name="PTT (Lineage)",
        description="PTT 看板 Lineage — NC Lineage 시리즈 통합",
        board_urls=[
            "https://www.ptt.cc/bbs/Lineage/index.html",
        ],
        post_url_pattern=r"https://www\.ptt\.cc/bbs/Lineage/M\.\d+",
        post_id_extractor=_ptt_post_id,
        css_selector="#main-content",
        image_filter=None,
        # over18 폼은 모든 ptt 보드에 동일 — yes 버튼 자동 클릭.
        js_code=[
            "document.querySelector('button[name=yes]')?.click();",
        ],
        delay_before_return_html=3.0,
        headers=_TW_HEADERS,
        max_pages=3,
        prev_page_link_text="上頁",
        enabled=True,
        note="100% NC 게임 보드 — title_keywords 불필요.",
    ),

    "ptt_mobile_game": SiteConfig(
        name="PTT (Mobile-game)",
        description="PTT 모바일게임 일반 — NC 키워드로 필터",
        board_urls=[
            "https://www.ptt.cc/bbs/Mobile-game/index.html",
        ],
        post_url_pattern=r"https://www\.ptt\.cc/bbs/Mobile-game/M\.\d+",
        post_id_extractor=_ptt_post_id,
        css_selector="#main-content",
        image_filter=None,
        js_code=[
            "document.querySelector('button[name=yes]')?.click();",
        ],
        delay_before_return_html=3.0,
        headers=_TW_HEADERS,
        title_keywords=_NC_GAME_KEYWORDS,  # 제목 키워드 매칭 후보 우선
        max_pages=3,
        prev_page_link_text="上頁",
        enabled=True,
        note="혼합 보드. NC 게임 제목 매칭 후보를 우선 fetch — 미매칭 후보도 보존.",
    ),

    # ── 대만 Dcard — 일반 게임 + 온라인게임 (둘 다 혼합) ─────────────────
    "dcard": SiteConfig(
        name="Dcard (game)",
        description="Dcard 게임 일반 게시판 — NC 키워드로 필터",
        board_urls=[
            "https://www.dcard.tw/f/game",
        ],
        post_url_pattern=r"https://www\.dcard\.tw/f/game/p/\d+",
        image_filter=_dcard_image_filter,
        # /f/game listing 은 article selector 로 회수되지만, detail page 에 같은 wait_for 를
        # 재사용하면 실제 smoke 에서 timeout. /f/online 과 동일하게 selector 의존을 끊는다.
        delay_before_return_html=3.0,
        wait_until=_dcard_wait_until(),
        simulate_user=_env_enabled("CRAWL_DCARD_SIMULATE_USER"),
        override_navigator=_env_enabled("CRAWL_DCARD_OVERRIDE_NAVIGATOR"),
        page_timeout=45_000,
        max_retries=1,
        headers=_TW_HEADERS,
        title_keywords=_NC_GAME_KEYWORDS,
        enabled=True,
        note="React SPA. selector 의존 제거 — title_keywords 는 priority feature.",
    ),

    "dcard_online": SiteConfig(
        name="Dcard (topic: 線上遊戲)",
        description="Dcard 線上遊戲 topic — 여러 forum 의 온라인게임 글 집계",
        board_urls=[
            "https://www.dcard.tw/topics/%E7%B7%9A%E4%B8%8A%E9%81%8A%E6%88%B2",
        ],
        post_url_pattern=r"https://www\.dcard\.tw/f/[A-Za-z0-9_-]+/p/\d+",
        image_filter=_dcard_image_filter,
        # Dcard React 클래스가 CSS module 해시 (PostList_entry_*) 라 selector 매번 깨짐.
        # /f/online 은 현재 게시글 링크를 내지 않음 — 線上遊戲 topic 으로 이동.
        # topic/listing 모두 DOM 의존 끊고 hydration 시간만 대기.
        delay_before_return_html=3.0,
        wait_until=_dcard_wait_until(),
        simulate_user=_env_enabled("CRAWL_DCARD_SIMULATE_USER"),
        override_navigator=_env_enabled("CRAWL_DCARD_OVERRIDE_NAVIGATOR"),
        page_timeout=45_000,
        max_retries=1,
        headers=_TW_HEADERS,
        title_keywords=_NC_GAME_KEYWORDS,
        enabled=True,
        note="線上遊戲 topic. 여러 forum post URL 을 수집. selector 의존 제거.",
    ),

    # ── 대만 Bahamut — NC 게임 8개 보드 (모두 순수 NC, title_keywords 불필요) ──
    "bahamut_lineage":         _make_bahamut_nc_site("天堂Lineage", 842),
    "bahamut_lineage_m":       _make_bahamut_nc_site("天堂M", 25908),
    "bahamut_lineage_w":       _make_bahamut_nc_site("天堂W", 71905),
    "bahamut_lineage_classic": _make_bahamut_nc_site("天堂經典版", 84452),
    "bahamut_aion":            _make_bahamut_nc_site("永恆紀元", 9856),
    "bahamut_aion2":           _make_bahamut_nc_site("AION2", 82913),
    "bahamut_bns":             _make_bahamut_nc_site("劍靈", 12980),
    "bahamut_tl":              _make_bahamut_nc_site("王權與自由", 33317),

    # ── 중국 ──────────────────────────────────
    "52pojie": SiteConfig(
        name="52pojie",
        description="중국 최대 크랙/리버싱 커뮤니티",
        # forum-16-1.html (1페이지) 는 거의 전부 sticky/공지/导航. 실측 결과 5/5 sticky.
        # 2페이지부터 일반 사용자 글이 나타남.
        board_urls=[
            "https://www.52pojie.cn/forum-16-2.html",
            "https://www.52pojie.cn/forum-16-3.html",
            "https://www.52pojie.cn/forum-16-4.html",
        ],
        post_url_pattern=r"https://www\.52pojie\.cn/thread-\d+-\d+-\d+\.html",
        post_id_extractor=_pojie_post_id,
        # Discuz! 포럼: .t_f 가 본문 div 표준이지만 sticky/공지 스레드는 layout 이
        # 다름. 그래서 본문 후보 셀렉터를 OR 로 묶어 누락 없게.
        #   .t_f                — 일반 게시글 본문
        #   [id^=postmessage_]  — 답글 포함 모든 floor 본문
        #   .t_msgfont          — 구버전 Discuz 호환
        css_selector=".t_f, [id^=postmessage_], .t_msgfont",
        image_filter=_pojie_image_filter,
        page_timeout=40_000,
        headers=_CN_HEADERS,
        enabled=True,
        note="Cloudflare 보호. stealth + zh-CN UA 로 통과 가능. 프록시 옵션.",
    ),

    "tieba": SiteConfig(
        name="바이두 티에바",
        description="중국 바이두 게임 커뮤니티 — 핵/매크로 게시물 출처",
        board_urls=[
            "https://tieba.baidu.com/f?kw=游戏外挂",
            "https://tieba.baidu.com/f?kw=手游辅助",
        ],
        post_url_pattern=r"https://tieba\.baidu\.com/p/\d+",
        # 본문: .d_post_content (각 floor 본문). 첫 글만 필요하면 #post_content_1.
        css_selector=".d_post_content, .left_section",
        image_filter=_tieba_image_filter,
        headers=_CN_HEADERS,
        page_timeout=40_000,
        # 약한 anti-bot 회피용 — IP 차단엔 무력하지만 시도는 해봄.
        simulate_user=True,
        user_agent_mode="random",
        proxy=_brightdata_cn_proxy(),
        enabled=False,
        note=(
            "Bright Data CN residential proxy PoC (2026-05-20) 결과: 프록시 라우팅·중국 IP "
            "발급은 정상이나 Baidu anti-bot 이 stealth Chromium까지 차단 (HTTP 403). "
            "추가로 민감 키워드(游戏外挂 등) 검색은 로그인 필수인데 계정 가입에 "
            "중국 본토 휴대폰 + 실명 인증 요구 → IP·계정 이중 장벽으로 out-of-scope. "
            "BRIGHTDATA_CN_USERNAME/PASSWORD 환경변수 + enabled=True 로 재활성 가능."
        ),
    ),

    "nga": SiteConfig(
        name="NGA BBS",
        description="중국 게임 커뮤니티 NGA — 게임 핵 관련 포럼",
        board_urls=[
            # fid=489 = 主机游戏综合区, fid=-7 = 综合大区 등.
            "https://bbs.nga.cn/thread.php?fid=489",
            "https://ngabbs.com/thread.php?fid=489",     # 미러 도메인 fallback
        ],
        post_url_pattern=r"https://(bbs\.nga\.cn|ngabbs\.com)/read\.php\?tid=\d+",
        post_id_extractor=_nga_post_id,
        # NGA read.php: 본문 #postcontent0 (첫 글) + .postcontent (답글).
        css_selector="#postcontent0, .postcontent, .postcontent_main",
        image_filter=_nga_image_filter,
        headers=_CN_HEADERS,
        page_timeout=35_000,
        # NGA 는 HTTP 403 anti-bot 으로 막힘. UA 회전 + simulate_user 시도 (IP 차단엔 무력).
        simulate_user=True,
        user_agent_mode="random",
        proxy=_brightdata_cn_proxy(),
        enabled=False,
        note=(
            "Bright Data CN residential proxy PoC (2026-05-20) 결과: "
            "ERR_TUNNEL_CONNECTION_FAILED — NGA 가 proxy 패턴 자체 차단 추정. "
            "본문 열람은 ngaPassportUid 쿠키 필수인데 계정 가입에 중국 본토 휴대폰 + "
            "실명 인증 요구 → IP·계정 이중 장벽으로 out-of-scope. "
            "BRIGHTDATA_CN_USERNAME/PASSWORD 환경변수 + enabled=True 로 재활성 가능."
        ),
    ),
}


def get_enabled_sites() -> dict[str, SiteConfig]:
    """활성화된 사이트만 반환."""
    return {k: v for k, v in SITES.items() if v.enabled}
