"""프롬프트 조립 레지스트리 — 공용 도메인 가이드 (Story 3-7, 라우팅 제거).

2026-06-11 재정의: 사이트→게임 라우팅(`SOURCE_ID_TO_GAME` + `games/*.md` 오버레이) 제거.
게임 맥락은 분류기가 자가 추론하고, 큐레이션 지식은 단일 공용 `domain_guide.md`로 항상 주입.
"""

from __future__ import annotations

from detection.src.pipeline.llm_client import build_system_prompt
from detection.src.prompts.registry import get_domain_guide, get_type_guidance


def test_type_guidance_loaded() -> None:
    assert "유형 판별 가이드:" in get_type_guidance()


def test_domain_guide_loaded() -> None:
    guide = get_domain_guide()
    assert "공용 도메인 가이드" in guide
    # 게임별 파일에서 병합된 은어·오탐 지식이 보존됐는지 (지식 보존 — FR12-C).
    assert "外掛" in guide  # 핵/오토 은어
    assert "私服" in guide  # 사설서버 은어
    assert "메이플스토리" in guide  # NEXON 비교군 오탐 방지 규칙


def test_system_prompt_includes_base_type_and_domain_guide() -> None:
    prompt = build_system_prompt()
    assert "NC AI 게임 보안 분석가" in prompt  # 베이스
    assert "유형 판별 가이드:" in prompt       # Stage 2-A
    assert "공용 도메인 가이드" in prompt       # 공용 도메인 가이드


def test_system_prompt_is_site_independent() -> None:
    # source_id가 달라도 동일 프롬프트 — 사이트 종속 제거 검증 (FR12-C 라우팅 제거).
    assert build_system_prompt("bahamut_lineage") == build_system_prompt("totally_unknown_site")
    assert build_system_prompt(None) == build_system_prompt("52pojie")
