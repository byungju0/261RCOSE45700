"""A/B 정확도·비용 메트릭 — 순수 함수 (Story 3-9). DB·OpenAI 무관 → 단위 테스트 대상.

`labelset_snapshot.compute_snapshot`(agreement)을 보완한다:
  - **agreement**: 라벨 == 예측 비율 (judgeable 분모, unknown 제외). compute_snapshot과 동일 규율을
    post_id 조인 입력으로 재구현 — A/B는 재분류 행에 human_label이 없어 같은-행 비교가 불가하므로
    `{post_id: human_label}` 맵으로 조인한다(3-9 핵심 함정).
  - **Tier별 Recall/Precision + confusion matrix**: compute_snapshot에 없는 신규 계산.
    type→Tier는 `tier_router.TYPE_TO_TIER` SSOT 재사용. PRD 목표 Recall T1≥0.85/T2≥0.70/T3≥0.55.
  - **비용 분포**: 평균·p95(stdlib 선형보간)·이미지 유/무 분리. p95는 분포가 필요하므로 게시글별
    cost_usd 리스트에서 산출.

설계: DB I/O는 `ab_compare.py`가 담당하고 본 모듈은 dict/list 입력만 받는다(3-5 labelset_snapshot
패턴 — 순수 함수 격리로 단위 테스트 가능).
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable

from detection.src.pipeline.tier_router import TIER_PRIORITY, TYPE_TO_TIER

_T4 = "T4"  # 알 수 없는 type의 fallback Tier (tier_router.TierRouter.route와 동일).


def _tier_of(type_value: str | None) -> str:
    """type → Tier. 미등록/None은 T4 (정상)로 — tier_router SSOT와 일관."""
    return TYPE_TO_TIER.get(type_value or "", _T4)


def build_label_map(rows: Iterable[dict[str, Any]]) -> dict[Any, str]:
    """ground truth 행 → `{post_id: human_label}` 맵 (null/unknown 제외).

    human_label은 원본 detection 행(주로 single)에만 1개 존재한다. 재분류한 양 모드 결과를
    post_id로 이 맵에 조인해 ground truth와 비교한다. unknown은 9-type과 매칭 불가 →
    judgeable 분모에서 제외(3-5 규율과 일치).
    """
    out: dict[Any, str] = {}
    for row in rows:
        label = (row.get("human_label") or "").strip()
        if not label or label == "unknown":
            continue
        out[row["post_id"]] = label
    return out


def join_predictions(
    label_map: dict[Any, str], mode_rows: Iterable[dict[str, Any]]
) -> list[dict[str, Any]]:
    """한 모드의 재분류 결과를 ground truth와 post_id로 조인.

    Returns:
        [{post_id, human_label, type}, ...] — label_map에 있는 post만(judgeable). 재분류되지
        않았거나 라벨 없는 post는 제외.
    """
    joined: list[dict[str, Any]] = []
    for row in mode_rows:
        pid = row.get("post_id")
        if pid in label_map:
            joined.append(
                {"post_id": pid, "human_label": label_map[pid], "type": row.get("type")}
            )
    return joined


def agreement(
    label_map: dict[Any, str], mode_rows: Iterable[dict[str, Any]]
) -> dict[str, Any]:
    """라벨 == 예측 type 비율 (judgeable 분모). compute_snapshot의 일치율과 동일 의미.

    재분류되지 않은 post는 조인에서 빠지므로 분모에 포함되지 않는다.
    """
    joined = join_predictions(label_map, mode_rows)
    judgeable = len(joined)
    agree = sum(1 for j in joined if j["human_label"] == j["type"])
    return {
        "judgeable": judgeable,
        "agree": agree,
        "agreement": (agree / judgeable) if judgeable else 0.0,
    }


def tier_metrics(
    label_map: dict[Any, str], mode_rows: Iterable[dict[str, Any]]
) -> dict[str, Any]:
    """Tier별 Recall/Precision + confusion matrix (다중 클래스, 4 Tier).

    - TP(T) = truth T & pred T
    - FN(T) = truth T & pred ≠ T
    - FP(T) = truth ≠ T & pred T
    - Recall(T) = TP/(TP+FN), Precision(T) = TP/(TP+FP) — 분모 0이면 None(미정의, 0.0 아님).
    - confusion: `{(true_tier, pred_tier): count}`.

    재분류되지 않은(label_map엔 있으나 mode_rows엔 없는) post는 메트릭에서 제외 — 모드별 표본
    커버리지 차이를 FN으로 오염시키지 않기 위함.
    """
    pred = {r.get("post_id"): r.get("type") for r in mode_rows}
    per_tier: dict[str, dict[str, int]] = {t: {"tp": 0, "fn": 0, "fp": 0} for t in TIER_PRIORITY}
    confusion: Counter[tuple[str, str]] = Counter()

    for pid, label in label_map.items():
        if pid not in pred:
            continue  # 이 모드로 재분류 안 됨 → 제외
        true_tier = _tier_of(label)
        pred_tier = _tier_of(pred[pid])
        confusion[(true_tier, pred_tier)] += 1
        if true_tier == pred_tier:
            per_tier[true_tier]["tp"] += 1
        else:
            per_tier[true_tier]["fn"] += 1
            per_tier[pred_tier]["fp"] += 1

    result: dict[str, dict[str, Any]] = {}
    for tier, c in per_tier.items():
        tp, fn, fp = c["tp"], c["fn"], c["fp"]
        result[tier] = {
            "tp": tp, "fn": fn, "fp": fp,
            "recall": (tp / (tp + fn)) if (tp + fn) else None,
            "precision": (tp / (tp + fp)) if (tp + fp) else None,
        }
    return {"per_tier": result, "confusion": dict(confusion)}


def illegal_detection_rate(
    label_map: dict[Any, str], mode_rows: Iterable[dict[str, Any]]
) -> dict[str, Any]:
    """명확 케이스 정탐율 — truth가 불법(Tier≠T4)인 post 중 불법으로 예측한 비율 (PRD ≥90%).

    is_illegal 게이트(T4=정상)와 동일 정의. Tier가 정확히 일치하지 않아도 불법으로만 잡으면 정탐.
    """
    pred = {r.get("post_id"): r.get("type") for r in mode_rows}
    truth_illegal = 0
    detected_illegal = 0
    for pid, label in label_map.items():
        if pid not in pred:
            continue
        if _tier_of(label) == _T4:
            continue  # truth 정상 → 정탐율 분모 아님
        truth_illegal += 1
        if _tier_of(pred[pid]) != _T4:
            detected_illegal += 1
    return {
        "truth_illegal": truth_illegal,
        "detected_illegal": detected_illegal,
        "rate": (detected_illegal / truth_illegal) if truth_illegal else None,
    }


def percentile(values: list[float], p: float) -> float | None:
    """p 백분위 (0~100), 선형보간. stdlib만 — numpy 불요. 빈 리스트는 None.

    NIST 권장 R-7(numpy 기본)과 동일: rank = p/100 * (n-1), 양 끝 인덱스 선형보간.
    """
    if not values:
        return None
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    rank = (p / 100.0) * (len(s) - 1)
    lo = int(rank)
    hi = min(lo + 1, len(s) - 1)
    frac = rank - lo
    return s[lo] + (s[hi] - s[lo]) * frac


def _group_stats(costs: list[float]) -> dict[str, Any]:
    return {
        "count": len(costs),
        "mean": (sum(costs) / len(costs)) if costs else None,
        "p95": percentile(costs, 95),
        "max": max(costs) if costs else None,
    }


def cost_summary(cost_rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """게시글별 비용 → 전체/이미지유/이미지무 그룹 통계 (평균·p95·max·count).

    Args:
        cost_rows: 각 dict는 cost_usd(float) + has_image(bool).
    """
    rows = list(cost_rows)
    # cost_usd는 None/누락 시 0.0으로 — has_image와 동일하게 소프트 접근(순수함수 단독 호출 견고성).
    all_costs = [float(r.get("cost_usd") or 0.0) for r in rows]
    with_img = [float(r.get("cost_usd") or 0.0) for r in rows if r.get("has_image")]
    without_img = [float(r.get("cost_usd") or 0.0) for r in rows if not r.get("has_image")]
    return {
        "all": _group_stats(all_costs),
        "with_image": _group_stats(with_img),
        "without_image": _group_stats(without_img),
    }


# ── 렌더 ────────────────────────────────────────────────────────────────────


def _pct(value: float | None) -> str:
    return f"{value * 100:.1f}%" if value is not None else "N/A"


def _usd(value: float | None) -> str:
    return f"${value:.4f}" if value is not None else "N/A"


def render_ab_markdown(
    *,
    single: dict[str, Any],
    agentic: dict[str, Any],
    cost: dict[str, Any],
    escalation_rate: float | None,
    sample_size: int,
    fast_path_sweep: list[dict[str, Any]] | None = None,
) -> str:
    """A/B 비교표 본문 — agreement + Tier별 Recall/Precision Δ + confusion + 비용 (3-5 render 패턴)."""
    s_tier = single["tier"]["per_tier"]
    a_tier = agentic["tier"]["per_tier"]
    lines: list[str] = [
        "# A/B Comparison — single vs agentic (Story 3-9)",
        "",
        f"> ground truth: human_label IS NOT NULL AND != 'unknown' (judgeable). 표본 {sample_size}건.",
        "> single(`openai:...`) vs agentic(`agentic:v1:...`)을 동일 post로 재분류해 비교.",
        "",
        "## Agreement (라벨 == 예측, judgeable 분모)",
        "",
        "| 모드 | judgeable | agree | agreement |",
        "|---|---|---|---|",
        f"| single | {single['agreement']['judgeable']} | {single['agreement']['agree']} "
        f"| {_pct(single['agreement']['agreement'])} |",
        f"| agentic | {agentic['agreement']['judgeable']} | {agentic['agreement']['agree']} "
        f"| {_pct(agentic['agreement']['agreement'])} |",
        "",
        "## Tier별 Recall / Precision (PRD 목표: Recall T1≥0.85 / T2≥0.70 / T3≥0.55)",
        "",
        "| Tier | single Recall | agentic Recall | Δ Recall | single Prec | agentic Prec |",
        "|---|---|---|---|---|---|",
    ]
    for tier in TIER_PRIORITY:
        s_r = s_tier[tier]["recall"]
        a_r = a_tier[tier]["recall"]
        delta = (
            f"{(a_r - s_r) * 100:+.1f}%p"
            if (s_r is not None and a_r is not None)
            else "N/A"
        )
        lines.append(
            f"| {tier} | {_pct(s_r)} | {_pct(a_r)} | {delta} "
            f"| {_pct(s_tier[tier]['precision'])} | {_pct(a_tier[tier]['precision'])} |"
        )

    lines += [
        "",
        "## 명확 케이스 정탐율 (truth 불법 → 불법 예측, PRD ≥90%)",
        "",
        f"- single: {single['illegal']['detected_illegal']}/{single['illegal']['truth_illegal']} "
        f"= {_pct(single['illegal']['rate'])}",
        f"- agentic: {agentic['illegal']['detected_illegal']}/{agentic['illegal']['truth_illegal']} "
        f"= {_pct(agentic['illegal']['rate'])}",
        "",
        "## Confusion Matrix (agentic — 행=truth Tier, 열=pred Tier)",
        "",
        "| truth\\pred | " + " | ".join(TIER_PRIORITY) + " |",
        "|---|" + "---|" * len(TIER_PRIORITY),
    ]
    a_conf = agentic["tier"]["confusion"]
    for true_tier in TIER_PRIORITY:
        cells = [str(a_conf.get((true_tier, pred_tier), 0)) for pred_tier in TIER_PRIORITY]
        lines.append(f"| {true_tier} | " + " | ".join(cells) + " |")

    lines += [
        "",
        "## 비용 실측 (agentic, 게시글당 — PRD 평균 ≤$0.005 · p95 ≤$0.02)",
        "",
        "| 그룹 | 건수 | 평균 | p95 | 최대 |",
        "|---|---|---|---|---|",
        f"| 전체 | {cost['all']['count']} | {_usd(cost['all']['mean'])} "
        f"| {_usd(cost['all']['p95'])} | {_usd(cost['all']['max'])} |",
        f"| 이미지 有 | {cost['with_image']['count']} | {_usd(cost['with_image']['mean'])} "
        f"| {_usd(cost['with_image']['p95'])} | {_usd(cost['with_image']['max'])} |",
        f"| 이미지 無 | {cost['without_image']['count']} | {_usd(cost['without_image']['mean'])} "
        f"| {_usd(cost['without_image']['p95'])} | {_usd(cost['without_image']['max'])} |",
        "",
        f"- **escalation율**: {_pct(escalation_rate)}",
    ]

    if fast_path_sweep:
        lines += [
            "",
            "## fast-path 임계 스윕 (FAST_PATH_CONFIDENCE 튜닝)",
            "",
            "| 임계 | escalation율 | agreement | 비고 |",
            "|---|---|---|---|",
        ]
        for sweep in fast_path_sweep:
            lines.append(
                f"| {sweep.get('threshold')} | {_pct(sweep.get('escalation_rate'))} "
                f"| {_pct(sweep.get('agreement'))} | {sweep.get('note', '')} |"
            )
    lines.append("")
    return "\n".join(lines)
