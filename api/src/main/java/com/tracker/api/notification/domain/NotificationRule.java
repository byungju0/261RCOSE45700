package com.tracker.api.notification.domain;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.time.Instant;

@Entity
@Table(name = "notification_rules")
@Getter
@Setter
@NoArgsConstructor
public class NotificationRule {

    @Id @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 100)
    private String name;

    @Column(nullable = false)
    private boolean enabled = true;

    @Enumerated(EnumType.STRING)
    @Column(name = "event_type", nullable = false, length = 50)
    private NotificationEventType eventType = NotificationEventType.DETECTION_CREATED;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "channel_id", nullable = false)
    private NotificationChannel channel;

    @Column(name = "min_confidence")
    private Double minConfidence;

    @Column(name = "min_tier", length = 2)
    private String minTier;

    @Column(name = "detection_type", length = 50)
    private String detectionType;

    @Column(name = "source_site_name", length = 50)
    private String sourceSiteName;

    @Enumerated(EnumType.STRING)
    @Column(name = "send_mode", nullable = false, length = 20)
    private NotificationSendMode sendMode = NotificationSendMode.IMMEDIATE;

    @Column(name = "created_at", nullable = false)
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    @PrePersist
    void prePersist() {
        Instant now = Instant.now();
        createdAt = now;
        updatedAt = now;
    }

    @PreUpdate
    void preUpdate() {
        updatedAt = Instant.now();
    }
}
