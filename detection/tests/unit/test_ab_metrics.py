"""A/B 메트릭 — post_id 조인 + Tier별 Recall/Precision/confusion + 비용 분포 (Story 3-9).

순수 함수 단위 테스트 (DB·OpenAI 무관). 고정 입력으로 TP/FN/FP 경계, unknown 제외,
post_id 조인 함정, p95 백분위, 이미지 유/무 분리를 검증한다.
"""

from __future__ import annotations

import math

from detection.scripts.ab_metrics import (
    agreement,
    build_label_map,
    cost_summary,
    illegal_detection_rate,
    join_predictions,
    percentile,
    render_ab_markdown,
    tier_metrics,
)


# ── build_label_map: {post_id: human_label} (null/unknown 제외) ──────────────


def test_build_label_map_excludes_null_and_unknown() -> None:
    rows = [
        {"post_id": 1, "human_label": "핵_치트"},
        {"post_id": 2, "human_label": "unknown"},  # 판단 불가 → 제외
        {"post_id": 3, "human_label": None},        # 미라벨 → 제외
        {"post_id": 4, "human_label": "  사설서버  "},  # 공백 trim
        {"post_id": 5, "human_label": ""},          # 빈 문자열 → 제외
    ]
    assert build_label_map(rows) == {1: "핵_치트", 4: "사설서버"}


# ── join_predictions: ground truth는 원본 행에만 → post_id로 조인 ─────────────


def test_join_predictions_joins_on_post_id_only() -> None:
    """재분류된 agentic 행에는 human_label이 없다 — label_map(post_id)로 조인해야 한다."""
    label_map = {1: "핵_치트", 4: "사설서버"}
    mode_rows = [
        {"post_id": 1, "type": "핵_치트"},
        {"post_id": 4, "type": "핵_치트"},  # 오분류
        {"post_id": 9, "type": "기타"},     # ground truth 없음 → 제외
    ]
    joined = join_predictions(label_map, mode_rows)
    assert joined == [
        {"post_id": 1, "human_label": "핵_치트", "type": "핵_치트"},
        {"post_id": 4, "human_label": "사설서버", "type": "핵_치트"},
    ]


# ── agreement: 라벨==예측 비율 (judgeable 분모) ──────────────────────────────


def test_agreement_counts_matches() -> None:
    label_map = {1: "핵_치트", 4: "사설서버"}
    mode_rows = [{"post_id": 1, "type": "핵_치트"}, {"post_id": 4, "type": "핵_치트"}]
    snap = agreement(label_map, mode_rows)
    assert snap["judgeable"] == 2
    assert snap["agree"] == 1
    assert snap["agreement"] == 0.5


def test_agreement_empty_is_zero_not_crash() -> None:
    assert agreement({}, [])["agreement"] == 0.0


# ── tier_metrics: Tier별 Recall/Precision + confusion (신규) ──────────────────


def _tier_fixture() -> tuple[dict, list]:
    # truth: 1=T1 2=T1 3=T2 5=T3 4=T4 / pred: 2를 T4로 오분류, 5는 같은 T3 다른 type.
    label_map = {1: "핵_치트", 2: "매크로_판매", 3: "사설서버", 4: "기타", 5: "현금화"}
    mode_rows = [
        {"post_id": 1, "type": "핵_치트"},     # T1 → T1 TP
        {"post_id": 2, "type": "기타"},        # T1 → T4 (FN T1, FP T4)
        {"post_id": 3, "type": "사설서버"},     # T2 → T2 TP
        {"post_id": 4, "type": "기타"},        # T4 → T4 TP
        {"post_id": 5, "type": "광고_도배"},    # T3 → T3 TP (type 달라도 같은 Tier)
    ]
    return label_map, mode_rows


def test_tier_metrics_recall_precision_boundaries() -> None:
    label_map, mode_rows = _tier_fixture()
    m = tier_metrics(label_map, mode_rows)
    t1 = m["per_tier"]["T1"]
    assert (t1["tp"], t1["fn"], t1["fp"]) == (1, 1, 0)
    assert t1["recall"] == 0.5
    assert t1["precision"] == 1.0
    t4 = m["per_tier"]["T4"]
    assert (t4["tp"], t4["fn"], t4["fp"]) == (1, 0, 1)
    assert t4["recall"] == 1.0
    assert t4["precision"] == 0.5
    t2 = m["per_tier"]["T2"]
    assert t2["recall"] == 1.0 and t2["precision"] == 1.0


def test_tier_metrics_confusion_matrix() -> None:
    label_map, mode_rows = _tier_fixture()
    m = tier_metrics(label_map, mode_rows)
    conf = m["confusion"]
    assert conf[("T1", "T1")] == 1
    assert conf[("T1", "T4")] == 1  # 매크로_판매(T1) → 기타(T4) 오분류
    assert conf[("T2", "T2")] == 1
    assert conf[("T3", "T3")] == 1
    assert conf[("T4", "T4")] == 1


def test_tier_metrics_recall_none_when_no_truth_for_tier() -> None:
    """truth에 해당 Tier가 0건이면 Recall은 None(0/0 분모 가드) — 0.0 아님."""
    label_map = {1: "핵_치트"}
    mode_rows = [{"post_id": 1, "type": "핵_치트"}]
    m = tier_metrics(label_map, mode_rows)
    assert m["per_tier"]["T2"]["recall"] is None  # T2 truth 없음
    assert m["per_tier"]["T1"]["recall"] == 1.0


def test_tier_metrics_skips_posts_not_reclassified() -> None:
    """해당 모드로 재분류되지 않은 post는 메트릭에서 제외 (조인 누락 가드)."""
    label_map = {1: "핵_치트", 2: "사설서버"}
    mode_rows = [{"post_id": 1, "type": "핵_치트"}]  # post 2 미재분류
    m = tier_metrics(label_map, mode_rows)
    assert m["per_tier"]["T1"]["tp"] == 1
    assert m["per_tier"]["T2"]["tp"] == 0
    assert m["per_tier"]["T2"]["fn"] == 0  # 미재분류는 FN으로도 안 셈


# ── illegal_detection_rate: 명확 케이스 정탐율 (PRD ≥90%) ─────────────────────


def test_illegal_detection_rate() -> None:
    label_map, mode_rows = _tier_fixture()
    # truth illegal(T1~T3): 1,2,3,5 → pred illegal: 1(T1) 3(T2) 5(T3) yes, 2(T4) no → 3/4
    rate = illegal_detection_rate(label_map, mode_rows)
    assert rate["truth_illegal"] == 4
    assert rate["detected_illegal"] == 3
    assert rate["rate"] == 0.75


# ── percentile: stdlib만, 선형보간 ──────────────────────────────────────────


def test_percentile_median_and_p95() -> None:
    assert percentile([1, 2, 3, 4, 5], 50) == 3.0
    assert math.isclose(percentile([1, 2, 3, 4], 95), 3.85)


def test_percentile_edge_cases() -> None:
    assert percentile([], 95) is None
    assert percentile([0.005], 95) == 0.005  # 단일 표본
    assert percentile([0.001, 0.02], 100) == 0.02  # 최댓값


# ── cost_summary: 평균·p95 + 이미지 유/무 분리 ───────────────────────────────


def test_cost_summary_splits_by_image_presence() -> None:
    rows = [
        {"post_id": 1, "cost_usd": 0.004, "has_image": False},
        {"post_id": 2, "cost_usd": 0.012, "has_image": True},
        {"post_id": 3, "cost_usd": 0.002, "has_image": False},
    ]
    s = cost_summary(rows)
    assert s["all"]["count"] == 3
    assert math.isclose(s["all"]["mean"], (0.004 + 0.012 + 0.002) / 3)
    assert s["all"]["max"] == 0.012
    assert s["with_image"]["count"] == 1
    assert s["with_image"]["mean"] == 0.012
    assert s["without_image"]["count"] == 2
    assert math.isclose(s["without_image"]["mean"], 0.003)


def test_cost_summary_empty() -> None:
    s = cost_summary([])
    assert s["all"]["count"] == 0
    assert s["all"]["mean"] is None
    assert s["all"]["p95"] is None


# ── render: 비교표가 깨지지 않고 핵심 수치를 담는다 ──────────────────────────


def test_render_ab_markdown_contains_tiers_and_costs() -> None:
    label_map, mode_rows = _tier_fixture()
    single = {
        "agreement": agreement(label_map, mode_rows),
        "tier": tier_metrics(label_map, mode_rows),
        "illegal": illegal_detection_rate(label_map, mode_rows),
    }
    # agentic는 살짝 다른 예측(2를 정분류)으로 대비.
    agentic_rows = [dict(r) for r in mode_rows]
    agentic_rows[1]["type"] = "매크로_판매"
    agentic = {
        "agreement": agreement(label_map, agentic_rows),
        "tier": tier_metrics(label_map, agentic_rows),
        "illegal": illegal_detection_rate(label_map, agentic_rows),
    }
    cost = cost_summary([{"post_id": 1, "cost_usd": 0.004, "has_image": False}])
    md = render_ab_markdown(
        single=single, agentic=agentic, cost=cost, escalation_rate=0.35,
        sample_size=5,
    )
    assert "T1" in md and "Recall" in md and "Precision" in md
    assert "agreement" in md.lower()
    assert "$0.0040" in md or "0.004" in md  # 평균 비용 표기
    assert "35" in md  # escalation율 %
