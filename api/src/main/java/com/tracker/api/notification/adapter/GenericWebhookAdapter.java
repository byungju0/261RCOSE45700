package com.tracker.api.notification.adapter;

import com.tracker.api.domain.Detection;
import com.tracker.api.notification.domain.NotificationChannelType;
import com.tracker.api.notification.service.NotificationTemplateRenderer;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

import java.util.LinkedHashMap;
import java.util.Map;

@Component
public class GenericWebhookAdapter extends AbstractWebhookAdapter {

    public GenericWebhookAdapter(RestClient.Builder builder, NotificationTemplateRenderer renderer) {
        super(builder, renderer);
    }

    @Override
    public NotificationChannelType type() {
        return NotificationChannelType.GENERIC_WEBHOOK;
    }

    @Override
    protected Map<String, Object> payload(Detection detection, String text) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("eventType", "DETECTION_CREATED");
        payload.put("text", text);
        payload.put("detectionId", detection.getId());
        payload.put("siteName", detection.getPost().getSource().getSiteName());
        payload.put("type", detection.getType());
        payload.put("tier", detection.getTier());
        payload.put("confidence", detection.getConfidence());
        payload.put("postUrl", detection.getPost().getPostUrl());
        payload.put("detectedAt", detection.getDetectedAt().toString());
        return payload;
    }
}
