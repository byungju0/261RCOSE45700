"""경량 정확도 스냅샷 (Story 3-5).

human_label(사람 정답)과 LLM 예측(detections.type)을 비교해 **가벼운 현황 보고**를 산출한다:
  - 라벨 총건수 + overall 일치율(agreement = human_label == type 비율)
  - game_key별 / type별 커버리지 카운트 (few-shot 코퍼스 충분성 점검용)

**경계:** ≥300 게이트 / Tier별 confusion matrix / 게시글당 비용·p95 측정은 **포함하지 않는다**
(원 Story 3.5 정식 측정 → deferred-work 이월). 본 스냅샷은 "지금까지 얼마나·얼마나 잘 모았나".

Usage:
    python -m detection.scripts.labelset_snapshot
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from detection.src.prompts.registry import SOURCE_ID_TO_GAME  # noqa: E402

SNAPSHOT_PATH = PROJECT_ROOT / "docs" / "labelset-snapshot.md"
_UNMAPPED = "(unmapped)"


def compute_snapshot(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """라벨된 행 → 스냅샷 집계 (pure — DB 무관, 단위 테스트 대상).

    Args:
        rows: 각 dict는 source_id / human_label / type 키. human_label 없는 행은 무시.

    Returns:
        {total, judgeable, agree, agreement, by_game, by_game_usable, by_type}.
        - total: 라벨된 전체 행(unknown 포함) — 커버리지 분모.
        - judgeable: unknown을 제외한 판단 가능 행 — **일치율 분모**.
        - by_game: game_key별 전체 라벨 수(unknown 포함).
        - by_game_usable: game_key별 unknown 제외 라벨 수 — **few-shot 코퍼스 충분성 기준**
          (코퍼스는 unknown을 제외하므로 by_game만 보면 충분성을 과대평가 — #9).
        - agreement: agree / judgeable. unknown은 9-type(type)과 절대 일치할 수 없어
          분모(total)에 넣으면 일치율을 왜곡하므로 제외. 커버리지(by_game/by_type/total)에는 포함.
    """
    total = 0
    judgeable = 0
    agree = 0
    by_game: Counter[str] = Counter()
    by_game_usable: Counter[str] = Counter()  # unknown 제외 — few-shot 코퍼스 충분성 기준 (#9)
    by_type: Counter[str] = Counter()
    for row in rows:
        label = (row.get("human_label") or "").strip()
        if not label:
            continue
        total += 1
        game_key = SOURCE_ID_TO_GAME.get(row.get("source_id"), _UNMAPPED)
        by_game[game_key] += 1
        by_type[label] += 1
        if label != "unknown":  # unknown은 일치율 분모·코퍼스에서 제외 (type 9-enum과 매칭 불가)
            judgeable += 1
            by_game_usable[game_key] += 1
            if label == row.get("type"):
                agree += 1
    agreement = (agree / judgeable) if judgeable else 0.0
    return {
        "total": total,
        "judgeable": judgeable,
        "agree": agree,
        "agreement": agreement,
        "by_game": dict(by_game),
        "by_game_usable": dict(by_game_usable),
        "by_type": dict(by_type),
    }


def render_markdown(snapshot: dict[str, Any]) -> str:
    """스냅샷 → docs/labelset-snapshot.md 본문."""
    total = snapshot["total"]
    judgeable = snapshot.get("judgeable", total)
    unknown = total - judgeable
    agreement_pct = f"{snapshot['agreement'] * 100:.1f}%" if judgeable else "N/A"
    judgeable_line = f"- 판단 가능 건수 (unknown 제외): **{judgeable}**"
    if unknown:
        judgeable_line += f"  ·  unknown {unknown}건 (일치율 분모 제외)"
    lines: list[str] = [
        "# Labelset Snapshot (Story 3-5 — 경량 정확도 스냅샷)",
        "",
        "> few-shot 학습용 라벨 수집 현황의 **가벼운 현황 보고**. "
        "≥300 게이트 / Tier confusion matrix / 비용·p95 정식 측정은 deferred-work 이월 "
        "(별도 측정 스토리에서 승격).",
        "",
        "## Overall",
        "",
        f"- 라벨 총건수: **{total}**",
        judgeable_line,
        f"- LLM 예측 일치율 (human_label == type, unknown 제외): **{agreement_pct}** "
        f"({snapshot['agree']}/{judgeable})",
        "",
        "## game_key별 커버리지",
        "",
        "> '사용 가능' = unknown 제외 (few-shot 코퍼스에 실제 쓰이는 예시 수 — 충분성은 이 열 기준).",
        "",
        "| game_key | 라벨 수 | 사용 가능(unknown 제외) |",
        "|---|---|---|",
    ]
    by_game = snapshot["by_game"]
    by_game_usable = snapshot.get("by_game_usable", {})
    if by_game:
        for game_key, count in sorted(by_game.items(), key=lambda kv: (-kv[1], kv[0])):
            lines.append(f"| {game_key} | {count} | {by_game_usable.get(game_key, 0)} |")
    else:
        lines.append("| _(라벨 없음)_ | 0 | 0 |")
    lines += [
        "",
        "## type별 커버리지 (human_label 기준)",
        "",
        "| type | 라벨 수 |",
        "|---|---|",
    ]
    by_type = snapshot["by_type"]
    if by_type:
        for type_key, count in sorted(by_type.items(), key=lambda kv: (-kv[1], kv[0])):
            lines.append(f"| {type_key} | {count} |")
    else:
        lines.append("| _(라벨 없음)_ | 0 |")
    lines.append("")
    return "\n".join(lines)


def fetch_rows(pool) -> list[dict[str, Any]]:
    """human_label이 부여된 detections를 source_id / human_label / type와 함께 조회."""
    sql = """
        SELECT s.site_name AS source_id,
               d.human_label,
               d.type
          FROM detections d
          JOIN posts p   ON p.id = d.post_id
          JOIN sources s ON s.id = p.source_id
         WHERE d.human_label IS NOT NULL
    """
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            cols = [c.name for c in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]


def main(argv: list[str] | None = None) -> int:
    import argparse

    argparse.ArgumentParser(
        description="경량 정확도 스냅샷 — 라벨 수집 현황 (Story 3-5)"
    ).parse_args(argv)

    from dotenv import load_dotenv

    env_path = PROJECT_ROOT / "infra" / ".env"
    if env_path.exists():
        load_dotenv(env_path)

    from detection.src.config.db_config import close_pool, get_pool

    try:
        pool = get_pool()
        rows = fetch_rows(pool)
    finally:
        close_pool()

    snapshot = compute_snapshot(rows)
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_PATH.write_text(render_markdown(snapshot), encoding="utf-8")

    print(
        f"[DONE] 스냅샷 작성 — 총 {snapshot['total']}건 "
        f"(판단가능 {snapshot['judgeable']}건) / "
        f"일치율 {snapshot['agreement'] * 100:.1f}% → {SNAPSHOT_PATH}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
