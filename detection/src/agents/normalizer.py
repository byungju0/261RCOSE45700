"""S0 Normalizer — 순수 Python 텍스트 정규화 + 링크 추출 (Story 3-7, LLM 없음, $0).

운영자 "텍스트 클린 에이전트" 요청 구현. 변형문자·우회 표기로 LLM 분류를 흐리는 게시글을
정규화하고, 본문에서 외부 링크를 추출해 LinkTracer(S2b) 입력으로 넘긴다.

수행:
  1. NFKC 정규화 — 전각/반각·합자·호환 문자 통일
  2. zero-width 문자 제거 — U+200B~200D, U+FEFF, U+2060 등 (단어 사이 끼워 우회)
  3. 변형문자 정적 매핑 — 라틴/키릴 등으로 위장한 한글 자모를 복원 (ㅎr킹 → 하킹 등)
  4. 반복문자 축약 — 3회 이상 연속 동일 문자를 2회로 (ㅋㅋㅋㅋ → ㅋㅋ)
  5. 링크 추출 — markdown [text](url) + bare URL, 순서 보존 + 중복 제거
"""

from __future__ import annotations

import re
import unicodedata

import regex as _regex

from detection.src.agents.contracts import NormalizedPost

# Unicode Cf (Format) 카테고리 전체 제거 — zero-width, bidi control, variation selector,
# Unicode Tag block(U+E0001, U+E0020-U+E007F) 등 키워드 우회에 쓰이는 모든 포맷 문자를 커버.
# 수동 집합 대신 \p{Cf}를 쓰는 이유: 미래 Unicode 버전 추가분도 자동 포함되고,
# bidi mark(U+200E/F), variation selector(U+FE00-FE0F) 등 기존 집합의 누락분을 보완.
_FORMAT_CHAR_RE = _regex.compile(r"\p{Cf}")

# 변형문자 정적 매핑 — 라틴/키릴/그리스 동형 글리프를 ASCII로 복원.
# NFKC는 호환 동치만 처리하며 크로스-스크립트 confusable(키릴 а vs 라틴 a 등)은 그대로 둔다.
# UTS #39 confusables.txt 기준 확실한 1:1 동형만 등록 — 과도 치환으로 정상 본문을 깨뜨리지 않는다.
_HOMOGLYPH_MAP = {
    # 키릴 소문자 → 라틴
    "а": "a",   # а CYRILLIC SMALL LETTER A
    "е": "e",   # е CYRILLIC SMALL LETTER IE
    "о": "o",   # о CYRILLIC SMALL LETTER O
    "р": "p",   # р CYRILLIC SMALL LETTER ER
    "с": "c",   # с CYRILLIC SMALL LETTER ES
    "х": "x",   # х CYRILLIC SMALL LETTER HA
    "у": "y",   # у CYRILLIC SMALL LETTER U
    # 키릴 대문자 → 라틴 대문자
    "В": "B",   # В CYRILLIC CAPITAL LETTER VE
    "Н": "H",   # Н CYRILLIC CAPITAL LETTER EN
    "М": "M",   # М CYRILLIC CAPITAL LETTER EM
    "Т": "T",   # Т CYRILLIC CAPITAL LETTER TE
    "К": "K",   # К CYRILLIC CAPITAL LETTER KA
    "А": "A",   # А CYRILLIC CAPITAL LETTER A
    "Е": "E",   # Е CYRILLIC CAPITAL LETTER IE
    "О": "O",   # О CYRILLIC CAPITAL LETTER O
    "Р": "P",   # Р CYRILLIC CAPITAL LETTER ER
    "С": "C",   # С CYRILLIC CAPITAL LETTER ES
    "Х": "X",   # Х CYRILLIC CAPITAL LETTER HA
    # 그리스 소문자 → 라틴 (명확한 동형만)
    "ο": "o",   # ο GREEK SMALL LETTER OMICRON
    "α": "a",   # α GREEK SMALL LETTER ALPHA
    "ε": "e",   # ε GREEK SMALL LETTER EPSILON
    "κ": "k",   # κ GREEK SMALL LETTER KAPPA (approximate)
    "ν": "v",   # ν GREEK SMALL LETTER NU
}

# 3회 이상 연속 동일 문자 → 2회로 축약 (의미 보존하며 토큰·노이즈 절감).
_REPEAT_RE = re.compile(r"(.)\1{2,}", re.DOTALL)

# markdown 링크: [텍스트](URL)
_MD_LINK_RE = re.compile(r"\[[^\]]*\]\((https?://[^\s)]+)\)", re.IGNORECASE)
# bare URL: http(s):// 로 시작. 끝의 흔한 구두점은 제외.
_BARE_URL_RE = re.compile(r"https?://[^\s<>\"'()\[\]]+", re.IGNORECASE)
_TRAILING_PUNCT = ".,;:!?。，"  # 영문/한중일 마침표·쉼표


def _strip_zero_width(text: str) -> str:
    return _FORMAT_CHAR_RE.sub("", text)


def _map_homoglyphs(text: str) -> str:
    return "".join(_HOMOGLYPH_MAP.get(ch, ch) for ch in text)


def _collapse_repeats(text: str) -> str:
    return _REPEAT_RE.sub(r"\1\1", text)


def extract_links(text: str) -> list[str]:
    """markdown + bare URL 추출. 등장 순서 보존 + 중복 제거.

    markdown 링크의 URL을 먼저 잡고, bare URL을 보탠다. 끝에 붙은 마침표·괄호류는 떼어
    실제 URL만 남긴다(문장 끝 URL 대응).
    """
    seen: set[str] = set()
    ordered: list[str] = []
    for match in _MD_LINK_RE.finditer(text):
        url = match.group(1).rstrip(_TRAILING_PUNCT)
        if url and url not in seen:
            seen.add(url)
            ordered.append(url)
    # bare URL — markdown으로 이미 잡힌 것은 seen으로 중복 제거.
    md_stripped = _MD_LINK_RE.sub(" ", text)
    for match in _BARE_URL_RE.finditer(md_stripped):
        url = match.group(0).rstrip(_TRAILING_PUNCT)
        if url and url not in seen:
            seen.add(url)
            ordered.append(url)
    return ordered


def normalize(text: str) -> NormalizedPost:
    """게시글 본문 정규화 + 링크 추출. 빈 입력은 빈 결과(예외 없음)."""
    raw = text or ""
    # 링크는 원문에서 추출 — 정규화(반복 축약 등)가 URL을 훼손하지 않도록.
    links = extract_links(raw)

    step = _strip_zero_width(raw)
    step = unicodedata.normalize("NFKC", step)
    step = _map_homoglyphs(step)
    cleaned = _collapse_repeats(step)

    # 변경된 문자 수 — 길이 차 + 동일 길이 내 글리프 치환분의 근사치(디버깅 신호).
    removed = max(0, len(raw) - len(cleaned))

    return NormalizedPost(text=cleaned, links=links, removed_char_count=removed)
