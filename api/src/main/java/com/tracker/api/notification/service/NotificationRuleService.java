package com.tracker.api.notification.service;

import com.tracker.api.exception.NotificationResourceNotFoundException;
import com.tracker.api.notification.domain.NotificationEventType;
import com.tracker.api.notification.domain.NotificationRule;
import com.tracker.api.notification.domain.NotificationSendMode;
import com.tracker.api.notification.dto.NotificationRuleRequest;
import com.tracker.api.notification.dto.NotificationRuleResponse;
import com.tracker.api.notification.repository.NotificationChannelRepository;
import com.tracker.api.notification.repository.NotificationRuleRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;

import java.util.List;

@Service
@RequiredArgsConstructor
public class NotificationRuleService {

    private final NotificationRuleRepository ruleRepository;
    private final NotificationChannelRepository channelRepository;

    @Transactional(readOnly = true)
    public List<NotificationRuleResponse> listRules() {
        return ruleRepository.findAllFetched().stream()
                .map(NotificationRuleResponse::from)
                .toList();
    }

    @Transactional
    public NotificationRuleResponse createRule(NotificationRuleRequest request) {
        var channel = channelRepository.findById(request.channelId())
                .orElseThrow(() -> new NotificationResourceNotFoundException(
                        "알림 채널을 찾을 수 없습니다: " + request.channelId()));
        NotificationRule rule = new NotificationRule();
        rule.setName(request.name());
        rule.setEnabled(request.enabled());
        rule.setEventType(NotificationEventType.DETECTION_CREATED);
        rule.setChannel(channel);
        rule.setMinConfidence(request.minConfidence());
        rule.setMinTier(normalize(request.minTier()));
        rule.setDetectionType(normalize(request.detectionType()));
        rule.setSourceSiteName(normalize(request.sourceSiteName()));
        rule.setSendMode(NotificationSendMode.IMMEDIATE);
        return NotificationRuleResponse.from(ruleRepository.save(rule));
    }

    private String normalize(String value) {
        return StringUtils.hasText(value) ? value : null;
    }
}
