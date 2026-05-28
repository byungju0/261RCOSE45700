package com.tracker.api.notification.service;

import com.tracker.api.domain.Detection;
import com.tracker.api.notification.domain.*;
import com.tracker.api.notification.repository.NotificationDeliveryRepository;
import com.tracker.api.notification.repository.NotificationEventRepository;
import com.tracker.api.notification.repository.NotificationRuleRepository;
import lombok.RequiredArgsConstructor;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

import java.time.Instant;
import java.util.List;

@Service
@RequiredArgsConstructor
@ConditionalOnProperty(name = "tracker.notifications.scheduler.enabled", havingValue = "true", matchIfMissing = true)
public class NotificationEventProcessor {

    private static final Logger log = LoggerFactory.getLogger(NotificationEventProcessor.class);

    private final NotificationEventRepository eventRepository;
    private final NotificationRuleRepository ruleRepository;
    private final NotificationDeliveryRepository deliveryRepository;
    private final NotificationRuleEvaluator ruleEvaluator;
    private final NotificationChannelService channelService;
    private final TransactionTemplate transactionTemplate;

    @Value("${tracker.notifications.batch-size:10}")
    private int batchSize;

    @Value("${tracker.notifications.max-attempts:3}")
    private int maxAttempts;

    @Value("${tracker.notifications.processing-timeout-seconds:120}")
    private int processingTimeoutSeconds;

    @Scheduled(fixedDelayString = "${tracker.notifications.poll-delay-ms:5000}")
    public void processPendingEvents() {
        List<Long> ids = claimPendingEvents();
        for (Long id : ids) {
            try {
                processEvent(id);
            } catch (Exception e) {
                log.warn("notification event 처리 실패: id={}", id, e);
                markFailed(id, e.getMessage());
            }
        }
    }

    private List<Long> claimPendingEvents() {
        return transactionTemplate.execute(status -> {
            List<Long> ids = eventRepository.findPendingIdsForUpdate(
                    batchSize, maxAttempts, processingTimeoutSeconds);
            if (!ids.isEmpty()) {
                eventRepository.markClaimed(ids, NotificationEventStatus.PROCESSING, Instant.now());
            }
            return ids;
        });
    }

    private void processEvent(Long id) {
        transactionTemplate.executeWithoutResult(status -> {
            NotificationEvent event = eventRepository.findByIdFetched(id)
                    .orElseThrow(() -> new IllegalStateException("notification event 없음: " + id));
            Detection detection = event.getDetection();
            if (detection == null || !detection.isIllegal()) {
                finish(event, NotificationEventStatus.SKIPPED, null);
                return;
            }

            List<NotificationRule> rules = ruleRepository.findEnabledRules(event.getEventType());
            List<NotificationRule> matchedRules = rules.stream()
                    .filter(rule -> ruleEvaluator.matches(rule, detection))
                    .toList();

            if (matchedRules.isEmpty()) {
                finish(event, NotificationEventStatus.SKIPPED, null);
                return;
            }

            boolean anySuccess = false;
            String lastError = null;
            for (NotificationRule rule : matchedRules) {
                NotificationSendResult result = channelService
                        .adapterFor(rule.getChannel().getType())
                        .send(detection, channelService.readConfig(rule.getChannel()));
                saveDelivery(event, rule, result);
                if (result.success()) {
                    anySuccess = true;
                    rule.getChannel().setLastSuccessAt(Instant.now());
                } else {
                    lastError = result.errorMessage();
                    rule.getChannel().setLastFailureAt(Instant.now());
                }
            }

            if (anySuccess) {
                finish(event, NotificationEventStatus.COMPLETED, null);
            } else if (event.getAttempts() >= maxAttempts) {
                finish(event, NotificationEventStatus.FAILED, lastError);
            } else {
                event.setStatus(NotificationEventStatus.PENDING);
                event.setLastError(lastError);
            }
        });
    }

    private void markFailed(Long id, String error) {
        transactionTemplate.executeWithoutResult(status -> eventRepository.findById(id).ifPresent(event -> {
            event.setStatus(event.getAttempts() >= maxAttempts
                    ? NotificationEventStatus.FAILED
                    : NotificationEventStatus.PENDING);
            event.setLastError(error);
        }));
    }

    private void saveDelivery(NotificationEvent event, NotificationRule rule, NotificationSendResult result) {
        NotificationDelivery delivery = new NotificationDelivery();
        delivery.setEvent(event);
        delivery.setDetection(event.getDetection());
        delivery.setRule(rule);
        delivery.setChannel(rule.getChannel());
        delivery.setStatus(result.success()
                ? NotificationDeliveryStatus.SUCCESS
                : NotificationDeliveryStatus.FAILED);
        delivery.setResponseCode(result.responseCode());
        delivery.setErrorMessage(result.errorMessage());
        delivery.setAttemptedAt(Instant.now());
        delivery.setSentAt(result.success() ? Instant.now() : null);
        deliveryRepository.save(delivery);
    }

    private void finish(NotificationEvent event, NotificationEventStatus status, String error) {
        event.setStatus(status);
        event.setLastError(error);
        event.setProcessedAt(Instant.now());
    }
}
