package com.tracker.api.notification.controller;

import com.tracker.api.notification.dto.*;
import com.tracker.api.notification.service.NotificationChannelService;
import com.tracker.api.notification.service.NotificationRuleService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.UUID;

@RestController
@RequestMapping("/api/notifications")
@RequiredArgsConstructor
@Tag(name = "Notifications", description = "사용자 설정 기반 알림 채널과 규칙 관리")
public class NotificationController {

    private final NotificationChannelService channelService;
    private final NotificationRuleService ruleService;

    @GetMapping("/channels")
    @Operation(summary = "알림 채널 목록 조회")
    public ResponseEntity<List<NotificationChannelResponse>> getChannels(HttpServletRequest request) {
        return ok(channelService.listChannels(), request);
    }

    @PostMapping("/channels")
    @Operation(summary = "알림 채널 등록", description = "Webhook URL은 서버에서 암호화 저장하고 응답에는 마스킹 값만 반환.")
    public ResponseEntity<NotificationChannelResponse> createChannel(
            @Valid @RequestBody NotificationChannelRequest body,
            HttpServletRequest request) {
        return ResponseEntity.status(201)
                .header("X-Correlation-ID", resolveCorrelationId(request))
                .body(channelService.createChannel(body));
    }

    @PostMapping("/channels/{id}/test")
    @Operation(summary = "알림 채널 테스트 발송")
    public ResponseEntity<NotificationTestResponse> testChannel(
            @PathVariable Long id,
            HttpServletRequest request) {
        return ok(channelService.testChannel(id), request);
    }

    @GetMapping("/rules")
    @Operation(summary = "알림 규칙 목록 조회")
    public ResponseEntity<List<NotificationRuleResponse>> getRules(HttpServletRequest request) {
        return ok(ruleService.listRules(), request);
    }

    @PostMapping("/rules")
    @Operation(summary = "알림 규칙 등록")
    public ResponseEntity<NotificationRuleResponse> createRule(
            @Valid @RequestBody NotificationRuleRequest body,
            HttpServletRequest request) {
        return ResponseEntity.status(201)
                .header("X-Correlation-ID", resolveCorrelationId(request))
                .body(ruleService.createRule(body));
    }

    @GetMapping("/deliveries")
    @Operation(summary = "최근 알림 발송 이력 조회")
    public ResponseEntity<List<NotificationDeliveryResponse>> getDeliveries(HttpServletRequest request) {
        return ok(channelService.listRecentDeliveries(), request);
    }

    private <T> ResponseEntity<T> ok(T body, HttpServletRequest request) {
        return ResponseEntity.ok()
                .header("X-Correlation-ID", resolveCorrelationId(request))
                .body(body);
    }

    private static String resolveCorrelationId(HttpServletRequest request) {
        String id = request.getHeader("X-Correlation-ID");
        return (id != null && !id.isBlank()) ? id : UUID.randomUUID().toString();
    }
}
