package com.tracker.api.notification.adapter;

import com.tracker.api.domain.Detection;
import com.tracker.api.notification.domain.NotificationChannelType;
import com.tracker.api.notification.service.NotificationSendResult;
import com.tracker.api.notification.service.WebhookConfig;

public interface NotificationChannelAdapter {
    NotificationChannelType type();
    NotificationSendResult send(Detection detection, WebhookConfig config);
    NotificationSendResult test(WebhookConfig config);
}
