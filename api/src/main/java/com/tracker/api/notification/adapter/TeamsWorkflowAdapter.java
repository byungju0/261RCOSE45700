package com.tracker.api.notification.adapter;

import com.tracker.api.domain.Detection;
import com.tracker.api.notification.domain.NotificationChannelType;
import com.tracker.api.notification.service.NotificationTemplateRenderer;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

import java.util.Map;

@Component
public class TeamsWorkflowAdapter extends AbstractWebhookAdapter {

    public TeamsWorkflowAdapter(RestClient.Builder builder, NotificationTemplateRenderer renderer) {
        super(builder, renderer);
    }

    @Override
    public NotificationChannelType type() {
        return NotificationChannelType.TEAMS_WORKFLOW;
    }

    @Override
    protected Map<String, Object> payload(Detection detection, String text) {
        return Map.of(
                "text", text,
                "title", "[Tracker] 불법 프로그램 의심 게시글 탐지",
                "detectionId", detection.getId(),
                "siteName", detection.getPost().getSource().getSiteName(),
                "type", detection.getType(),
                "tier", detection.getTier(),
                "confidence", detection.getConfidence()
        );
    }
}
