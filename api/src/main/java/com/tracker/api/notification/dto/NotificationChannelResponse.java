package com.tracker.api.notification.dto;

import com.tracker.api.notification.domain.NotificationChannel;
import com.tracker.api.notification.domain.NotificationChannelType;

public record NotificationChannelResponse(
        Long id,
        String name,
        NotificationChannelType type,
        boolean enabled,
        String configPreview,
        String lastTestedAt,
        String lastSuccessAt,
        String lastFailureAt,
        String createdAt,
        String updatedAt
) {
    public static NotificationChannelResponse from(NotificationChannel channel) {
        return new NotificationChannelResponse(
                channel.getId(),
                channel.getName(),
                channel.getType(),
                channel.isEnabled(),
                channel.getConfigPreview(),
                channel.getLastTestedAt() == null ? null : channel.getLastTestedAt().toString(),
                channel.getLastSuccessAt() == null ? null : channel.getLastSuccessAt().toString(),
                channel.getLastFailureAt() == null ? null : channel.getLastFailureAt().toString(),
                channel.getCreatedAt().toString(),
                channel.getUpdatedAt().toString()
        );
    }
}
