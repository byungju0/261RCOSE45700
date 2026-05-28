package com.tracker.api.notification.service;

import com.tracker.api.domain.Detection;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class NotificationTemplateRenderer {

    private final String dashboardUrl;

    public NotificationTemplateRenderer(
            @Value("${tracker.dashboard-url:http://localhost:5173}") String dashboardUrl) {
        this.dashboardUrl = trimTrailingSlash(dashboardUrl);
    }

    public String renderText(Detection detection) {
        String snippet = detection.getTranslatedText() != null && !detection.getTranslatedText().isBlank()
                ? detection.getTranslatedText()
                : detection.getPost().getBody();
        return """
                [Tracker] 불법 프로그램 의심 게시글 탐지

                사이트: %s
                유형: %s
                신뢰도: %.2f
                Tier: %s
                탐지 시간: %s

                요약:
                %s

                원문 URL: %s
                대시보드: %s/detections/%d
                """.formatted(
                detection.getPost().getSource().getSiteName(),
                detection.getType(),
                detection.getConfidence(),
                detection.getTier(),
                detection.getDetectedAt(),
                abbreviate(snippet, 500),
                detection.getPost().getPostUrl() == null ? "(없음)" : detection.getPost().getPostUrl(),
                dashboardUrl,
                detection.getId()
        );
    }

    private static String abbreviate(String value, int maxLength) {
        if (value == null) return "";
        return value.length() <= maxLength ? value : value.substring(0, maxLength - 3) + "...";
    }

    private static String trimTrailingSlash(String value) {
        if (value.endsWith("/")) return value.substring(0, value.length() - 1);
        return value;
    }
}
