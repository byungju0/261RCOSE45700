package com.tracker.api.exception;

public class NotificationResourceNotFoundException extends RuntimeException {
    public NotificationResourceNotFoundException(String message) {
        super(message);
    }
}
