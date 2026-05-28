package com.tracker.api.notification.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.tracker.api.exception.NotificationResourceNotFoundException;
import com.tracker.api.notification.adapter.NotificationChannelAdapter;
import com.tracker.api.notification.domain.NotificationChannel;
import com.tracker.api.notification.domain.NotificationChannelType;
import com.tracker.api.notification.domain.NotificationDeliveryStatus;
import com.tracker.api.notification.dto.NotificationChannelRequest;
import com.tracker.api.notification.dto.NotificationChannelResponse;
import com.tracker.api.notification.dto.NotificationDeliveryResponse;
import com.tracker.api.notification.dto.NotificationTestResponse;
import com.tracker.api.notification.repository.NotificationChannelRepository;
import com.tracker.api.notification.repository.NotificationDeliveryRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.Instant;
import java.util.EnumMap;
import java.util.List;
import java.util.Map;

@Service
public class NotificationChannelService {

    private final NotificationChannelRepository channelRepository;
    private final NotificationDeliveryRepository deliveryRepository;
    private final NotificationSecretCrypto crypto;
    private final ObjectMapper objectMapper;
    private final Map<NotificationChannelType, NotificationChannelAdapter> adapters;

    public NotificationChannelService(
            NotificationChannelRepository channelRepository,
            NotificationDeliveryRepository deliveryRepository,
            NotificationSecretCrypto crypto,
            ObjectMapper objectMapper,
            List<NotificationChannelAdapter> adapterList) {
        this.channelRepository = channelRepository;
        this.deliveryRepository = deliveryRepository;
        this.crypto = crypto;
        this.objectMapper = objectMapper;
        this.adapters = new EnumMap<>(NotificationChannelType.class);
        for (NotificationChannelAdapter adapter : adapterList) {
            adapters.put(adapter.type(), adapter);
        }
    }

    @Transactional(readOnly = true)
    public List<NotificationChannelResponse> listChannels() {
        return channelRepository.findAllByOrderByCreatedAtDesc().stream()
                .map(NotificationChannelResponse::from)
                .toList();
    }

    @Transactional
    public NotificationChannelResponse createChannel(NotificationChannelRequest request) {
        WebhookConfig config = new WebhookConfig(request.webhookUrl());
        NotificationChannel channel = new NotificationChannel();
        channel.setName(request.name());
        channel.setType(request.type());
        channel.setEnabled(request.enabled());
        channel.setEncryptedConfig(crypto.encrypt(writeConfig(config)));
        channel.setConfigFingerprint(crypto.fingerprint(request.webhookUrl()));
        channel.setConfigPreview(maskWebhookUrl(request.webhookUrl()));
        return NotificationChannelResponse.from(channelRepository.save(channel));
    }

    @Transactional
    public NotificationTestResponse testChannel(Long id) {
        NotificationChannel channel = findChannel(id);
        NotificationChannelAdapter adapter = adapterFor(channel.getType());
        NotificationSendResult result = adapter.test(readConfig(channel));
        Instant now = Instant.now();
        channel.setLastTestedAt(now);
        if (result.success()) {
            channel.setLastSuccessAt(now);
        } else {
            channel.setLastFailureAt(now);
        }
        return new NotificationTestResponse(result.success(), result.responseCode(), result.errorMessage());
    }

    @Transactional(readOnly = true)
    public List<NotificationDeliveryResponse> listRecentDeliveries() {
        return deliveryRepository.findTop20ByOrderByAttemptedAtDesc().stream()
                .map(NotificationDeliveryResponse::from)
                .toList();
    }

    WebhookConfig readConfig(NotificationChannel channel) {
        try {
            return objectMapper.readValue(crypto.decrypt(channel.getEncryptedConfig()), WebhookConfig.class);
        } catch (Exception e) {
            throw new IllegalStateException("notification channel config 파싱 실패", e);
        }
    }

    NotificationChannelAdapter adapterFor(NotificationChannelType type) {
        NotificationChannelAdapter adapter = adapters.get(type);
        if (adapter == null) {
            throw new IllegalStateException("지원하지 않는 알림 채널입니다: " + type);
        }
        return adapter;
    }

    private NotificationChannel findChannel(Long id) {
        return channelRepository.findById(id)
                .orElseThrow(() -> new NotificationResourceNotFoundException("알림 채널을 찾을 수 없습니다: " + id));
    }

    private String writeConfig(WebhookConfig config) {
        try {
            return objectMapper.writeValueAsString(config);
        } catch (Exception e) {
            throw new IllegalStateException("notification channel config 직렬화 실패", e);
        }
    }

    private String maskWebhookUrl(String webhookUrl) {
        int visible = Math.min(6, webhookUrl.length());
        return "••••" + webhookUrl.substring(webhookUrl.length() - visible);
    }
}
