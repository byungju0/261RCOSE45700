package com.tracker.api.notification.service;

public record NotificationSendResult(
        boolean success,
        Integer responseCode,
        String errorMessage
) {
    public static NotificationSendResult success(Integer responseCode) {
        return new NotificationSendResult(true, responseCode, null);
    }

    public static NotificationSendResult failure(Integer responseCode, String errorMessage) {
        return new NotificationSendResult(false, responseCode, sanitize(errorMessage));
    }

    private static String sanitize(String value) {
        if (value == null) return null;
        return value.length() > 500 ? value.substring(0, 500) : value;
    }
}
