"""경량 정확도 스냅샷 — 일치율 + 커버리지 집계 (Story 3-5). DB 무관 (pure 함수)."""

from __future__ import annotations

from detection.scripts.labelset_snapshot import compute_snapshot, render_markdown


def _row(source_id: str, human_label: str, predicted_type: str) -> dict:
    return {"source_id": source_id, "human_label": human_label, "type": predicted_type}


def test_labelset_snapshot_aggregates() -> None:
    rows = [
        _row("ptt", "핵_치트", "핵_치트"),            # lineage, agree
        _row("bahamut_lineage", "사설서버", "핵_치트"),  # lineage, disagree
        _row("bahamut_aion", "핵_치트", "핵_치트"),      # aion, agree
        _row("bahamut_aion", "계정_거래", "계정_거래"),   # aion, agree
        _row("totally_unknown", "기타", "기타"),          # unmapped, agree
        {"source_id": "ptt", "human_label": None, "type": "핵_치트"},  # 미라벨 → 무시
    ]

    snap = compute_snapshot(rows)

    assert snap["total"] == 5  # None 행 제외
    assert snap["judgeable"] == 5  # unknown 없음 → 전부 판단 가능
    assert snap["agree"] == 4
    assert snap["agreement"] == 4 / 5
    assert snap["by_game"] == {"lineage": 2, "aion": 2, "(unmapped)": 1}
    assert snap["by_game_usable"] == {"lineage": 2, "aion": 2, "(unmapped)": 1}  # unknown 없음
    assert snap["by_type"] == {"핵_치트": 2, "사설서버": 1, "계정_거래": 1, "기타": 1}


def test_agreement_excludes_unknown_from_denominator() -> None:
    """unknown 라벨은 type(9-enum)과 매칭 불가 → 일치율 분모(judgeable)에서 제외하되 커버리지엔 포함."""
    rows = [
        _row("ptt", "핵_치트", "핵_치트"),   # judgeable, agree
        _row("ptt", "unknown", "핵_치트"),    # unknown → 분모 제외
        _row("ptt", "unknown", "기타"),       # unknown → 분모 제외
    ]
    snap = compute_snapshot(rows)
    assert snap["total"] == 3        # 커버리지엔 unknown 포함
    assert snap["judgeable"] == 1    # 일치율 분모는 unknown 제외
    assert snap["agree"] == 1
    assert snap["agreement"] == 1.0  # 1/1 (1/3 아님 — 왜곡 방지)
    assert snap["by_game"] == {"lineage": 3}          # 커버리지는 unknown 포함
    assert snap["by_game_usable"] == {"lineage": 1}   # 코퍼스 충분성은 unknown 제외 (#9)
    assert snap["by_type"]["unknown"] == 2

    md = render_markdown(snap)
    assert "100.0%" in md  # 분모 1 기준 100%
    assert "unknown 2건" in md  # unknown 카운트 가시화


def test_labelset_snapshot_empty() -> None:
    snap = compute_snapshot([])
    assert snap == {
        "total": 0, "judgeable": 0, "agree": 0, "agreement": 0.0,
        "by_game": {}, "by_game_usable": {}, "by_type": {},
    }
    # 빈 스냅샷도 마크다운 렌더링이 깨지지 않는다 (N/A 표기)
    md = render_markdown(snap)
    assert "라벨 총건수: **0**" in md
    assert "N/A" in md


def test_render_markdown_includes_coverage_rows() -> None:
    snap = compute_snapshot([_row("ptt", "핵_치트", "핵_치트")])
    md = render_markdown(snap)
    assert "| lineage | 1 | 1 |" in md  # 라벨 수 | 사용 가능(unknown 제외)
    assert "| 핵_치트 | 1 |" in md
    assert "100.0%" in md
