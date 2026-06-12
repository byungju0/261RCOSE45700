"""프롬프트 조립 레지스트리 — 공용 도메인 가이드 (Story 3-7, FR12-C).

2026-06-11 재정의: 사이트→게임 라우팅(`SOURCE_ID_TO_GAME` + `games/*.md` 게임별 오버레이)을
분류 경로에서 제거했다. 게임 맥락은 S1 트리아지가 게시글 본문에서 자가 추론하고(game_context),
게임 라벨에 종속되지 않는 큐레이션 지식(은어 사전·오탐 방지 규칙)은 단일 공용
`domain_guide.md`로 모든 게시글에 항상 주입한다.

라벨링 CLI(`scripts/label_detections.py`)는 자체 source_id→game 매핑을 보유한다 — 분류 경로와
무관(Story 3-5 라벨 코퍼스 game_key 그룹핑 전용).

파일이 없으면 빈 문자열 반환 → 베이스 프롬프트로 fallback (동작 중립).
"""

from __future__ import annotations

from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent
_TYPE_GUIDANCE_PATH = _PROMPTS_DIR / "type_guidance.md"
_DOMAIN_GUIDE_PATH = _PROMPTS_DIR / "domain_guide.md"


def _load_text(path: Path) -> str:
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    return ""


_TYPE_GUIDANCE: str = _load_text(_TYPE_GUIDANCE_PATH)
_DOMAIN_GUIDE: str = _load_text(_DOMAIN_GUIDE_PATH)


def get_type_guidance() -> str:
    """모든 게시글에 적용되는 유형 판별 가이드(Stage 2-A). 파일 없으면 "" (베이스만)."""
    return _TYPE_GUIDANCE


def get_domain_guide() -> str:
    """모든 게시글에 적용되는 공용 도메인 가이드(은어·오탐 규칙). 파일 없으면 "" (베이스만)."""
    return _DOMAIN_GUIDE
