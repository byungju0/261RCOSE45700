"""Listing candidate priority scoring tests."""
from __future__ import annotations

from crawler.src.scheduler.candidate_scoring import score_listing_candidate


def test_high_risk_distribution_candidate_is_p0():
    result = score_listing_candidate(
        site_id="52pojie",
        board_url="https://example.com/forum",
        title="Valorant undetected cheat loader download Discord",
        keyword_matched=True,
        has_title_keywords=True,
    )

    assert result.priority_bucket == "P0"
    assert result.score >= 70
    assert "high_risk_term" in result.reasons
    assert "contact_or_sales_term" in result.reasons
    assert "download_or_file_term" in result.reasons


def test_source_risk_alone_does_not_promote_to_p2():
    result = score_listing_candidate(
        site_id="52pojie",
        board_url="https://www.52pojie.cn/forum-16-2.html",
        title="普通讨论帖",
        keyword_matched=False,
        has_title_keywords=False,
    )

    assert result.priority_bucket == "P3"
    assert result.score > 0


def test_ascii_terms_do_not_match_inside_words_or_emoticons():
    result = score_listing_candidate(
        site_id="bahamut_lineage",
        board_url="https://forum.gamer.com.tw/B.php?bsn=842",
        title="安裝後出現 the execution arguments are not valid QQ",
        keyword_matched=False,
        has_title_keywords=False,
    )

    assert result.contact_signal == 0
    assert result.download_signal == 0
    assert result.priority_bucket == "P3"


def test_report_or_rule_post_gets_low_intent_penalty():
    result = score_listing_candidate(
        site_id="bahamut_aion",
        board_url="https://forum.gamer.com.tw/B.php?bsn=9856",
        title="【攻略】檢舉外掛的流程",
        keyword_matched=False,
        has_title_keywords=False,
    )

    assert "low_distribution_intent" in result.reasons
    assert result.priority_bucket == "P3"


def test_pojie_intro_navigation_title_is_not_p2():
    result = score_listing_candidate(
        site_id="52pojie",
        board_url="https://www.52pojie.cn/forum-16-2.html",
        title="Windows破解入门",
        keyword_matched=False,
        has_title_keywords=False,
    )

    assert "low_distribution_intent" in result.reasons
    assert result.priority_bucket == "P3"


def test_title_unmatched_mixed_board_is_sampling_candidate_not_drop():
    result = score_listing_candidate(
        site_id="dcard",
        board_url="https://www.dcard.tw/f/game",
        title="最近設定分享",
        keyword_matched=False,
        has_title_keywords=True,
    )

    assert result.priority_bucket in {"P2", "P3"}
    assert result.exploration_bonus > 0
    assert "title_unmatched_sampling_candidate" in result.reasons


def test_low_signal_dedicated_board_still_gets_source_score():
    result = score_listing_candidate(
        site_id="bahamut_lineage",
        board_url="https://forum.gamer.com.tw/B.php?bsn=842",
        title="請問每日任務",
        keyword_matched=False,
        has_title_keywords=False,
    )

    assert result.score > 0
    assert result.priority_bucket == "P3"
