"""DetectionRepository 통합 테스트 — 실 PostgreSQL 사용 (Story 3-4).

PostgreSQL이 떠있지 않으면 자동 skip (`requires_pg`).
"""

from __future__ import annotations

import pytest

from detection.src.agents.contracts import AgentRunTrace
from detection.src.repository.detection_repository import DetectionRepository
from detection.tests.conftest import requires_pg
from shared.interfaces.llm import LLMResponse
from shared.models.crawl_event import CrawlEvent


def _build_event(post_id: str = "test_001", language: str = "ko") -> CrawlEvent:
    return CrawlEvent(
        post_id=post_id,
        source_id="ptt_lineage",
        site_name="PTT Lineage",
        raw_text="리니지M 핵 팝니다",
        language=language,
        detected_at="2026-05-27T00:00:00Z",
        correlation_id=f"cid-{post_id}",
    )


def _build_response(type_: str = "핵_치트", confidence: float = 0.95) -> LLMResponse:
    return LLMResponse(
        type=type_,
        confidence=confidence,
        reason_ko="이미지에 핵 광고 텍스트 확인됨",
        translated_text_ko=None,
        image_observed=False,
        input_tokens=537,
        output_tokens=63,
        cost_usd=0.00197,
    )


@requires_pg
def test_save_creates_sources_posts_detections(clean_db) -> None:
    repo = DetectionRepository(clean_db)
    event = _build_event()
    response = _build_response()

    detection_id = repo.save(event, response, tier="T1", model_version="openai:gpt-4o:2024-08-06")

    assert detection_id is not None and detection_id > 0

    # DB 직접 확인 — 3개 테이블에 row 들어갔는지.
    with clean_db.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT site_name, board_name FROM sources WHERE site_name=%s", (event.source_id,))
            source = cur.fetchone()
            assert source == ("ptt_lineage", "PTT Lineage")

            cur.execute("SELECT body, language FROM posts WHERE post_id_at_source=%s", (event.post_id,))
            post = cur.fetchone()
            assert post == ("리니지M 핵 팝니다", "ko")

            cur.execute(
                "SELECT type, tier, confidence, is_illegal, translated_text, image_observed, cost_usd, model_version "
                "FROM detections WHERE id=%s",
                (detection_id,),
            )
            det = cur.fetchone()
            assert det[0] == "핵_치트"
            assert det[1] == "T1"
            assert float(det[2]) == 0.95
            assert det[3] is True  # is_illegal (T1)
            assert det[4] is None  # translated_text_ko None
            assert det[5] is False  # image_observed
            assert float(det[6]) == pytest.approx(0.00197, rel=1e-3)
            assert det[7] == "openai:gpt-4o:2024-08-06"

            cur.execute(
                "SELECT event_type, status, correlation_id FROM notification_events WHERE detection_id=%s",
                (detection_id,),
            )
            event_row = cur.fetchone()
            assert event_row == ("DETECTION_CREATED", "PENDING", event.correlation_id)


@requires_pg
def test_save_t4_marks_is_illegal_false(clean_db) -> None:
    repo = DetectionRepository(clean_db)
    event = _build_event(post_id="clean_001")
    response = _build_response(type_="기타", confidence=0.85)

    detection_id = repo.save(event, response, tier="T4", model_version="openai:gpt-4o:2024-08-06")

    with clean_db.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT is_illegal, tier FROM detections WHERE id=%s", (detection_id,))
            is_illegal, tier = cur.fetchone()
            assert is_illegal is False
            assert tier == "T4"


@requires_pg
def test_save_is_idempotent_on_same_model_version(clean_db) -> None:
    """동일 post_id + 동일 model_version으로 2회 save → 두 번째는 None 반환."""
    repo = DetectionRepository(clean_db)
    event = _build_event(post_id="dup_001")
    response = _build_response()

    first_id = repo.save(event, response, tier="T1", model_version="openai:gpt-4o:2024-08-06")
    second_id = repo.save(event, response, tier="T1", model_version="openai:gpt-4o:2024-08-06")

    assert first_id is not None
    assert second_id is None  # ON CONFLICT DO NOTHING → RETURNING 없음

    # detections에는 1 row만.
    with clean_db.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM detections "
                "WHERE post_id IN (SELECT id FROM posts WHERE post_id_at_source=%s)",
                (event.post_id,),
            )
            assert cur.fetchone()[0] == 1

            cur.execute("SELECT COUNT(*) FROM notification_events")
            assert cur.fetchone()[0] == 1


@requires_pg
def test_save_different_model_version_allowed(clean_db) -> None:
    """동일 post_id + 다른 model_version → 두 번째도 INSERT 성공."""
    repo = DetectionRepository(clean_db)
    event = _build_event(post_id="multimodel_001")
    response = _build_response()

    id1 = repo.save(event, response, tier="T1", model_version="openai:gpt-4o:2024-08-06")
    id2 = repo.save(event, response, tier="T1", model_version="openai:gpt-4o-mini:2024-07-18")

    assert id1 is not None and id2 is not None
    assert id1 != id2

    with clean_db.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM detections")
            assert cur.fetchone()[0] == 2
            cur.execute("SELECT COUNT(*) FROM posts")
            assert cur.fetchone()[0] == 1  # posts는 1 row만 (UPSERT)


@requires_pg
def test_save_translated_text_persisted(clean_db) -> None:
    repo = DetectionRepository(clean_db)
    event = _build_event(post_id="zh_001", language="zh-CN")
    response = _build_response()
    response.translated_text_ko = "월핵 최신 버전 업로드. 탐지 안 됨. 무료"

    detection_id = repo.save(event, response, tier="T1", model_version="openai:gpt-4o:2024-08-06")

    with clean_db.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT translated_text FROM detections WHERE id=%s", (detection_id,))
            assert cur.fetchone()[0] == "월핵 최신 버전 업로드. 탐지 안 됨. 무료"


# ---------------------------------------------------------------------------
# Story 3-7: agent_runs 동일 트랜잭션 저장 (V10)
# ---------------------------------------------------------------------------

_AGENTIC_MV = "agentic:v1:gpt-4o-mini:2026-06"


def _traces() -> list[AgentRunTrace]:
    return [
        AgentRunTrace(stage="normalize", model=None, latency_ms=1, output={"links": ["https://x"]}),
        AgentRunTrace(
            stage="triage", model="gpt-4o-mini", input_tokens=100, output_tokens=30,
            cost_usd=0.00042, latency_ms=120, output={"type": "핵_치트"},
        ),
        AgentRunTrace(
            stage="link_trace", model=None, latency_ms=80,
            output={"links": [{"url": "https://x", "kind": "web"}]},
        ),
    ]


@requires_pg
def test_save_with_agent_runs_persists_traces(clean_db) -> None:
    repo = DetectionRepository(clean_db)
    event = _build_event(post_id="agentic_001")

    detection_id = repo.save(
        event, _build_response(), tier="T1", model_version=_AGENTIC_MV, agent_runs=_traces()
    )
    assert detection_id is not None

    with clean_db.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT stage, model, cost_usd FROM agent_runs WHERE detection_id=%s ORDER BY id",
                (detection_id,),
            )
            rows = cur.fetchall()
            assert [r[0] for r in rows] == ["normalize", "triage", "link_trace"]
            triage = next(r for r in rows if r[0] == "triage")
            assert triage[1] == "gpt-4o-mini"
            assert float(triage[2]) == pytest.approx(0.00042, rel=1e-3)
            # output JSONB 저장 확인.
            cur.execute(
                "SELECT output->'links'->>0 FROM agent_runs WHERE detection_id=%s AND stage='normalize'",
                (detection_id,),
            )
            assert cur.fetchone()[0] == "https://x"


@requires_pg
def test_agent_runs_skipped_on_idempotent_conflict(clean_db) -> None:
    """detections 멱등 conflict(2회차)면 agent_runs도 INSERT 안 됨."""
    repo = DetectionRepository(clean_db)
    event = _build_event(post_id="agentic_dup")

    first = repo.save(event, _build_response(), tier="T1", model_version=_AGENTIC_MV, agent_runs=_traces())
    second = repo.save(event, _build_response(), tier="T1", model_version=_AGENTIC_MV, agent_runs=_traces())

    assert first is not None
    assert second is None  # conflict skip

    with clean_db.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM agent_runs")
            assert cur.fetchone()[0] == 3  # 첫 저장의 3건만, 두 번째는 skip


@requires_pg
def test_single_mode_save_writes_no_agent_runs(clean_db) -> None:
    """agent_runs=None(single 모드)이면 agent_runs 테이블에 아무것도 안 들어감."""
    repo = DetectionRepository(clean_db)
    event = _build_event(post_id="single_001")
    detection_id = repo.save(event, _build_response(), tier="T1", model_version=_MV)
    assert detection_id is not None
    with clean_db.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM agent_runs")
            assert cur.fetchone()[0] == 0


# ---------------------------------------------------------------------------
# Story 3-5: set_human_label
# ---------------------------------------------------------------------------

_MV = "openai:gpt-4o:2024-08-06"


def _save_one(repo: DetectionRepository, post_id: str = "label_001") -> int:
    """detection 1건 저장 후 detections.post_id (FK) 반환 — set_human_label 입력값."""
    event = _build_event(post_id=post_id)
    detection_id = repo.save(
        event, _build_response(), tier="T1", model_version=_MV
    )
    assert detection_id is not None
    with repo._pool.connection() as conn:  # noqa: SLF001 — 테스트에서 FK 조회
        with conn.cursor() as cur:
            cur.execute("SELECT post_id FROM detections WHERE id=%s", (detection_id,))
            return cur.fetchone()[0]


@requires_pg
def test_set_human_label_updates_row(clean_db) -> None:
    repo = DetectionRepository(clean_db)
    fk_post_id = _save_one(repo)

    updated = repo.set_human_label(fk_post_id, _MV, "핵_치트", source="manual_cli")
    assert updated == 1

    with clean_db.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT human_label, human_verified_at, label_source "
                "FROM detections WHERE post_id=%s AND model_version=%s",
                (fk_post_id, _MV),
            )
            label, verified_at, src = cur.fetchone()
            assert label == "핵_치트"
            assert verified_at is not None  # NOW()로 채워짐
            assert src == "manual_cli"


@requires_pg
def test_set_human_label_idempotent(clean_db) -> None:
    """재라벨 시 값만 덮어쓰고 행 수는 증가하지 않는다."""
    repo = DetectionRepository(clean_db)
    fk_post_id = _save_one(repo, post_id="label_idem")

    repo.set_human_label(fk_post_id, _MV, "핵_치트")
    second = repo.set_human_label(fk_post_id, _MV, "사설서버")  # 정정
    assert second == 1

    with clean_db.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM detections WHERE post_id=%s AND model_version=%s",
                (fk_post_id, _MV),
            )
            assert cur.fetchone()[0] == 1  # 행 증가 없음
            cur.execute(
                "SELECT human_label FROM detections WHERE post_id=%s AND model_version=%s",
                (fk_post_id, _MV),
            )
            assert cur.fetchone()[0] == "사설서버"  # 마지막 값으로 덮어쓰기


@requires_pg
def test_set_human_label_no_match_returns_zero(clean_db) -> None:
    """매칭 행이 없으면 0 반환 (예외 아님)."""
    repo = DetectionRepository(clean_db)
    assert repo.set_human_label(999999, _MV, "핵_치트") == 0


def test_set_human_label_rejects_invalid_label() -> None:
    """enum 밖 값은 DB 도달 전 ValueError — pool 없이도 차단 검증."""
    repo = DetectionRepository(pool=None)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="invalid human_label"):
        repo.set_human_label(1, _MV, "존재하지않는라벨")
