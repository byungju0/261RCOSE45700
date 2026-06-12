-- Story 3-7 (2026-06-11 Epic 3 재정의 — 멀티 에이전트 오케스트레이터)
-- agent_runs: 멀티 에이전트 파이프라인의 스테이지별 trace/비용 기록 테이블.
--
-- 목적:
--   DETECTION_MODE=agentic에서 S0(normalize)~S3(synthesize) 각 스테이지의 입출력·토큰·
--   비용·지연시간을 detections와 같은 트랜잭션으로 기록 → 디버깅·비용 추적·Story 3-9
--   A/B 실측의 데이터 소스. 링크 추적(S2b) fetch 결과는 별도 테이블 없이 output JSONB에 내장.
--
-- 설계 원칙:
--   - 순수 ADDITIVE — 기존 테이블(detections/posts/sources)·인덱스·제약 무변경 (출력 계약 불변).
--   - detections 멱등 conflict(ON CONFLICT DO NOTHING) 시 agent_runs도 INSERT skip —
--     detection_id NOT NULL 보장은 애플리케이션(DetectionRepository)에서.
--   - 대시보드/API 미노출 (backend-only diagnostic). DTO/프론트 계약에 미포함.
--   - Flyway 재실행 멱등: CREATE TABLE IF NOT EXISTS / CREATE INDEX IF NOT EXISTS.

CREATE TABLE IF NOT EXISTS agent_runs (
    id             BIGSERIAL PRIMARY KEY,
    detection_id   BIGINT REFERENCES detections(id) ON DELETE CASCADE,
    post_id        BIGINT NOT NULL REFERENCES posts(id),
    stage          VARCHAR(20) NOT NULL,   -- normalize|triage|image|link_trace|synthesize
    model          VARCHAR(50),            -- NULL = LLM 미사용 스테이지 (normalize/link_trace fetch)
    input_tokens   INT NOT NULL DEFAULT 0,
    output_tokens  INT NOT NULL DEFAULT 0,
    cost_usd       NUMERIC(10,6) NOT NULL DEFAULT 0,
    latency_ms     INT,
    output         JSONB,                  -- 스테이지 출력 전문 (링크 fetch 결과 내장)
    correlation_id VARCHAR(100),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 게시글 단위 trace 조회 (디버깅·3-9 비용 집계의 기본 액세스 패턴)
CREATE INDEX IF NOT EXISTS idx_agent_runs_post_id ON agent_runs (post_id);

-- detection 단위 trace 조회 (탐지 결과 → 증거 역추적)
CREATE INDEX IF NOT EXISTS idx_agent_runs_detection_id ON agent_runs (detection_id);
