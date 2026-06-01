"""게임별 프롬프트 오버레이 레지스트리 (Stage 1 — per-game 분화).

`source_id`(CrawlEvent에서 전달, 크롤러 SITES 레지스트리 키)를 game_key로 매핑하고,
`detection/src/prompts/games/<game_key>.md` 파일의 오버레이 텍스트를 로드한다.

매핑/파일이 없으면 빈 문자열을 반환 → 베이스 프롬프트로 fallback (동작 중립).
오버레이는 베이스 SYSTEM_PROMPT의 9유형/confidence 루브릭을 **재정의하지 않고 보강만** 한다.
"""

from __future__ import annotations

from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent
_GAMES_DIR = _PROMPTS_DIR / "games"
_TYPE_GUIDANCE_PATH = _PROMPTS_DIR / "type_guidance.md"

# source_id → game_key. 같은 게임을 가리키는 source_id(가족)는 하나의 game_key로 묶는다.
# 키는 crawler/src/sites/registry.py SITES dict의 실제 키와 일치해야 한다.
SOURCE_ID_TO_GAME: dict[str, str] = {
    # 리니지 PC/클래식
    "ptt": "lineage",
    "inven_lineage_classic": "lineage",
    "bahamut_lineage": "lineage",
    "bahamut_lineage_classic": "lineage",
    # 리니지 모바일 (M/W)
    "bahamut_lineage_m": "lineage_mobile",
    "bahamut_lineage_w": "lineage_mobile",
    # 아이온
    "bahamut_aion": "aion",
    "bahamut_aion2": "aion",
    # 블레이드 & 소울
    "bahamut_bns": "bns",
    # 쓰론 앤 리버티
    "bahamut_tl": "tl",
    # 혼합 모바일/온라인 (NC 키워드 필터)
    "ptt_mobile_game": "mixed_mobile",
    "dcard": "mixed_mobile",
    "dcard_online": "mixed_mobile",
    # 크래킹/리버싱 포럼
    "52pojie": "cracking_forum",
    # 주의: SITES의 nga·tieba는 의도적으로 비매핑. 현재 enabled=False(PoC anti-bot 차단)이고,
    # 향후 재활성되더라도 매핑/오버레이가 없으면 베이스 프롬프트로 안전하게 fallback한다.
    # 전용 오버레이가 필요해지면 game_key 추가 + games/<key>.md 작성.
}


def _load_all_overlays() -> dict[str, str]:
    """games/*.md 를 import 시점에 1회 로드. 파일명(stem)이 game_key."""
    overlays: dict[str, str] = {}
    if _GAMES_DIR.exists():
        for path in sorted(_GAMES_DIR.glob("*.md")):
            text = path.read_text(encoding="utf-8").strip()
            if text:
                overlays[path.stem] = text
    return overlays


def _load_type_guidance() -> str:
    """유형 disambiguation 가이드 (Stage 2-A). 게임 무관·항상 적용. 파일 없으면 ""."""
    if _TYPE_GUIDANCE_PATH.exists():
        return _TYPE_GUIDANCE_PATH.read_text(encoding="utf-8").strip()
    return ""


_OVERLAYS: dict[str, str] = _load_all_overlays()
_TYPE_GUIDANCE: str = _load_type_guidance()


def get_type_guidance() -> str:
    """모든 게시글에 적용되는 유형 판별 가이드 텍스트. 파일 없으면 "" (베이스만)."""
    return _TYPE_GUIDANCE


def get_game_overlay(source_id: str | None) -> str:
    """source_id에 해당하는 게임 오버레이 텍스트. 매핑/파일 없으면 "" (베이스 fallback)."""
    if not source_id:
        return ""
    game_key = SOURCE_ID_TO_GAME.get(source_id)
    if not game_key:
        return ""
    return _OVERLAYS.get(game_key, "")
