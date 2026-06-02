-- Story 3-5 (2026-06-02 재정의 — few-shot 학습용 라벨 데이터 수집 기반)
-- detections에 "사람이 검증한 정답 라벨" 컬럼을 additive로 추가.
--
-- 목적:
--   전수 저장된 detections(Story 3-4)에 human_label을 RDS 컬럼으로 부여 → Spring API(api/)가
--   추가 마이그레이션 없이 즉시 읽을 수 있는 backend-connected 경로. 누적 라벨은 향후 game·type별
--   few-shot 예시 코퍼스의 정답 소스가 된다.
--
-- 설계 원칙:
--   - 순수 ADD COLUMN (모두 NULLABLE) — 기존 행은 모두 NULL = 미라벨. 기존 컬럼/인덱스/제약 무변경.
--   - Flyway 재실행 멱등: ADD COLUMN IF NOT EXISTS / CREATE INDEX IF NOT EXISTS.
--   - human_label enum 검증은 애플리케이션(DetectionRepository.set_human_label)에서 차단 —
--     향후 9-type enum 변경 시 마이그레이션 재작성 부담을 피하려고 DB CHECK는 두지 않음.

-- 1) 라벨 컬럼 3개 (모두 NULLABLE)
ALTER TABLE detections
    ADD COLUMN IF NOT EXISTS human_label       VARCHAR(32);     -- 9-type enum 값 또는 'unknown'. NULL=미라벨
ALTER TABLE detections
    ADD COLUMN IF NOT EXISTS human_verified_at TIMESTAMP WITH TIME ZONE;  -- 라벨 확정 시각. NULL=미라벨
ALTER TABLE detections
    ADD COLUMN IF NOT EXISTS label_source      VARCHAR(32);     -- 라벨 출처(예: 'manual_cli')

-- 2) 미라벨 행 빠른 조회용 partial 인덱스 (라벨링 CLI가 human_label IS NULL을 detected_at DESC로 스캔)
CREATE INDEX IF NOT EXISTS idx_detections_unlabeled
    ON detections (detected_at DESC)
    WHERE human_label IS NULL;
