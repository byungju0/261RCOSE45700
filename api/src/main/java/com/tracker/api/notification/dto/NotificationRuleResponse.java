package com.tracker.api.notification.dto;

import com.tracker.api.notification.domain.NotificationRule;

public record NotificationRuleResponse(
        Long id,
        String name,
        boolean enabled,
        Long channelId,
        String channelName,
        Double minConfidence,
        String minTier,
        String detectionType,
        String sourceSiteName,
        String createdAt,
        String updatedAt
) {
    public static NotificationRuleResponse from(NotificationRule rule) {
        return new NotificationRuleResponse(
                rule.getId(),
                rule.getName(),
                rule.isEnabled(),
                rule.getChannel().getId(),
                rule.getChannel().getName(),
                rule.getMinConfidence(),
                rule.getMinTier(),
                rule.getDetectionType(),
                rule.getSourceSiteName(),
                rule.getCreatedAt().toString(),
                rule.getUpdatedAt().toString()
        );
    }
}
