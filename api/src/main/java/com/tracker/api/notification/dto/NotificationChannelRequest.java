package com.tracker.api.notification.dto;

import com.tracker.api.notification.domain.NotificationChannelType;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record NotificationChannelRequest(
        @NotBlank String name,
        @NotNull NotificationChannelType type,
        @NotBlank String webhookUrl,
        boolean enabled
) {
}
