-- DLQ 재처리 시 중복 삽입 방지 — 멱등성 보장
ALTER TABLE detections
    ADD CONSTRAINT uq_detection_post_model UNIQUE (post_id, model_version);
