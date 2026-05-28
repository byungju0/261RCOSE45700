package com.tracker.api.notification.dto;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record NotificationRuleRequest(
        @NotBlank String name,
        @NotNull Long channelId,
        boolean enabled,
        @Min(0) @Max(1) Double minConfidence,
        String minTier,
        String detectionType,
        String sourceSiteName
) {
}
