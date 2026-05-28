package com.tracker.api.notification.dto;

public record NotificationTestResponse(
        boolean success,
        Integer responseCode,
        String errorMessage
) {
}
