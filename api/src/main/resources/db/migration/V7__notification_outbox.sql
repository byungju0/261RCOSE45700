-- Notification outbox + user-configured channel/rule tables.
-- Detection worker writes notification_events in the same transaction as detections.
-- Spring API owns channel secrets, rule evaluation, delivery, and logs.

CREATE TABLE notification_events (
    id             BIGSERIAL PRIMARY KEY,
    event_type     VARCHAR(50) NOT NULL,
    detection_id   BIGINT REFERENCES detections(id) ON DELETE CASCADE,
    correlation_id VARCHAR(100),
    status         VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    attempts       INT NOT NULL DEFAULT 0,
    last_error     TEXT,
    created_at     TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    claimed_at     TIMESTAMP WITH TIME ZONE,
    processed_at   TIMESTAMP WITH TIME ZONE,
    CONSTRAINT notification_events_status_check
        CHECK (status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED', 'SKIPPED')),
    CONSTRAINT notification_events_type_check
        CHECK (event_type IN ('DETECTION_CREATED')),
    CONSTRAINT notification_events_detection_unique
        UNIQUE (event_type, detection_id)
);

CREATE INDEX idx_notification_events_pending
    ON notification_events (status, created_at, claimed_at);

CREATE TABLE notification_channels (
    id                 BIGSERIAL PRIMARY KEY,
    name               VARCHAR(100) NOT NULL,
    type               VARCHAR(50) NOT NULL,
    enabled            BOOLEAN NOT NULL DEFAULT TRUE,
    encrypted_config   TEXT NOT NULL,
    config_fingerprint VARCHAR(64) NOT NULL,
    config_preview     VARCHAR(200) NOT NULL,
    last_tested_at     TIMESTAMP WITH TIME ZONE,
    last_success_at    TIMESTAMP WITH TIME ZONE,
    last_failure_at    TIMESTAMP WITH TIME ZONE,
    created_at         TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    CONSTRAINT notification_channels_type_check
        CHECK (type IN (
            'GENERIC_WEBHOOK',
            'DISCORD',
            'GOOGLE_CHAT',
            'SLACK_WORKFLOW',
            'SLACK_WEBHOOK',
            'TEAMS_WORKFLOW'
        ))
);

CREATE TABLE notification_rules (
    id               BIGSERIAL PRIMARY KEY,
    name             VARCHAR(100) NOT NULL,
    enabled          BOOLEAN NOT NULL DEFAULT TRUE,
    event_type       VARCHAR(50) NOT NULL DEFAULT 'DETECTION_CREATED',
    channel_id       BIGINT NOT NULL REFERENCES notification_channels(id) ON DELETE CASCADE,
    min_confidence   DOUBLE PRECISION CHECK (min_confidence IS NULL OR (min_confidence >= 0 AND min_confidence <= 1)),
    min_tier         VARCHAR(2) CHECK (min_tier IS NULL OR min_tier IN ('T1', 'T2', 'T3', 'T4')),
    detection_type   VARCHAR(50),
    source_site_name VARCHAR(50),
    send_mode        VARCHAR(20) NOT NULL DEFAULT 'IMMEDIATE',
    created_at       TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    CONSTRAINT notification_rules_event_type_check
        CHECK (event_type IN ('DETECTION_CREATED')),
    CONSTRAINT notification_rules_send_mode_check
        CHECK (send_mode IN ('IMMEDIATE'))
);

CREATE INDEX idx_notification_rules_enabled
    ON notification_rules (enabled, event_type);

CREATE TABLE notification_deliveries (
    id            BIGSERIAL PRIMARY KEY,
    event_id      BIGINT NOT NULL REFERENCES notification_events(id) ON DELETE CASCADE,
    detection_id  BIGINT REFERENCES detections(id) ON DELETE CASCADE,
    rule_id       BIGINT REFERENCES notification_rules(id) ON DELETE SET NULL,
    channel_id    BIGINT REFERENCES notification_channels(id) ON DELETE SET NULL,
    status        VARCHAR(20) NOT NULL,
    response_code INT,
    error_message TEXT,
    attempted_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    sent_at       TIMESTAMP WITH TIME ZONE,
    CONSTRAINT notification_deliveries_status_check
        CHECK (status IN ('SUCCESS', 'FAILED', 'SKIPPED'))
);

CREATE INDEX idx_notification_deliveries_detection
    ON notification_deliveries (detection_id, attempted_at DESC);
