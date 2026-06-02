"""미라벨 detections 라벨링 CLI (Story 3-5).

`human_label IS NULL`인 detections를 한 건씩 보여주고 — 본문 발췌 + **LLM 예측(type/tier/
reason_ko)을 기본값으로 제시** — dev가 1-key로 확정·정정한다. 확정 시
`DetectionRepository.set_human_label`로 RDS에 기록한다.

입력:
  Enter   = LLM 예측(type)에 동의 (1-key 확정)
  <type>  = 9-type 중 하나 입력 (정정)
  u       = unknown (판단 불가)
  s       = skip (라벨 안 하고 다음)
  q       = 종료

대화형이라 pytest 범위 밖. 핵심 로직(필터 쿼리 / 라벨 적용)은 `DetectionRepository` +
아래 순수 헬퍼로 분리되어 테스트 가능.

Usage:
    python -m detection.scripts.label_detections [--game lineage] [--tier T1] [--limit 20]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from detection.src.prompts.registry import SOURCE_ID_TO_GAME  # noqa: E402
from shared.interfaces.llm import ALLOWED_DETECTION_TYPES  # noqa: E402

_VALID_TIERS = ("T1", "T2", "T3", "T4")
_EXCERPT_CHARS = 600


def source_ids_for_game(game_key: str) -> list[str]:
    """game_key → 매핑된 source_id 목록 (registry.SOURCE_ID_TO_GAME 역매핑 재사용)."""
    return [sid for sid, gk in SOURCE_ID_TO_GAME.items() if gk == game_key]


def fetch_unlabeled(
    pool,
    game: str | None = None,
    tier: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """미라벨 detections 조회 (human_label IS NULL + 옵션 필터, detected_at DESC).

    반환 행: post_id(FK) / model_version / source_id / body / type / tier / reason / confidence.
    game 필터는 source_id 역매핑으로 sources.site_name IN (...) 적용.
    """
    where = ["d.human_label IS NULL"]
    params: list[Any] = []
    if game:
        source_ids = source_ids_for_game(game)
        if not source_ids:
            return []  # 매핑 없는 game_key → 결과 없음
        where.append("s.site_name = ANY(%s)")
        params.append(source_ids)
    if tier:
        where.append("d.tier = %s")
        params.append(tier)
    params.append(limit)

    sql = f"""
        SELECT d.post_id, d.model_version, s.site_name AS source_id,
               p.body, d.type, d.tier, d.reason, d.confidence
          FROM detections d
          JOIN posts p   ON p.id = d.post_id
          JOIN sources s ON s.id = p.source_id
         WHERE {' AND '.join(where)}
         ORDER BY d.detected_at DESC
         LIMIT %s
    """
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            cols = [c.name for c in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]


def _excerpt(body: str | None) -> str:
    text = (body or "").strip()
    return text if len(text) <= _EXCERPT_CHARS else text[:_EXCERPT_CHARS].rstrip() + "…"


def _resolve_input(raw: str, predicted_type: str) -> str | None:
    """사용자 입력 → 확정 라벨. None = skip/미해결 (호출자가 분기)."""
    cmd = raw.strip()
    if cmd == "":
        return predicted_type  # Enter = LLM 예측 동의
    if cmd == "u":
        return "unknown"
    if cmd in ALLOWED_DETECTION_TYPES:
        return cmd
    return None  # 알 수 없는 입력 → 호출자가 재입력 요구


def _prompt_loop(rows: list[dict[str, Any]], repo) -> int:
    """대화형 라벨링 루프. 확정 건수 반환."""
    total = len(rows)
    labeled = 0
    type_menu = " / ".join(sorted(ALLOWED_DETECTION_TYPES))
    for idx, row in enumerate(rows, start=1):
        predicted = row.get("type") or "기타"
        print("\n" + "=" * 72)
        print(f"[{idx}/{total}]  source_id={row['source_id']}  tier={row['tier']}")
        print(f"LLM 예측: type={predicted}  confidence={float(row['confidence']):.2f}")
        print(f"근거(reason_ko): {row.get('reason') or '(없음)'}")
        print("-" * 72)
        print(_excerpt(row.get("body")))
        print("-" * 72)
        print(f"유형: {type_menu}")
        print("[Enter]=LLM동의  <type>=정정  u=unknown  s=skip  q=종료")

        while True:
            raw = input("라벨> ")
            cmd = raw.strip()
            if cmd == "q":
                print(f"\n[종료] {labeled}/{total} labeled")
                return labeled
            if cmd == "s":
                print("  → skip")
                break
            label = _resolve_input(raw, predicted)
            if label is None:
                print("  ! 알 수 없는 입력. 9-type 중 하나 / Enter / u / s / q 로 재입력.")
                continue
            try:
                updated = repo.set_human_label(row["post_id"], row["model_version"], label)
            except ValueError as exc:
                # Enter로 동의한 LLM 예측(type)이 enum 밖(레거시/수동 입력 데이터)일 때 등 —
                # 세션 전체를 죽이지 않고 이 행만 재입력하도록 되돌린다.
                print(f"  ! 라벨 거부됨: {exc}\n    9-type 중 하나를 직접 입력하거나 s=skip / q=종료.")
                continue
            if updated:
                labeled += 1
                print(f"  ✓ {label} 기록 ({labeled}/{total} labeled)")
            else:
                print("  ! 매칭 행 0건 — 이미 변경됐을 수 있음. 다음으로.")
            break

    print(f"\n[완료] {labeled}/{total} labeled")
    return labeled


def _positive_int(value: str) -> int:
    """argparse용: 1 이상의 정수만 허용 (음수 LIMIT 크래시 / limit=0 무음 조회 방지)."""
    ivalue = int(value)
    if ivalue < 1:
        raise argparse.ArgumentTypeError(f"1 이상의 정수여야 합니다: {value!r}")
    return ivalue


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="미라벨 detections 라벨링 CLI (Story 3-5)")
    parser.add_argument("--game", help="game_key 필터 (예: lineage). registry 매핑 기준")
    parser.add_argument("--tier", choices=_VALID_TIERS, help="Tier 필터 (T1~T4)")
    parser.add_argument("--limit", type=_positive_int, default=20, help="조회 건수 (기본 20, 1 이상)")
    args = parser.parse_args(argv)

    from dotenv import load_dotenv

    env_path = PROJECT_ROOT / "infra" / ".env"
    if env_path.exists():
        load_dotenv(env_path)

    from detection.src.config.db_config import close_pool, get_pool
    from detection.src.repository.detection_repository import DetectionRepository

    try:
        pool = get_pool()
        rows = fetch_unlabeled(pool, game=args.game, tier=args.tier, limit=args.limit)
        if not rows:
            print("[INFO] 미라벨 detections 0건 (필터 조건 내). 라벨링할 대상이 없습니다.")
            return 0
        repo = DetectionRepository(pool)
        _prompt_loop(rows, repo)
    finally:
        close_pool()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
