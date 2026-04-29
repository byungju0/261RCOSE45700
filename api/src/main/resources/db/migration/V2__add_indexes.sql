-- GET /detections 필터(날짜·유형·신뢰도) p95 ≤ 500ms NFR 충족
CREATE INDEX idx_detections_filter ON detections (detected_at DESC, type, confidence DESC);

-- posts.source_id FK 인덱스
CREATE INDEX idx_posts_source_id ON posts (source_id);
