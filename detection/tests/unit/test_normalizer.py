"""S0 Normalizer 단위 테스트 (Story 3-7) — 정규화 + 링크 추출."""

from __future__ import annotations

from detection.src.agents.normalizer import extract_links, normalize


def test_empty_input_returns_empty_result() -> None:
    result = normalize("")
    assert result.text == ""
    assert result.links == []


def test_zero_width_chars_removed() -> None:
    # 단어 사이 zero-width space 삽입으로 키워드 매칭 우회 시도.
    dirty = "핵​치​트 팝니다"
    result = normalize(dirty)
    assert "​" not in result.text
    assert "핵치트" in result.text


def test_nfkc_normalizes_fullwidth() -> None:
    # 전각 라틴/숫자 → 반각 통일.
    result = normalize("ＨＡＣＫ ０１２")
    assert "HACK" in result.text
    assert "012" in result.text


def test_homoglyph_cyrillic_mapped_to_latin() -> None:
    # 키릴 а/о/с 로 위장한 라틴 문자 복원.
    result = normalize("hасk")  # h + 키릴 а + 라틴 c + k
    assert result.text == "hack"


def test_repeated_chars_collapsed() -> None:
    # NFKC 안정 문자(완성형 음절·구두점)로 3회+ 연속 → 2회 축약 검증.
    result = normalize("대박요요요요요 팝니다!!!!!")
    assert "요요요" not in result.text
    assert "요요" in result.text
    assert "!!!" not in result.text


def test_extract_markdown_link() -> None:
    links = extract_links("다운로드 [여기](https://evil.example/hack.zip) 클릭")
    assert links == ["https://evil.example/hack.zip"]


def test_extract_bare_url() -> None:
    links = extract_links("판매중 https://t.me/secretchannel 연락주세요.")
    # 끝의 마침표는 제외되어야.
    assert links == ["https://t.me/secretchannel"]


def test_extract_links_dedup_preserves_order() -> None:
    text = (
        "첫째 https://a.example/1 "
        "[같은링크](https://a.example/1) "
        "둘째 https://b.example/2"
    )
    assert extract_links(text) == ["https://a.example/1", "https://b.example/2"]


def test_links_extracted_from_raw_before_collapse() -> None:
    # 반복 축약이 URL을 훼손하지 않아야 (예: 경로의 연속 문자).
    result = normalize("받기 https://x.example/aaaa/file 보세요")
    assert result.links == ["https://x.example/aaaa/file"]


def test_mixed_language_text_preserved() -> None:
    result = normalize("外掛 판매 hack for sale 私服")
    assert "外掛" in result.text
    assert "私服" in result.text
    assert "hack" in result.text


def test_removed_char_count_nonzero_when_zero_width_stripped() -> None:
    # U+200B (zero-width space) 1자 삽입 → removed_char_count ≥ 1.
    dirty = "핵​치트"
    result = normalize(dirty)
    assert result.removed_char_count >= 1


def test_removed_char_count_zero_for_clean_text() -> None:
    result = normalize("정상적인 게시글입니다")
    assert result.removed_char_count == 0


def test_extract_links_strips_cjk_trailing_period() -> None:
    # URL 뒤 한중일 마침표(。)는 URL의 일부가 아니므로 제거.
    links = extract_links("다운로드 https://evil.example/hack。")
    assert links == ["https://evil.example/hack"]


def test_extract_links_strips_cjk_trailing_comma() -> None:
    # URL 뒤에 한중일 쉼표(，)가 있고 이후 공백으로 분리되면 쉼표를 제거.
    links = extract_links("링크 https://evil.example/x， 다음 텍스트")
    assert links == ["https://evil.example/x"]
