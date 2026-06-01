"""게임별 프롬프트 오버레이 레지스트리 — 매핑·fallback (Stage 1)."""

from __future__ import annotations

from detection.src.prompts.registry import (
    SOURCE_ID_TO_GAME,
    get_game_overlay,
    get_type_guidance,
)


def test_known_source_id_returns_overlay() -> None:
    # 크롤러 SITES 키와 일치하는 source_id는 게임 오버레이를 반환.
    overlay = get_game_overlay("bahamut_lineage")
    assert overlay
    assert "게임 맥락:" in overlay


def test_family_source_ids_map_to_same_game() -> None:
    # 리니지 가족 source_id는 동일 game_key(lineage)로 묶여 같은 오버레이를 공유.
    assert SOURCE_ID_TO_GAME["ptt"] == "lineage"
    assert SOURCE_ID_TO_GAME["bahamut_lineage_classic"] == "lineage"
    assert get_game_overlay("ptt") == get_game_overlay("bahamut_lineage")


def test_none_and_unknown_source_id_return_empty() -> None:
    assert get_game_overlay(None) == ""
    assert get_game_overlay("") == ""
    assert get_game_overlay("totally_unknown_site") == ""


def test_all_mapped_game_keys_have_overlay_files() -> None:
    # 매핑된 모든 game_key는 대응하는 오버레이 파일이 존재해야 한다 (누락 시 silent fallback 방지).
    for source_id in SOURCE_ID_TO_GAME:
        assert get_game_overlay(source_id), f"오버레이 누락: {source_id}"


def test_type_guidance_loaded() -> None:
    guidance = get_type_guidance()
    assert "유형 판별 가이드:" in guidance
