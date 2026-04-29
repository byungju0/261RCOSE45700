-- sources: 크롤링 대상 커뮤니티 사이트
CREATE TABLE sources (
    id          BIGSERIAL PRIMARY KEY,
    site_name   VARCHAR(50)  NOT NULL,
    board_name  VARCHAR(200),
    base_url    VARCHAR(500) NOT NULL,
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- posts: 크롤링된 게시글
CREATE TABLE posts (
    id                  BIGSERIAL PRIMARY KEY,
    source_id           BIGINT       NOT NULL REFERENCES sources(id),
    post_id_at_source   VARCHAR(200) NOT NULL,
    title               TEXT,
    body                TEXT,
    author              VARCHAR(200),
    post_url            VARCHAR(1000) NOT NULL,
    language            VARCHAR(10),
    crawled_at          TIMESTAMP WITH TIME ZONE NOT NULL,
    UNIQUE (source_id, post_id_at_source)
);

-- post_images: 게시글 첨부 이미지
CREATE TABLE post_images (
    id          BIGSERIAL PRIMARY KEY,
    post_id     BIGINT        NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    image_url   VARCHAR(1000) NOT NULL,
    s3_key      VARCHAR(500),
    image_hash  VARCHAR(64),
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- detections: VARCO AI 탐지 결과
CREATE TABLE detections (
    id            BIGSERIAL PRIMARY KEY,
    post_id       BIGINT        NOT NULL REFERENCES posts(id),
    is_illegal    BOOLEAN       NOT NULL,
    type          VARCHAR(50),
    confidence    DOUBLE PRECISION NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    reason        TEXT,
    model_version VARCHAR(50)   NOT NULL,
    detected_at   TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);
