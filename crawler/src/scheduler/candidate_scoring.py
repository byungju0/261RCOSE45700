"""Cheap candidate priority scoring for crawl inventory experiments."""
from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class CandidateScore:
    score: int
    priority_bucket: str
    reasons: list[str]
    source_risk: int
    keyword_signal: int
    contact_signal: int
    download_signal: int
    game_signal: int
    exploration_bonus: int


_SOURCE_RISK: dict[str, int] = {
    "52pojie": 20,
    "ptt_mobile_game": 8,
    "dcard": 6,
    "dcard_online": 6,
}

_HIGH_RISK_TERMS = (
    "hack", "cheat", "crack", "macro", "bot", "bypass", "injector", "loader",
    "undetected", "hwid", "aimbot", "esp", "wallhack", "keyauth",
    "핵", "치트", "매크로", "봇", "우회", "자동사냥",
    "外掛", "外挂", "輔助", "辅助", "破解", "私服", "自動", "自动",
)

_CONTACT_TERMS = (
    "telegram", "discord", "wechat", "weixin", "kakao", "openchat",
    "qq号", "qq號", "qq群", "qq 群", "qq:",
    "텔레그램", "디스코드", "카톡", "오픈채팅", "문의", "판매", "구매",
    "聯絡", "联系", "出售", "购买", "代練", "代练",
)

_DOWNLOAD_TERMS = (
    "download", "release", "github", "mediafire", "mega.nz", "drive.google",
    "dropbox", "apk", "exe", "dll", "zip", "rar", "7z",
    "다운로드", "다운", "파일", "첨부", "下載", "下载", "附件",
)

_GAME_TERMS = (
    "lineage", "리니지", "天堂", "maple", "메이플", "楓之谷", "枫之谷",
    "roblox", "로블록스", "valorant", "발로란트", "cs2", "counter-strike",
    "minecraft", "마인크래프트", "aion", "아이온", "blade", "bns",
)

_LOW_INTENT_TERMS = (
    "공지", "규정", "신고", "운영자", "공식", "점검", "패치노트",
    "檢舉", "举报", "官方", "規定", "规定", "版規", "版规", "公告", "目錄", "目录",
    "入門", "入门", "新手", "導航", "导航", "索引",
)


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    lowered = text.lower()
    for term in terms:
        needle = term.lower()
        if needle.isascii():
            pattern = rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])"
            if re.search(pattern, lowered):
                return True
        elif needle in lowered:
            return True
    return False


def score_listing_candidate(
    *,
    site_id: str,
    board_url: str,
    title: str,
    keyword_matched: bool,
    has_title_keywords: bool,
) -> CandidateScore:
    """Score a listing-stage candidate without fetching the detail page.

    This score is intentionally cheap and explainable. It must not be used as a
    hard drop rule by itself; low-score candidates still need sampling so title
    euphemisms and source-specific slang can be discovered.
    """
    haystack = " ".join([site_id, board_url, title])
    reasons: list[str] = []

    source_risk = _SOURCE_RISK.get(site_id, 4)
    if source_risk >= 10:
        reasons.append(f"source_risk:{site_id}")

    keyword_signal = 25 if keyword_matched else 0
    if keyword_signal:
        reasons.append("title_keyword_match")

    high_risk_signal = 30 if _contains_any(haystack, _HIGH_RISK_TERMS) else 0
    if high_risk_signal:
        reasons.append("high_risk_term")

    contact_signal = 20 if _contains_any(haystack, _CONTACT_TERMS) else 0
    if contact_signal:
        reasons.append("contact_or_sales_term")

    download_signal = 20 if _contains_any(haystack, _DOWNLOAD_TERMS) else 0
    if download_signal:
        reasons.append("download_or_file_term")

    game_signal = 10 if _contains_any(haystack, _GAME_TERMS) else 0
    if game_signal:
        reasons.append("game_term")

    exploration_bonus = 6 if has_title_keywords and not keyword_matched else 0
    if exploration_bonus:
        reasons.append("title_unmatched_sampling_candidate")

    low_intent_penalty = -15 if _contains_any(haystack, _LOW_INTENT_TERMS) else 0
    if low_intent_penalty:
        reasons.append("low_distribution_intent")

    score = (
        source_risk
        + keyword_signal
        + high_risk_signal
        + contact_signal
        + download_signal
        + game_signal
        + exploration_bonus
        + low_intent_penalty
    )
    score = max(0, score)

    strong_signal_count = sum(
        1
        for signal in (keyword_signal + high_risk_signal, contact_signal, download_signal)
        if signal > 0
    )
    has_distribution_combo = strong_signal_count >= 2

    if score >= 70 and has_distribution_combo:
        priority_bucket = "P0"
    elif score >= 45 and has_distribution_combo:
        priority_bucket = "P1"
    elif (
        score >= 25
        and (high_risk_signal or contact_signal or download_signal)
        and not (low_intent_penalty and not (contact_signal or download_signal))
    ):
        priority_bucket = "P2"
    else:
        priority_bucket = "P3"

    return CandidateScore(
        score=score,
        priority_bucket=priority_bucket,
        reasons=reasons,
        source_risk=source_risk,
        keyword_signal=keyword_signal + high_risk_signal,
        contact_signal=contact_signal,
        download_signal=download_signal,
        game_signal=game_signal,
        exploration_bonus=exploration_bonus,
    )
