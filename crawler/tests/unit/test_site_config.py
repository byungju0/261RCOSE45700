"""SiteConfig 의 fetch 옵션 필드(cookies/wait_for/headers/page_timeout/proxy) 기본값과
SITES 레지스트리의 사이트별 설정이 의도대로 채워져 있는지 검증."""
from __future__ import annotations

from crawler.src.sites.registry import SITES, SiteConfig, get_enabled_sites


class TestSiteConfigDefaults:
    def _make(self, **overrides) -> SiteConfig:
        base = dict(
            name="t",
            description="d",
            board_urls=["https://example.com/board"],
            post_url_pattern=r"https://example\.com/\d+",
        )
        base.update(overrides)
        return SiteConfig(**base)

    def test_new_option_fields_default_to_none(self):
        s = self._make()
        assert s.cookies is None
        assert s.wait_for is None
        assert s.headers is None
        assert s.page_timeout is None
        assert s.proxy is None
        assert s.max_retries == 0
        assert s.js_code is None
        assert s.delay_before_return_html is None

    def test_modern_option_fields_have_sensible_defaults(self):
        s = self._make()
        # bool 기본값
        assert s.scan_full_page is False
        assert s.simulate_user is False
        assert s.override_navigator is False
        # 본문이 링크 위주인 사이트(52pojie 등)가 텅 비는 회귀를 막기 위해 기본 off.
        assert s.exclude_social_media_links is False
        # None 기본값
        assert s.scroll_delay is None
        assert s.virtual_scroll_config is None
        assert s.wait_until is None
        assert s.user_agent_mode is None
        assert s.c4a_script is None
        assert s.exclude_external_links is None

    def test_enabled_defaults_to_true(self):
        assert self._make().enabled is True

    def test_cookies_accepts_list_of_dicts(self):
        cookies = [{"name": "over18", "value": "1", "domain": ".ptt.cc", "path": "/"}]
        s = self._make(cookies=cookies)
        assert s.cookies == cookies


class TestSiteRegistryWiring:
    """레지스트리의 사이트별 옵션이 의도된 값으로 설정되어 있는지."""

    # ── 인벤 (회귀 방지) ──
    def test_inven_sites_unchanged(self):
        assert SITES["inven_maple"].css_selector == ".articleMain"
        assert SITES["inven_lineage_classic"].css_selector == ".articleMain"

    # ── PTT ──
    def test_ptt_has_over18_form_click_js(self):
        ptt = SITES["ptt"]
        # cookies 인자만으론 통과 안 됨이 실측으로 확인 — js_code 로 폼 자동 제출.
        assert ptt.js_code is not None
        joined = " ".join(ptt.js_code)
        assert "button[name=yes]" in joined or "yes" in joined

    def test_ptt_has_delay_for_post_submit_navigation(self):
        # js_code 클릭 후 navigation 이 일어나므로 delay 가 있어야 새 페이지를 회수함.
        assert SITES["ptt"].delay_before_return_html is not None
        assert SITES["ptt"].delay_before_return_html >= 2.0

    def test_ptt_has_main_content_selector(self):
        assert SITES["ptt"].css_selector == "#main-content"

    def test_ptt_has_tw_accept_language(self):
        assert SITES["ptt"].headers is not None
        assert "zh-TW" in SITES["ptt"].headers.get("Accept-Language", "")

    # ── Dcard ──
    def test_dcard_uses_delay_not_selector(self):
        dcard = SITES["dcard"]
        assert dcard.wait_for is None
        assert dcard.delay_before_return_html == 3.0

    def test_dcard_has_extended_page_timeout(self):
        assert SITES["dcard"].page_timeout is not None
        assert SITES["dcard"].page_timeout >= 40_000
        assert SITES["dcard"].max_retries == 1

    def test_dcard_avoids_aggressive_scroll(self):
        # scan_full_page + networkidle 조합이 Dcard anti-bot 을 자극해 차단됨 (실측).
        # detail page 에 listing selector 를 재사용하면 timeout → hydration delay 만 유지.
        dcard = SITES["dcard"]
        assert dcard.scan_full_page is False
        assert dcard.simulate_user is False
        assert dcard.override_navigator is False
        assert dcard.wait_until is None
        assert dcard.wait_for is None

    def test_nga_and_tieba_use_simulate_user_and_ua_rotation(self):
        # IP 차단엔 무력하지만 약한 anti-bot 회피용으로 시도.
        for site_id in ("nga", "tieba"):
            site = SITES[site_id]
            assert site.simulate_user is True, f"{site_id} simulate_user"
            assert site.user_agent_mode == "random", f"{site_id} user_agent_mode"

    # ── Bahamut NC 8개 게임 보드 ──
    _BAHAMUT_NC_IDS = (
        "bahamut_lineage", "bahamut_lineage_m", "bahamut_lineage_w",
        "bahamut_lineage_classic", "bahamut_aion", "bahamut_aion2",
        "bahamut_bns", "bahamut_tl",
    )

    def test_bahamut_nc_sites_all_registered(self):
        for sid in self._BAHAMUT_NC_IDS:
            assert sid in SITES, f"{sid} missing"
            assert SITES[sid].enabled is True

    def test_bahamut_nc_sites_have_distinct_bsn(self):
        import re
        bsns = set()
        for sid in self._BAHAMUT_NC_IDS:
            url = SITES[sid].board_urls[0]
            m = re.search(r"bsn=(\d+)", url)
            assert m, f"{sid} board_urls missing bsn"
            bsns.add(m.group(1))
        # 8 개 NC 게임이 모두 서로 다른 bsn 을 가져야 함.
        assert len(bsns) == len(self._BAHAMUT_NC_IDS), f"bsn 중복: {bsns}"

    def test_bahamut_nc_post_pattern_matches_C_php(self):
        import re
        for sid in self._BAHAMUT_NC_IDS:
            p = re.compile(SITES[sid].post_url_pattern)
            # page 1 형태
            assert p.match("https://forum.gamer.com.tw/C.php?bsn=842&snA=12345")
            # page 2+ 형태 (bPage=N 파라미터 앞에 붙음)
            assert p.match(
                "https://forum.gamer.com.tw/C.php?bPage=2&bsn=842&snA=715421&tnum=7"
            )
            # last=1 링크는 제외되어야 함 (dedup 불가)
            assert not p.match(
                "https://forum.gamer.com.tw/C.php?bPage=2&bsn=842&last=1&snA=715421&tnum=7"
            )
            # 보드 URL 은 매칭되면 안 된다.
            assert not p.match("https://forum.gamer.com.tw/B.php?bsn=842")

    def test_bahamut_nc_sites_have_content_selector(self):
        for sid in self._BAHAMUT_NC_IDS:
            sel = SITES[sid].css_selector or ""
            assert "c-article__content" in sel or "c-post__body" in sel

    # ── 52pojie ──
    def test_pojie_selector_covers_stickies_and_normal_threads(self):
        sel = SITES["52pojie"].css_selector or ""
        # 일반(.t_f) + sticky/일부 floor 호환([id^=postmessage_]) 둘 다 포함되어야 함.
        assert ".t_f" in sel
        assert "postmessage_" in sel

    def test_pojie_skips_page_1_for_real_threads(self):
        # forum-16-1.html 은 거의 전부 공지/导航 — 2페이지부터 시작.
        urls = SITES["52pojie"].board_urls
        assert not any("forum-16-1.html" in u for u in urls), "page 1은 sticky만 — 제외해야 함"
        assert any("forum-16-2.html" in u for u in urls)

    # ── NGA ──
    def test_nga_has_cn_accept_language(self):
        # UA 는 stealth 모드가 자동 생성하게 두고, Accept-Language 만 명시.
        nga = SITES["nga"]
        assert nga.headers is not None
        assert "zh-CN" in nga.headers.get("Accept-Language", "")

    def test_nga_has_mirror_domain_fallback(self):
        urls = SITES["nga"].board_urls
        assert any("bbs.nga.cn" in u for u in urls)
        assert any("ngabbs.com" in u for u in urls)

    def test_nga_post_pattern_accepts_both_domains(self):
        import re
        p = re.compile(SITES["nga"].post_url_pattern)
        assert p.match("https://bbs.nga.cn/read.php?tid=12345")
        assert p.match("https://ngabbs.com/read.php?tid=12345")

    # ── Tieba ──
    def test_tieba_documents_proxy_requirement(self):
        # 해외 IP 차단으로 인한 운영 메모가 명시되어 있어야 한다.
        note = SITES["tieba"].note
        assert "중국" in note or "proxy" in note.lower()

    # ── 제외 사이트 ──
    def test_tailstar_removed_from_registry(self):
        # 새 타겟 리스트에서 빠짐. 잔존 시 게시판 0건 사이트가 자동 시도되는 문제 회귀.
        assert "tailstar" not in SITES

    # ── PTT Mobile-game (혼합 보드 + title_keywords) ──
    def test_ptt_mobile_game_has_nc_keywords(self):
        s = SITES["ptt_mobile_game"]
        assert s.title_keywords is not None
        joined = "|".join(s.title_keywords)
        assert "天堂" in joined and "Lineage" in joined

    # ── Dcard online ──
    def test_dcard_and_online_both_use_title_keywords(self):
        for sid in ("dcard", "dcard_online"):
            s = SITES[sid]
            assert s.title_keywords is not None, f"{sid} missing title_keywords"

    def test_dcard_online_uses_delay_not_selector(self):
        # 2026-06-05: /f/online 은 게시글 링크 0건 → 線上遊戲 topic 으로 이동.
        # Dcard React CSS module 해시(PostList_entry_*)는 빌드마다 바뀌어 셀렉터 자체가 안티패턴.
        s = SITES["dcard_online"]
        assert "/topics/" in s.board_urls[0]
        assert s.wait_for is None, "dcard_online 셀렉터 의존 회귀 — wait_for 는 None 이어야 함"
        assert s.delay_before_return_html == 3.0
        assert s.max_retries == 1
        assert "/[A-Za-z0-9_-]+/p/" in s.post_url_pattern

    def test_dcard_game_board_selector_removed_after_detail_timeout(self):
        # 2026-06-05 smoke: listing OK 이후 detail page 에서 css:article timeout.
        assert SITES["dcard"].wait_for is None
        assert SITES["dcard"].delay_before_return_html == 3.0

    # ── PTT Lineage 보드 ──
    def test_ptt_targets_lineage_board(self):
        # 이전 C_Chat 에서 NC 전용 Lineage 보드로 교체.
        s = SITES["ptt"]
        assert any("/bbs/Lineage/" in u for u in s.board_urls)
        # 100% NC 보드라 title_keywords 불필요.
        assert s.title_keywords is None

    # ── enabled 사이트 전수 점검 ──
    def test_get_enabled_sites_contains_all_targets(self):
        enabled = get_enabled_sites()
        expected = {
            "inven_maple", "inven_lineage_classic",
            "ptt", "ptt_mobile_game",
            "dcard", "dcard_online",
            "bahamut_lineage", "bahamut_lineage_m", "bahamut_lineage_w",
            "bahamut_lineage_classic", "bahamut_aion", "bahamut_aion2",
            "bahamut_bns", "bahamut_tl",
            "52pojie",
        }
        assert expected.issubset(enabled.keys()), (
            f"missing: {expected - enabled.keys()}"
        )

    def test_china_anti_bot_sites_disabled(self):
        """nga / tieba 는 Bright Data PoC (2026-05-20) 결과 anti-bot 차단 확인 →
        out-of-scope, enabled=False 로 보관."""
        assert SITES["nga"].enabled is False
        assert SITES["tieba"].enabled is False
