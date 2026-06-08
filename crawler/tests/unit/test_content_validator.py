"""content_validator: 사이트별 사용자 게시글 / 공지·인증벽·캡차 판별 검증."""
from __future__ import annotations

from crawler.src.preprocessor import content_validator as cv

# ──────────────────────────────────────────────
# 공통 가드
# ──────────────────────────────────────────────


class TestGenericGuard:
    def test_empty_returns_empty_kind(self):
        v = cv.validate("inven_maple", "", "")
        assert v.is_real_user_post is False
        assert v.kind == "empty"

    def test_whitespace_returns_empty_kind(self):
        v = cv.validate("inven_maple", "   \n\t  ", "")
        assert v.kind == "empty"

    def test_too_short_returns_short_kind(self):
        v = cv.validate("inven_maple", "짧다", "")
        assert v.kind == "short"

    def test_cloudflare_marker_returns_captcha(self):
        text = "Just a moment... Please wait. Cloudflare Ray ID: 12345"
        v = cv.validate("52pojie", text, "")
        assert v.kind == "captcha"
        assert v.is_real_user_post is False

    def test_auth_wall_marker_returns_auth_wall(self):
        text = (
            "歡迎您回到 PTT。為了維護討論品質，本看板需確認您已年滿十八歲。"
            "請按下方確認鍵繼續。" + "x" * 60
        )
        v = cv.validate("ptt", text, "")
        assert v.kind == "auth_wall"


# ──────────────────────────────────────────────
# 인벤
# ──────────────────────────────────────────────

class TestInvenValidator:
    def test_real_post_with_exp_marker(self):
        text = "# 보스 잡는 팁 EXP 5000 / 8000 인벤쪽지 보내기 " + "x" * 100
        v = cv.validate_inven(text, "")
        assert v.is_real_user_post is True
        assert v.kind == "real"

    def test_unknown_when_no_inven_markers(self):
        text = "이것은 그냥 일반 텍스트입니다. " * 10
        v = cv.validate_inven(text, "")
        assert v.is_real_user_post is False
        assert v.kind == "unknown"


# ──────────────────────────────────────────────
# PTT
# ──────────────────────────────────────────────

class TestPttValidator:
    def test_real_post_has_four_headers(self):
        text = (
            "作者orca1912 (翻滾虎鯨) 看板C_Chat 標題[閒聊] 高空乳X好刺激 "
            "時間Tue May 19 15:55:57 2026 沒錯！在高空中高速乳搖非常刺激！" + "x" * 50
        )
        v = cv.validate_ptt(text, "")
        assert v.is_real_user_post is True
        assert v.kind == "real"

    def test_announcement_detected_as_sticky(self):
        text = (
            "作者ptt_admin 看板C_Chat 標題[公告] 板規修正 "
            "時間Mon Jan 1 00:00:00 2026 본문 본문 본문 " + "x" * 50
        )
        v = cv.validate_ptt(text, "")
        assert v.is_real_user_post is False
        assert v.kind == "sticky"

    def test_missing_headers_unknown(self):
        text = "그냥 텍스트 그냥 텍스트 " * 10
        v = cv.validate_ptt(text, "")
        assert v.kind == "unknown"


# ──────────────────────────────────────────────
# Dcard
# ──────────────────────────────────────────────

class TestDcardValidator:
    def test_real_post_with_category_and_time(self):
        text = "## #閒聊 玩盜版遊戲還找開發者問問題 昨天 06:35 본문 " + "x" * 60
        v = cv.validate_dcard(text, "")
        assert v.is_real_user_post is True
        assert v.kind == "real"

    def test_real_post_with_category_only(self):
        text = "## #問題 어떻게 풀어요 " + "x" * 60
        v = cv.validate_dcard(text, "")
        assert v.is_real_user_post is True

    def test_real_post_with_dcard_post_url_and_body_length(self):
        text = "狼人殺揪團心得，這篇沒有 Dcard 類別 chrome，但正文很完整。" * 12
        v = cv.validate_dcard(text, "https://www.dcard.tw/f/werewolf/p/261604959")
        assert v.is_real_user_post is True
        assert v.kind == "real"

    def test_no_markers_unknown(self):
        v = cv.validate_dcard("그냥 일반 텍스트 " * 20, "")
        assert v.kind == "unknown"


# ──────────────────────────────────────────────
# 바하무트
# ──────────────────────────────────────────────

class TestBahamutValidator:
    def test_30th_anniversary_is_sticky(self):
        text = "巴哈姆特 30 週年站聚 ACG 輕音祭 報名期間 " + "x" * 60
        v = cv.validate_bahamut(text, "")
        assert v.is_real_user_post is False
        assert v.kind == "sticky"
        assert "週年" in v.reason or "站聚" in v.reason

    def test_admin_announcement_is_sticky(self):
        text = "管理員公告 板規修正 " + "x" * 80
        v = cv.validate_bahamut(text, "")
        assert v.kind == "sticky"

    def test_real_user_post_passes_on_body_length(self):
        # css_selector 가 chrome(GP/BP/樓主)을 잘라낸 후의 순수 본문에서도
        # 길이 기반으로 real 판정해야 함 (Bahamut 회귀 방지).
        text = (
            "리니지 블맹 후기 — 어제 보스 사냥 가서 "
            "공성전 준비 중인데 외掛 쓰는 사람들이 많아서 짜증나네요 "
            "팀 채팅도 매크로로 도배되고. 그냥 일반 사용자 글입니다."
        ) * 5  # 200자 넘게 확보
        v = cv.validate_bahamut(text, "")
        assert v.is_real_user_post is True
        assert v.kind == "real"

    def test_short_post_classified_as_short_not_real(self):
        # generic guard 기준 50자 미만 → real 가 아닌 short.
        text = "짧은 글 " * 5  # 30자 정도
        v = cv.validate_bahamut(text, "")
        assert v.is_real_user_post is False
        assert v.kind == "short"

    def test_short_but_meaningful_user_post_passes(self):
        # 2026-06-07 detail probe: 50~200자 사이 Bahamut 글에도 위험 신호가 있었다.
        text = (
            "今天在野外找背包和採集看到的外掛，請問這種情況官方會處理嗎？"
            "角色一直重複同樣動作，附近玩家也都在討論。"
        )
        v = cv.validate_bahamut(text, "")
        assert v.is_real_user_post is True
        assert v.kind == "real"


# ──────────────────────────────────────────────
# 52pojie
# ──────────────────────────────────────────────

class TestPojieValidator:
    def test_navigation_index_is_sticky(self):
        # 실제 회수된 sticky 글 패턴.
        text = "动画发布区新手入门导航索引贴 좋은 도구 리스트 " + "x" * 80
        v = cv.validate_pojie(text, "")
        assert v.is_real_user_post is False
        assert v.kind == "sticky"

    def test_normal_thread_with_user_markers(self):
        text = "某游戏分析 楼主 发表于 2026-1-1 复制代码 " + "x" * 80
        v = cv.validate_pojie(text, "")
        assert v.is_real_user_post is True

    def test_thread_without_markers_unknown(self):
        v = cv.validate_pojie("그냥 일반 텍스트 " * 30, "")
        assert v.kind == "unknown"


# ──────────────────────────────────────────────
# 디스패치
# ──────────────────────────────────────────────

class TestDispatcher:
    def test_unknown_site_uses_generic_guard(self):
        # 등록 안 된 site_id 면 generic guard 만 통과.
        v = cv.validate("nonexistent_site", "충분히 긴 텍스트 " * 20, "")
        assert v.is_real_user_post is True
        assert "검증자 미등록" in v.reason

    def test_unknown_site_still_catches_empty(self):
        v = cv.validate("nonexistent_site", "", "")
        assert v.kind == "empty"

    def test_dispatch_picks_correct_validator(self):
        text = "[公告] foo 作者 a 看板 b 標題 c 時間 d " + "x" * 60
        v = cv.validate("ptt", text, "")
        # PTT 전용 sticky 판정이 동작해야 한다.
        assert v.kind == "sticky"

    def test_prefix_dispatch_bahamut_family(self):
        # bahamut_tl, bahamut_lineage 등 신규 site_id 가 자동으로 validate_bahamut 사용.
        text = "巴哈姆特 30 週年站聚 활동 안내 " + "x" * 80
        for sid in ("bahamut_tl", "bahamut_lineage", "bahamut_aion"):
            v = cv.validate(sid, text, "")
            assert v.kind == "sticky", f"{sid} should dispatch to bahamut validator"

    def test_prefix_dispatch_ptt_mobile_game(self):
        # ptt_mobile_game 도 PTT 검증자 사용.
        text = "作者foo 看板Mobile-game 標題[閒聊] 천堂M 신규 클래스 후기 時間Mon " + "x" * 60
        v = cv.validate("ptt_mobile_game", text, "")
        assert v.kind == "real"

    def test_prefix_dispatch_dcard_online(self):
        text = "## #閒聊 天堂W 신규 캐릭터 후기 昨天 본문 본문 " + "x" * 60
        v = cv.validate("dcard_online", text, "")
        assert v.kind == "real"
