package com.tracker.api.notification.adapter;

import com.tracker.api.domain.Detection;
import com.tracker.api.notification.domain.NotificationChannelType;
import com.tracker.api.notification.service.NotificationTemplateRenderer;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

import java.util.Map;

@Component
public class GoogleChatWebhookAdapter extends AbstractWebhookAdapter {

    public GoogleChatWebhookAdapter(RestClient.Builder builder, NotificationTemplateRenderer renderer) {
        super(builder, renderer);
    }

    @Override
    public NotificationChannelType type() {
        return NotificationChannelType.GOOGLE_CHAT;
    }

    @Override
    protected Map<String, Object> payload(Detection detection, String text) {
        return Map.of("text", text);
    }
}
