"""few-shot 코퍼스 빌드 — 그룹화/상한/빈 코퍼스 (Story 3-5). DB 무관 (pure 함수)."""

from __future__ import annotations

import json

import pytest

from detection.scripts.build_fewshot_corpus import build_corpus, write_corpus


def _row(source_id: str, label: str, conf: float, body: str = "본문 텍스트",
         row_id: int = 0) -> dict:
    return {
        "id": row_id,
        "source_id": source_id,
        "human_label": label,
        "body": body,
        "reason_ko": "근거",
        "tier": "T1",
        "confidence": conf,
    }


def test_build_fewshot_corpus_groups_by_game_and_type() -> None:
    rows = [
        # lineage(ptt) × 핵_치트 4건 → per_group=2 상한, confidence 상위 2건만
        _row("ptt", "핵_치트", 0.99, "핵 A"),
        _row("ptt", "핵_치트", 0.70, "핵 B"),
        _row("ptt", "핵_치트", 0.95, "핵 C"),
        _row("bahamut_lineage", "핵_치트", 0.50, "핵 D"),  # 같은 game_key=lineage
        # lineage × 사설서버 1건 → 별도 type 그룹
        _row("ptt", "사설서버", 0.88, "사설"),
        # aion × 핵_치트 1건 → 별도 game_key
        _row("bahamut_aion", "핵_치트", 0.80, "아이온 핵"),
        # unknown 라벨 → 코퍼스 제외
        _row("ptt", "unknown", 0.99, "모름"),
        # 미매핑 source_id → 제외
        _row("totally_unknown_site", "핵_치트", 0.99, "미매핑"),
    ]

    corpus = build_corpus(rows, per_group=2)

    assert set(corpus.keys()) == {"lineage", "aion"}

    # lineage: 핵_치트 상위 2건(0.99, 0.95) + 사설서버 1건 = 3 레코드
    lineage_labels = sorted(r["label"] for r in corpus["lineage"])
    assert lineage_labels == ["사설서버", "핵_치트", "핵_치트"]
    lineage_texts = {r["text"] for r in corpus["lineage"] if r["label"] == "핵_치트"}
    assert lineage_texts == {"핵 A", "핵 C"}  # confidence 상위 2 (0.70/0.50 탈락)

    # aion: 핵_치트 1건
    assert len(corpus["aion"]) == 1
    assert corpus["aion"][0]["label"] == "핵_치트"

    # 레코드 포맷 계약
    rec = corpus["aion"][0]
    assert set(rec.keys()) == {"text", "label", "reason_ko", "tier"}
    assert rec["tier"] == "T1"


def test_build_fewshot_corpus_empty_is_noop(tmp_path) -> None:
    # 라벨 0건 → 빈 dict
    assert build_corpus([]) == {}
    # unknown/미매핑만 있어도 빈 dict (동작 중립)
    only_excluded = [
        {"source_id": "ptt", "human_label": "unknown", "body": "x",
         "reason_ko": "", "tier": "T4", "confidence": 0.5},
        {"source_id": "nope", "human_label": "핵_치트", "body": "x",
         "reason_ko": "", "tier": "T1", "confidence": 0.9},
    ]
    assert build_corpus(only_excluded) == {}

    # write_corpus는 빈 코퍼스에 파일을 만들지 않는다
    written = write_corpus({}, out_dir=tmp_path)
    assert written == {}
    assert list(tmp_path.glob("*.jsonl")) == []


def test_write_corpus_emits_valid_jsonl(tmp_path) -> None:
    corpus = build_corpus([_row("ptt", "핵_치트", 0.9, "핵 팝니다")], per_group=3)
    written = write_corpus(corpus, out_dir=tmp_path)

    assert written == {"lineage": 1}
    path = tmp_path / "lineage.jsonl"
    assert path.exists()
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec == {"text": "핵 팝니다", "label": "핵_치트", "reason_ko": "근거", "tier": "T1"}


def _rec(text: str = "x") -> dict:
    return {"text": text, "label": "핵_치트", "reason_ko": "", "tier": "T1"}


def test_write_corpus_removes_stale_files_on_rebuild(tmp_path) -> None:
    """재빌드 시 코퍼스에서 빠진 game_key의 옛 .jsonl이 제거된다 (stale 방지)."""
    first = write_corpus({"lineage": [_rec("a")], "aion": [_rec("b")]}, out_dir=tmp_path)
    assert set(first) == {"lineage", "aion"}
    assert (tmp_path / "aion.jsonl").exists()

    # 2차: aion이 코퍼스에서 빠짐 → 옛 aion.jsonl은 제거, lineage만 남아야 함
    second = write_corpus({"lineage": [_rec("a2")]}, out_dir=tmp_path)
    assert second == {"lineage": 1}
    assert (tmp_path / "lineage.jsonl").exists()
    assert not (tmp_path / "aion.jsonl").exists()  # stale 제거됨

    # 라벨 0건 재빌드 → 모든 .jsonl 제거 (동작 중립 fallback 복원)
    assert write_corpus({}, out_dir=tmp_path) == {}
    assert list(tmp_path.glob("*.jsonl")) == []


def test_write_corpus_preserves_non_jsonl(tmp_path) -> None:
    """README.md 등 비-jsonl 파일은 정리 대상이 아니다."""
    (tmp_path / "README.md").write_text("포맷 계약", encoding="utf-8")
    write_corpus({"lineage": [_rec("a")]}, out_dir=tmp_path)
    assert (tmp_path / "README.md").read_text(encoding="utf-8") == "포맷 계약"


def test_build_corpus_rejects_nonpositive_per_group() -> None:
    """per_group 0/음수는 코퍼스를 비우거나 음수 슬라이싱으로 그룹을 깎으므로 차단."""
    rows = [_row("ptt", "핵_치트", 0.9)]
    with pytest.raises(ValueError, match="per_group"):
        build_corpus(rows, per_group=0)
    with pytest.raises(ValueError, match="per_group"):
        build_corpus(rows, per_group=-1)


def test_build_corpus_tiebreak_is_deterministic() -> None:
    """동일 confidence 그룹은 id 오름차순으로 결정적 선택 (입력/DB 힙 순서 무관 — #8)."""
    rows = [
        _row("ptt", "핵_치트", 0.90, body="C", row_id=3),
        _row("ptt", "핵_치트", 0.90, body="A", row_id=1),
        _row("ptt", "핵_치트", 0.90, body="D", row_id=4),
        _row("ptt", "핵_치트", 0.90, body="B", row_id=2),
    ]
    corpus = build_corpus(rows, per_group=2)
    assert [r["text"] for r in corpus["lineage"]] == ["A", "B"]  # id 1,2 — 결정적
