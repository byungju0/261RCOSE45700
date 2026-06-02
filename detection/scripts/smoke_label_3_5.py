"""Story 3-5 실사 smoke — 사람 라벨 쓰기 → 코퍼스 빌드 → 경량 스냅샷이 실 PostgreSQL에서 흐른다.

set_human_label / build_fewshot_corpus / labelset_snapshot의 DB 경로를 한 번에 검증한다.
의존 스키마는 **V9(human_label 컬럼)만** — 시드 행을 직접 INSERT하여 V7 notification_events
드리프트와 무관하게 격리. OpenAI/네트워크 호출 0.

전제:
    docker compose -f infra/docker-compose.yml --env-file infra/.env up -d postgres
    # 그리고 V9 적용:
    docker exec -i tracker-postgres psql -U tracker_user -d tracker \
        < api/src/main/resources/db/migration/V9__add_human_label.sql

Usage:
    python detection/scripts/smoke_label_3_5.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv
except ImportError as exc:  # pragma: no cover
    sys.exit(f"[FAIL] python-dotenv 미설치: {exc}")

ENV_PATH = PROJECT_ROOT / "infra" / ".env"
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)

import os

if not os.environ.get("DB_PASSWORD"):
    sys.exit("[FAIL] DB_PASSWORD 미설정. infra/.env 갱신 필요.")

from detection.src.config.db_config import close_pool, get_pool  # noqa: E402
from detection.src.repository.detection_repository import DetectionRepository  # noqa: E402
from detection.scripts.build_fewshot_corpus import (  # noqa: E402
    build_corpus,
    fetch_labeled_rows,
    write_corpus,
)
from detection.scripts.labelset_snapshot import (  # noqa: E402
    compute_snapshot,
    fetch_rows,
)

_MV = "smoke:gpt-4o:3-5"
_SITE = "ptt"  # registry.SOURCE_ID_TO_GAME → lineage


def _seed(pool, post_uid: str) -> int:
    """sources/posts/detections 1건 직접 INSERT. detections.post_id(FK) 반환."""
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                # 기존 ptt(=lineage 실데이터) source의 board_name을 덮어쓰지 않는다 (#6 — save()와 동일).
                "INSERT INTO sources (site_name, board_name) VALUES (%s, %s) "
                "ON CONFLICT (site_name) DO UPDATE "
                "    SET board_name = COALESCE(sources.board_name, EXCLUDED.board_name) "
                "RETURNING id",
                (_SITE, "smoke board"),
            )
            source_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO posts (source_id, post_id_at_source, body, language, crawled_at) "
                "VALUES (%s, %s, %s, %s, NOW()) "
                "ON CONFLICT (source_id, post_id_at_source) DO UPDATE SET body=EXCLUDED.body "
                "RETURNING id",
                (source_id, post_uid, "리니지M 월핵 최신 버전 팝니다. 텔레그램 @smoke", "ko"),
            )
            post_fk = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO detections "
                "(post_id, is_illegal, type, tier, confidence, reason, model_version) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (post_id, model_version) DO UPDATE SET type=EXCLUDED.type",
                (post_fk, True, "핵_치트", "T1", 0.93, "명시적 핵 판매 + 연락처", _MV),
            )
    return post_fk


def _cleanup(pool, post_fk: int) -> None:
    """시드한 detection·post를 제거하고, 우리가 만든 source(다른 post가 없을 때만)도 정리 (#6).

    실제 ptt source가 이미 다른 post를 가지면 source는 보존한다(FK·실데이터 보호) —
    시드가 새로 만든 빈 source만 삭제된다.
    """
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT source_id FROM posts WHERE id=%s", (post_fk,))
            row = cur.fetchone()
            source_id = row[0] if row else None
            cur.execute("DELETE FROM detections WHERE post_id=%s", (post_fk,))
            cur.execute("DELETE FROM posts WHERE id=%s", (post_fk,))
            if source_id is not None:
                cur.execute(
                    "DELETE FROM sources WHERE id=%s "
                    "AND NOT EXISTS (SELECT 1 FROM posts WHERE source_id=%s)",
                    (source_id, source_id),
                )


def _run() -> int:
    print(f"[INFO] DB={os.environ.get('DB_HOST')}:{os.environ.get('DB_PORT', '5432')}/{os.environ.get('DB_NAME')}")
    pool = get_pool()
    post_uid = "smoke_3_5_label"
    post_fk = _seed(pool, post_uid)
    print(f"[INFO] 시드 완료: detections.post_id(FK)={post_fk} model_version={_MV}")

    repo = DetectionRepository(pool)

    # 1) set_human_label — 사람 정답 기록
    updated = repo.set_human_label(post_fk, _MV, "핵_치트", source="manual_cli")
    assert updated == 1, f"set_human_label updated={updated} (1 기대)"
    # 멱등 정정
    repo.set_human_label(post_fk, _MV, "사설서버")
    repo.set_human_label(post_fk, _MV, "핵_치트")  # 최종 핵_치트로 복원
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT human_label, human_verified_at, label_source FROM detections "
                "WHERE post_id=%s AND model_version=%s",
                (post_fk, _MV),
            )
            label, verified_at, src = cur.fetchone()
    print(f"[OK ] set_human_label → label={label} verified_at={verified_at is not None} source={src}")
    assert label == "핵_치트" and verified_at is not None and src == "manual_cli"

    # 2) build_fewshot_corpus — 실 DB 라벨에서 코퍼스 빌드 (임시 디렉터리로, 산출물 오염 방지)
    rows = fetch_labeled_rows(pool)
    corpus = build_corpus(rows, per_group=3)
    with tempfile.TemporaryDirectory() as tmp:
        written = write_corpus(corpus, out_dir=Path(tmp))
    print(f"[OK ] build_fewshot_corpus → game_keys={sorted(written)} (lineage 포함 기대)")
    assert "lineage" in corpus, "시드한 ptt→lineage 예시가 코퍼스에 있어야 함"

    # 3) labelset_snapshot — 집계
    snap = compute_snapshot(fetch_rows(pool))
    print(f"[OK ] labelset_snapshot → total={snap['total']} agreement={snap['agreement']*100:.1f}% "
          f"by_game={snap['by_game']}")
    assert snap["total"] >= 1 and snap["by_game"].get("lineage", 0) >= 1

    _cleanup(pool, post_fk)
    print("\n[DONE] Story 3-5 smoke 통과 — set_human_label → 코퍼스 → 스냅샷이 실 PostgreSQL에서 흘렀습니다.")
    return 0


def main() -> int:
    try:
        return _run()
    finally:
        close_pool()


if __name__ == "__main__":
    sys.exit(main())
