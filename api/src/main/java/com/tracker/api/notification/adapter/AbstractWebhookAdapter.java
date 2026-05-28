package com.tracker.api.notification.adapter;

import com.tracker.api.domain.Detection;
import com.tracker.api.notification.service.NotificationSendResult;
import com.tracker.api.notification.service.NotificationTemplateRenderer;
import com.tracker.api.notification.service.WebhookConfig;
import org.springframework.http.MediaType;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClientResponseException;

import java.util.Map;

abstract class AbstractWebhookAdapter implements NotificationChannelAdapter {

    private final RestClient restClient;
    private final NotificationTemplateRenderer renderer;

    protected AbstractWebhookAdapter(RestClient.Builder builder, NotificationTemplateRenderer renderer) {
        this.restClient = builder.build();
        this.renderer = renderer;
    }

    @Override
    public NotificationSendResult send(Detection detection, WebhookConfig config) {
        return post(config.webhookUrl(), payload(detection, renderer.renderText(detection)));
    }

    @Override
    public NotificationSendResult test(WebhookConfig config) {
        return post(config.webhookUrl(), testPayload("[Tracker] 테스트 알림입니다. 알림 채널 연결이 정상입니다."));
    }

    protected abstract Map<String, Object> payload(Detection detection, String text);

    protected Map<String, Object> testPayload(String text) {
        return Map.of("text", text);
    }

    protected NotificationSendResult post(String webhookUrl, Map<String, Object> body) {
        try {
            var response = restClient.post()
                    .uri(webhookUrl)
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(body)
                    .retrieve()
                    .toBodilessEntity();
            return NotificationSendResult.success(response.getStatusCode().value());
        } catch (RestClientResponseException e) {
            return NotificationSendResult.failure(e.getStatusCode().value(), e.getResponseBodyAsString());
        } catch (RestClientException e) {
            return NotificationSendResult.failure(null, e.getMessage());
        }
    }
}
