package com.tracker.api.notification.service;

import jakarta.validation.constraints.NotBlank;

public record WebhookConfig(
        @NotBlank String webhookUrl
) {
}
