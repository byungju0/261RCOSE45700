package com.tracker.api.notification.service;

import com.tracker.api.domain.Detection;
import com.tracker.api.notification.domain.NotificationRule;
import org.springframework.stereotype.Component;
import org.springframework.util.StringUtils;

@Component
public class NotificationRuleEvaluator {

    public boolean matches(NotificationRule rule, Detection detection) {
        if (rule.getMinConfidence() != null && detection.getConfidence() < rule.getMinConfidence()) {
            return false;
        }
        if (StringUtils.hasText(rule.getMinTier())
                && tierRank(detection.getTier()) > tierRank(rule.getMinTier())) {
            return false;
        }
        if (StringUtils.hasText(rule.getDetectionType())
                && !rule.getDetectionType().equals(detection.getType())) {
            return false;
        }
        return !StringUtils.hasText(rule.getSourceSiteName())
                || rule.getSourceSiteName().equals(detection.getPost().getSource().getSiteName());
    }

    private int tierRank(String tier) {
        return switch (tier) {
            case "T1" -> 1;
            case "T2" -> 2;
            case "T3" -> 3;
            default -> 4;
        };
    }
}
