"""few-shot 예시 코퍼스 빌드 (Story 3-5).

`human_label IS NOT NULL`인 detections를 **game_key × type(=human_label)별로 그룹화**하여,
그룹당 최대 N건(confidence 높은 순)을 골라 `detection/src/prompts/examples/{game_key}.jsonl`로
export한다. game_key 매핑은 `label_detections.SOURCE_ID_TO_GAME` 재사용.

**경계 (본 스토리에서 하지 않는 것):** 생성된 코퍼스를 `build_system_prompt()` Stage 2-B에 실제
주입하는 로직과 정확도 효과 측정은 별도 미래 스토리. 본 스크립트는 코퍼스 파일 생성까지만.
포맷 계약은 `detection/src/prompts/examples/README.md` 참조.

Usage:
    python -m detection.scripts.build_fewshot_corpus [--per-group 3]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from detection.scripts.label_detections import SOURCE_ID_TO_GAME  # noqa: E402

# 코퍼스 출력 디렉터리.
EXAMPLES_DIR = PROJECT_ROOT / "detection" / "src" / "prompts" / "examples"
# 본문 발췌 최대 길이 — 프롬프트 토큰 예산 가드 (game·type 상한과 함께 폭증 방지).
EXCERPT_MAX_CHARS = int(os.environ.get("FEWSHOT_EXCERPT_MAX_CHARS", "500"))
DEFAULT_PER_GROUP = int(os.environ.get("FEWSHOT_PER_GROUP", "3"))


def _excerpt(body: str | None) -> str:
    """본문을 EXCERPT_MAX_CHARS로 자른 발췌. None/공백은 빈 문자열."""
    text = (body or "").strip()
    if len(text) <= EXCERPT_MAX_CHARS:
        return text
    return text[:EXCERPT_MAX_CHARS].rstrip() + "…"


def build_corpus(
    rows: Iterable[dict[str, Any]], per_group: int = DEFAULT_PER_GROUP
) -> dict[str, list[dict[str, Any]]]:
    """라벨된 행 → game_key별 예시 리스트 (pure — DB 무관, 단위 테스트 대상).

    Args:
        rows: 각 dict는 source_id / human_label / body / reason_ko / tier / confidence 키.
        per_group: game_key × type 그룹당 최대 예시 수 (confidence 내림차순 상위).

    Returns:
        {game_key: [{"text", "label", "reason_ko", "tier"}, ...]} — 동작 중립:
        라벨 0건 / 미매핑 source_id / human_label="unknown"은 제외되어 빈 dict 가능.

    Raises:
        ValueError: per_group < 1. 0은 코퍼스를 통째로 비우고(라벨이 있어도 "0건" 오해),
            음수는 items[:per_group] 음수 슬라이싱으로 그룹을 조용히 누락시키므로 차단.
    """
    if per_group < 1:
        raise ValueError(f"per_group must be >= 1, got {per_group}")

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        label = (row.get("human_label") or "").strip()
        if not label or label == "unknown":
            continue  # unknown은 코퍼스 제외 (스냅샷 분모에는 포함 — labelset_snapshot)
        game_key = SOURCE_ID_TO_GAME.get(row.get("source_id"))
        if not game_key:
            continue  # 미매핑 source_id → 베이스 fallback (코퍼스 제외)
        grouped[(game_key, label)].append(row)

    corpus: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for (game_key, label), items in grouped.items():
        # confidence 내림차순; 동점은 id 오름차순으로 결정적 선택 (재빌드 재현성 — #8).
        items.sort(key=lambda r: (-float(r.get("confidence") or 0.0), r.get("id") or 0))
        for row in items[:per_group]:
            corpus[game_key].append(
                {
                    "text": _excerpt(row.get("body")),
                    "label": label,
                    "reason_ko": (row.get("reason_ko") or "").strip(),
                    "tier": row.get("tier") or "",
                }
            )
    return dict(corpus)


def write_corpus(
    corpus: dict[str, list[dict[str, Any]]], out_dir: Path = EXAMPLES_DIR
) -> dict[str, int]:
    """game_key별 examples/{game_key}.jsonl 작성. 그룹당 레코드 수 dict 반환.

    재빌드 멱등성: 쓰기 전에 out_dir의 기존 ``*.jsonl``을 모두 제거한다(README.md 등
    비-jsonl 파일은 보존). 라벨이 빠진 game_key(전부 unknown 재라벨/리매핑 등)의 옛 코퍼스가
    살아남아 "파일 없음 = 베이스 프롬프트만"이라는 동작 중립 fallback 계약을 깨는 것을 방지.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("*.jsonl"):
        stale.unlink()
    written: dict[str, int] = {}
    for game_key, records in corpus.items():
        if not records:
            continue
        path = out_dir / f"{game_key}.jsonl"
        with path.open("w", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        written[game_key] = len(records)
    return written


def fetch_labeled_rows(pool) -> list[dict[str, Any]]:
    """human_label이 부여된 detections를 본문·source_id와 함께 조회 (DB 경로)."""
    sql = """
        SELECT d.id,
               s.site_name AS source_id,
               d.human_label,
               p.body,
               d.reason     AS reason_ko,
               d.tier,
               d.confidence
          FROM detections d
          JOIN posts p   ON p.id = d.post_id
          JOIN sources s ON s.id = p.source_id
         WHERE d.human_label IS NOT NULL
         ORDER BY d.confidence DESC, d.id
    """
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            cols = [c.name for c in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]


def _positive_int(value: str) -> int:
    """argparse용: 1 이상의 정수만 허용 (per-group 0/음수가 코퍼스를 비우거나 깎는 것 방지)."""
    ivalue = int(value)
    if ivalue < 1:
        raise argparse.ArgumentTypeError(f"1 이상의 정수여야 합니다: {value!r}")
    return ivalue


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="few-shot 예시 코퍼스 빌드 (Story 3-5)")
    parser.add_argument(
        "--per-group", type=_positive_int, default=DEFAULT_PER_GROUP,
        help=f"game_key × type 그룹당 최대 예시 수 (기본 {DEFAULT_PER_GROUP}, 1 이상)",
    )
    args = parser.parse_args(argv)

    from dotenv import load_dotenv

    env_path = PROJECT_ROOT / "infra" / ".env"
    if env_path.exists():
        load_dotenv(env_path)

    from detection.src.config.db_config import close_pool, get_pool

    try:
        pool = get_pool()
        rows = fetch_labeled_rows(pool)
    finally:
        close_pool()

    corpus = build_corpus(rows, per_group=args.per_group)
    written = write_corpus(corpus)

    total_examples = sum(written.values())
    if not written:
        print(
            "[INFO] 라벨된 detections 0건 또는 미매핑 — 코퍼스 미생성 (동작 중립 fallback). "
            "`label_detections.py`로 라벨을 먼저 수집하세요."
        )
        return 0

    print(f"[DONE] few-shot 코퍼스 생성 — {len(written)} game_key / {total_examples} 예시")
    for game_key, n in sorted(written.items()):
        print(f"  - {game_key}.jsonl : {n} 예시")
    print(f"  출력 위치: {EXAMPLES_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
