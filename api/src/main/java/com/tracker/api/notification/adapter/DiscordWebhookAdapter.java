package com.tracker.api.notification.adapter;

import com.tracker.api.domain.Detection;
import com.tracker.api.notification.domain.NotificationChannelType;
import com.tracker.api.notification.service.NotificationTemplateRenderer;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

import java.util.List;
import java.util.Map;

@Component
public class DiscordWebhookAdapter extends AbstractWebhookAdapter {

    public DiscordWebhookAdapter(RestClient.Builder builder, NotificationTemplateRenderer renderer) {
        super(builder, renderer);
    }

    @Override
    public NotificationChannelType type() {
        return NotificationChannelType.DISCORD;
    }

    @Override
    protected Map<String, Object> payload(Detection detection, String text) {
        return Map.of(
                "content", "[Tracker] 불법 프로그램 의심 게시글 탐지",
                "embeds", List.of(Map.of(
                        "title", detection.getType() + " · " + detection.getTier(),
                        "description", text,
                        "color", 15158332
                ))
        );
    }

    @Override
    protected Map<String, Object> testPayload(String text) {
        return Map.of("content", text);
    }
}
