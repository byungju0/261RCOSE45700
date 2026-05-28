package com.tracker.api.notification.dto;

import com.tracker.api.notification.domain.NotificationDelivery;
import com.tracker.api.notification.domain.NotificationDeliveryStatus;

public record NotificationDeliveryResponse(
        Long id,
        Long detectionId,
        Long channelId,
        String channelName,
        NotificationDeliveryStatus status,
        Integer responseCode,
        String errorMessage,
        String attemptedAt,
        String sentAt
) {
    public static NotificationDeliveryResponse from(NotificationDelivery delivery) {
        return new NotificationDeliveryResponse(
                delivery.getId(),
                delivery.getDetection() == null ? null : delivery.getDetection().getId(),
                delivery.getChannel() == null ? null : delivery.getChannel().getId(),
                delivery.getChannel() == null ? null : delivery.getChannel().getName(),
                delivery.getStatus(),
                delivery.getResponseCode(),
                delivery.getErrorMessage(),
                delivery.getAttemptedAt().toString(),
                delivery.getSentAt() == null ? null : delivery.getSentAt().toString()
        );
    }
}
