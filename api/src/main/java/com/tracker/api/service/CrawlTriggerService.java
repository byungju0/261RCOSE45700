package com.tracker.api.service;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.tracker.api.dto.CrawlJobStatusResponse;
import com.tracker.api.dto.CrawlPipelineStatsResponse;
import com.tracker.api.exception.CrawlJobNotFoundException;
import lombok.RequiredArgsConstructor;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;

@Service
@RequiredArgsConstructor
public class CrawlTriggerService {

    private static final String CRAWL_TRIGGER_CHANNEL = "crawl:trigger";
    private static final String CRAWL_JOB_KEY_PREFIX = "crawl:jobs:";
    private static final String CRAWL_STATS_LATEST_KEY = "crawl:stats:latest";
    private static final Duration CRAWL_JOB_TTL = Duration.ofHours(6);

    private final StringRedisTemplate stringRedisTemplate;
    private final ObjectMapper objectMapper;

    public String trigger(String correlationId) {
        String jobId = UUID.randomUUID().toString();
        String requestedAt = Instant.now().toString();
        String key = key(jobId);

        stringRedisTemplate.opsForHash().putAll(key, Map.ofEntries(
                Map.entry("jobId", jobId),
                Map.entry("status", "queued"),
                Map.entry("totalSites", "0"),
                Map.entry("completedSites", "0"),
                Map.entry("percent", "0"),
                Map.entry("currentSite", ""),
                Map.entry("message", "크롤링 대기 중"),
                Map.entry("failedSites", "[]"),
                Map.entry("requestedAt", requestedAt),
                Map.entry("startedAt", ""),
                Map.entry("updatedAt", requestedAt),
                Map.entry("finishedAt", "")
        ));
        stringRedisTemplate.expire(key, CRAWL_JOB_TTL);

        // Redis PUBLISH may return 0 when no crawler is subscribed; Story 4.2 treats the command as accepted.
        stringRedisTemplate.convertAndSend(CRAWL_TRIGGER_CHANNEL, triggerPayload(jobId, correlationId, requestedAt));

        return jobId;
    }

    public CrawlJobStatusResponse getStatus(String jobId) {
        Map<Object, Object> raw = stringRedisTemplate.opsForHash().entries(key(jobId));
        if (raw.isEmpty()) {
            throw new CrawlJobNotFoundException(jobId);
        }

        return new CrawlJobStatusResponse(
                value(raw, "jobId"),
                value(raw, "status"),
                intValue(raw, "totalSites"),
                intValue(raw, "completedSites"),
                intValue(raw, "percent"),
                value(raw, "currentSite"),
                value(raw, "message"),
                failedSites(raw),
                value(raw, "requestedAt"),
                value(raw, "startedAt"),
                value(raw, "updatedAt"),
                value(raw, "finishedAt")
        );
    }

    public CrawlPipelineStatsResponse getLatestPipelineStats() {
        String json = stringRedisTemplate.opsForValue().get(CRAWL_STATS_LATEST_KEY);
        if (json == null || json.isBlank()) {
            return new CrawlPipelineStatsResponse(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, "");
        }
        try {
            @SuppressWarnings("unchecked")
            Map<String, Object> data = objectMapper.readValue(json, Map.class);
            return new CrawlPipelineStatsResponse(
                    intFrom(data, "listingBoards"),
                    intFrom(data, "listingDiscoveredTotal"),
                    intFrom(data, "listingUrlsSelected"),
                    intFrom(data, "listingKeywordMatched"),
                    intFrom(data, "listingKeywordUnmatched"),
                    intFrom(data, "selectedP0"),
                    intFrom(data, "selectedP1"),
                    intFrom(data, "selectedP2"),
                    intFrom(data, "selectedP3"),
                    intFrom(data, "attempted"),
                    intFrom(data, "enqueued"),
                    intFrom(data, "skippedSeenUrl"),
                    intFrom(data, "skippedDedup"),
                    intFrom(data, "skippedEmpty"),
                    intFrom(data, "skippedSticky"),
                    intFrom(data, "skippedBlocked"),
                    intFrom(data, "skippedUnknown"),
                    intFrom(data, "failed"),
                    strFrom(data, "recordedAt")
            );
        } catch (JsonProcessingException e) {
            return new CrawlPipelineStatsResponse(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, "");
        }
    }

    private int intFrom(Map<String, Object> data, String key) {
        Object v = data.get(key);
        if (v == null) return 0;
        if (v instanceof Number n) return n.intValue();
        try { return Integer.parseInt(v.toString()); } catch (NumberFormatException e) { return 0; }
    }

    private String strFrom(Map<String, Object> data, String key) {
        Object v = data.get(key);
        return v == null ? "" : v.toString();
    }

    private String triggerPayload(String jobId, String correlationId, String requestedAt) {
        try {
            return objectMapper.writeValueAsString(Map.of(
                    "jobId", jobId,
                    "correlationId", correlationId,
                    "requestedAt", requestedAt
            ));
        } catch (JsonProcessingException e) {
            throw new IllegalStateException("Failed to serialize crawl trigger payload", e);
        }
    }

    private List<String> failedSites(Map<Object, Object> raw) {
        String json = value(raw, "failedSites");
        if (json.isBlank()) return List.of();
        try {
            return objectMapper.readerForListOf(String.class).readValue(json);
        } catch (JsonProcessingException e) {
            return List.of();
        }
    }

    private int intValue(Map<Object, Object> raw, String field) {
        String value = value(raw, field);
        if (value.isBlank()) return 0;
        try {
            return Integer.parseInt(value);
        } catch (NumberFormatException e) {
            return 0;
        }
    }

    private String value(Map<Object, Object> raw, String field) {
        Object value = raw.get(field);
        return value == null ? "" : value.toString();
    }

    private String key(String jobId) {
        return CRAWL_JOB_KEY_PREFIX + jobId;
    }
}
