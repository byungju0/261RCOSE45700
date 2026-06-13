"""크롤된 본문이 실제 사용자 게시글인지 검증.

목적:
  - "OK 로 표시됐는데 사실 인증벽/공지/캡차였다" 같은 위양성 잡기
  - smoke / pipeline 양쪽에서 같은 기준으로 검증
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

# ──────────────────────────────────────────────
# 결과 모델
# ──────────────────────────────────────────────

# kind 정의:
#   real       — 실제 사용자 게시글 (다음 단계로 진행)
#   sticky     — 공지/index/스티키 (운영자 글, 스킵 대상)
#   auth_wall  — 로그인/연령 인증 인터스티셜 (재시도 또는 옵션 추가 필요)
#   captcha    — Cloudflare/캡차 챌린지
#   empty      — 본문 0자
#   short      — 본문이 의미있는 글이라기엔 너무 짧음 (50자 미만)
#   error      — 4xx/5xx 또는 사이트 에러 페이지
#   unknown    — 사이트별 마커가 안 잡힘 (보수적으로 false 처리)
PostKind = str


@dataclass
class PostValidation:
    is_real_user_post: bool
    kind: PostKind
    reason: str

    def __str__(self) -> str:
        return f"{self.kind}: {self.reason}"


ContentValidator = Callable[[str, str], PostValidation]


# ──────────────────────────────────────────────
# 공통 가드 — 사이트별 검증 직전 통과
# ──────────────────────────────────────────────

# Note: PTT 정상 게시글에도 인용으로 "登入"/"登入" 같은 단어가 나올 수 있어
# 인증벽 마커는 의도적으로 짧고 강한 것만 둠.
_AUTH_WALL_MARKERS: tuple[str, ...] = (
    "請按下方確認鍵",      # PTT over18 인터스티셜
    "我同意，我已年滿十八歲",  # PTT over18 버튼 라벨
    "請先登入",            # 대만권 로그인 강제
    "請先登錄",
    "请先登录",
    "请登录后再访问",
    "您没有权限",
    "需要登录后才能",
    "Access Denied",
    "403 Forbidden",
    "您的请求被拦截",
)

_CAPTCHA_MARKERS: tuple[str, ...] = (
    "Cloudflare Ray ID",
    "Just a moment",
    "Please complete the security check",
    "请完成以下验证",
    "請完成下方驗證",
    "hCaptcha",
    "reCAPTCHA",
)

_ERROR_MARKERS: tuple[str, ...] = (
    "404 Not Found",
    "Page Not Found",
    "找不到頁面",
    "页面不存在",
    "500 Internal Server Error",
    "Bad Gateway",
)

_MIN_BODY_LEN = 50


def _generic_guard(markdown: str) -> PostValidation | None:
    """공통 안전망. 통과(None)면 사이트별 검증으로 위임."""
    text = (markdown or "").strip()
    if not text:
        return PostValidation(False, "empty", "본문이 비어있음")
    if len(text) < _MIN_BODY_LEN:
        return PostValidation(False, "short", f"본문 {len(text)}자 (min {_MIN_BODY_LEN})")
    # 캡차가 가장 흔한 위양성. auth/error 보다 먼저 잡는다.
    for m in _CAPTCHA_MARKERS:
        if m in text:
            return PostValidation(False, "captcha", f"캡차 마커: {m!r}")
    for m in _AUTH_WALL_MARKERS:
        if m in text:
            return PostValidation(False, "auth_wall", f"인증벽 마커: {m!r}")
    for m in _ERROR_MARKERS:
        if m in text:
            return PostValidation(False, "error", f"에러 페이지 마커: {m!r}")
    return None


# ──────────────────────────────────────────────
# 사이트별 검증자
# ──────────────────────────────────────────────


def validate_inven(markdown: str, url: str) -> PostValidation:
    """인벤: EXP/인벤쪽지/댓글 — 게시글에만 따라붙는 사용자 프로필 chrome 존재."""
    g = _generic_guard(markdown)
    if g:
        return g
    markers = ("EXP", "인벤쪽지", "획득스킬", "추천")
    if any(m in markdown for m in markers):
        return PostValidation(True, "real", "인벤 사용자 게시글 마커 발견")
    return PostValidation(False, "unknown", "인벤 사용자 프로필 chrome 미발견")


def validate_ptt(markdown: str, url: str) -> PostValidation:
    """PTT: 4헤더(作者/看板/標題/時間) 모두 존재해야 진짜 글.
    [公告] / [協尋] / [情報] 같은 카테고리 prefix 가 標題 줄에 있으면 공지·운영 글."""
    g = _generic_guard(markdown)
    if g:
        return g
    required = ("作者", "看板", "標題", "時間")
    missing = [k for k in required if k not in markdown]
    if missing:
        return PostValidation(False, "unknown", f"PTT 헤더 누락: {missing}")
    if "[公告]" in markdown or "[協尋]" in markdown:
        return PostValidation(False, "sticky", "PTT 공지/협심 게시글")
    return PostValidation(True, "real", "PTT 4헤더 완전 + 일반 글")


_BAHAMUT_OFFICIAL_MARKERS: tuple[str, ...] = (
    "巴哈姆特 30 週年", "巴哈姆特30週年", "30 週年站聚",
    "官方公告", "巴哈姆特官方", "活動辦法", "活動公告",
    "報名期間", "活動期間", "管理員公告", "板務公告",
)


_BAHAMUT_BODY_MIN_LEN = 50


def validate_bahamut(markdown: str, url: str) -> PostValidation:
    """바하무트:
      1) 공지 마커(站聚/30주년/官方公告 등) → sticky
      2) 본문이 _BAHAMUT_BODY_MIN_LEN 이상이고 sticky 아님 → real

    Chrome 마커(GP/BP/樓主) 의존을 의도적으로 버린 이유:
    css_selector(.c-article__content, .c-post__body) 가 *순수 본문* 만 추출하므로
    header/footer 의 chrome 마커가 markdown 에 안 남는다. 21K자 사용자 글이 자꾸
    unknown 으로 분류되던 회귀(2026-05) 직접 분석 → URL 정규식이 이미
    C.php?bsn=N&snA=N 로 게시글임을 보장 + sticky 마커가 selector 통과 후에도
    남는 사실 확인 → 길이 기반이 가장 정확.

    2026-06-07 detail probe 에서 50~200자 사이의 짧은 사용자 글에도 외掛/계정/
    다운로드 신호가 자주 나타났다. generic guard 의 50자 미만 short 기준은
    유지하되, Bahamut 전용 200자 장벽은 제거한다.
    """
    g = _generic_guard(markdown)
    if g:
        return g
    head = markdown[:1200]  # 제목·첫 단락에 공지 마커가 모이는 경향
    for kw in _BAHAMUT_OFFICIAL_MARKERS:
        if kw in head:
            return PostValidation(False, "sticky", f"바하무트 공지 마커: {kw!r}")
    body_len = len(markdown.strip())
    if body_len >= _BAHAMUT_BODY_MIN_LEN:
        return PostValidation(
            True, "real",
            f"바하무트 게시글 본문 충분 ({body_len}자, chrome 제거 후 순수 본문)",
        )
    return PostValidation(
        False, "short",
        f"바하무트 본문 짧음 ({body_len}자 < {_BAHAMUT_BODY_MIN_LEN})",
    )


_POJIE_STICKY_MARKERS: tuple[str, ...] = (
    "导航索引", "导航贴", "导航帖",
    "新手入门", "入门导航", "入门索引",
    "公告", "置顶", "版规", "版主",
    "汇总贴", "汇总帖",
)


def validate_pojie(markdown: str, url: str) -> PostValidation:
    """52pojie: 导航/索引/教程/置顶 → 공지/관리 글. 发表于/楼主/复制代码 → 사용자 글."""
    g = _generic_guard(markdown)
    if g:
        return g
    head = markdown[:800]
    for kw in _POJIE_STICKY_MARKERS:
        if kw in head:
            return PostValidation(False, "sticky", f"52pojie 공지/导航 마커: {kw!r}")
    user_markers = ("发表于", "楼主", "复制代码", "评分", "回帖奖励")
    if any(m in markdown for m in user_markers):
        return PostValidation(True, "real", "52pojie 일반 스레드 마커")
    return PostValidation(False, "unknown", "52pojie 사용자/공지 마커 둘 다 미발견")


def validate_nga(markdown: str, url: str) -> PostValidation:
    """NGA: 게시글이면 작성자/등급 표시 + 楼层 번호. 비로그인 차단 시 본문 0."""
    g = _generic_guard(markdown)
    if g:
        return g
    if "请先注册或登录" in markdown or "您所在的用户组" in markdown:
        return PostValidation(False, "auth_wall", "NGA 비로그인 차단")
    user_markers = ("发表于", "楼主", "Lv.", "[s:")  # NGA emoji 인 [s:ac:囧] 같은 마커
    if any(m in markdown for m in user_markers):
        return PostValidation(True, "real", "NGA 사용자 게시글 마커")
    return PostValidation(False, "unknown", "NGA 사용자 마커 미발견")


def validate_tieba(markdown: str, url: str) -> PostValidation:
    """티에바: 로그인 없이도 본문은 보임. 발표 시간/팔로워 마커 확인."""
    g = _generic_guard(markdown)
    if g:
        return g
    if "百度首页" in markdown[:200] and "贴吧" in markdown[:200] and len(markdown) < 500:
        return PostValidation(False, "error", "Tieba 홈/리다이렉트 페이지 추정")
    user_markers = ("回复", "楼主", "来自", "签到")
    if any(m in markdown for m in user_markers):
        return PostValidation(True, "real", "Tieba 사용자 게시글 마커")
    return PostValidation(False, "unknown", "Tieba 마커 미발견")


# ──────────────────────────────────────────────
# 디스패치
# ──────────────────────────────────────────────

SITE_VALIDATORS: dict[str, ContentValidator] = {
    "inven_maple": validate_inven,
    "inven_lineage_classic": validate_inven,
    "52pojie": validate_pojie,
    "nga": validate_nga,
    "tieba": validate_tieba,
}

# 같은 family(ptt_*/bahamut_*/inven_*) 가 같은 검증자를 공유.
# SITES 에 보드 추가될 때마다 SITE_VALIDATORS 를 손댈 필요 없게 한다.
PREFIX_VALIDATORS: list[tuple[str, ContentValidator]] = [
    ("ptt_", validate_ptt),
    ("ptt", validate_ptt),            # 'ptt' (Lineage) 자체
    ("bahamut_", validate_bahamut),
    ("bahamut", validate_bahamut),
    ("inven_", validate_inven),
]


def validate(site_id: str, markdown: str, url: str = "") -> PostValidation:
    """site_id 별 검증자 호출. SITE_VALIDATORS 우선, 그 다음 PREFIX_VALIDATORS,
    마지막으로 generic guard 만 적용."""
    fn = SITE_VALIDATORS.get(site_id)
    if fn is None:
        for prefix, candidate in PREFIX_VALIDATORS:
            # 정확 일치(site_id == prefix) 또는 prefix 로 시작.
            if site_id == prefix or site_id.startswith(prefix):
                fn = candidate
                break
    if fn is None:
        g = _generic_guard(markdown)
        if g:
            return g
        return PostValidation(True, "real", f"기본 검증만 통과 (site={site_id} 검증자 미등록)")
    return fn(markdown, url)
