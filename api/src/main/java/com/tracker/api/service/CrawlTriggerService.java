package com.tracker.api.service;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.tracker.api.dto.CrawlJobStatusResponse;
import com.tracker.api.dto.CrawlPipelineStatsResponse;
import com.tracker.api.exception.CrawlJobNotFoundException;
import com.tracker.api.exception.CrawlTriggerUnavailableException;
import com.tracker.api.util.RedisFieldExtractor;
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

        Long subscribers = stringRedisTemplate.convertAndSend(
                CRAWL_TRIGGER_CHANNEL,
                triggerPayload(jobId, correlationId, requestedAt));
        if (subscribers == null || subscribers == 0L) {
            String finishedAt = Instant.now().toString();
            stringRedisTemplate.opsForHash().putAll(key, Map.ofEntries(
                    Map.entry("status", "skipped"),
                    Map.entry("message", "크롤러 트리거 리스너가 응답하지 않습니다."),
                    Map.entry("updatedAt", finishedAt),
                    Map.entry("finishedAt", finishedAt)
            ));
            stringRedisTemplate.expire(key, CRAWL_JOB_TTL);
            throw new CrawlTriggerUnavailableException(jobId);
        }

        return jobId;
    }

    public CrawlJobStatusResponse getStatus(String jobId) {
        Map<Object, Object> raw = stringRedisTemplate.opsForHash().entries(key(jobId));
        if (raw.isEmpty()) {
            throw new CrawlJobNotFoundException(jobId);
        }

        return new CrawlJobStatusResponse(
                RedisFieldExtractor.str(raw, "jobId"),
                RedisFieldExtractor.str(raw, "status"),
                RedisFieldExtractor.intValue(raw, "totalSites"),
                RedisFieldExtractor.intValue(raw, "completedSites"),
                RedisFieldExtractor.intValue(raw, "percent"),
                RedisFieldExtractor.str(raw, "currentSite"),
                RedisFieldExtractor.str(raw, "message"),
                failedSites(raw),
                RedisFieldExtractor.str(raw, "requestedAt"),
                RedisFieldExtractor.str(raw, "startedAt"),
                RedisFieldExtractor.str(raw, "updatedAt"),
                RedisFieldExtractor.str(raw, "finishedAt")
        );
    }

    public CrawlPipelineStatsResponse getLatestPipelineStats() {
        String json = stringRedisTemplate.opsForValue().get(CRAWL_STATS_LATEST_KEY);
        if (json == null || json.isBlank()) {
            return CrawlPipelineStatsResponse.empty();
        }
        try {
            @SuppressWarnings("unchecked")
            Map<String, Object> data = objectMapper.readValue(json, Map.class);
            return new CrawlPipelineStatsResponse(
                    RedisFieldExtractor.intValue(data, "listingBoards"),
                    RedisFieldExtractor.intValue(data, "listingDiscoveredTotal"),
                    RedisFieldExtractor.intValue(data, "listingUrlsSelected"),
                    RedisFieldExtractor.intValue(data, "listingKeywordMatched"),
                    RedisFieldExtractor.intValue(data, "listingKeywordUnmatched"),
                    RedisFieldExtractor.intValue(data, "selectedP0"),
                    RedisFieldExtractor.intValue(data, "selectedP1"),
                    RedisFieldExtractor.intValue(data, "selectedP2"),
                    RedisFieldExtractor.intValue(data, "selectedP3"),
                    RedisFieldExtractor.intValue(data, "attempted"),
                    RedisFieldExtractor.intValue(data, "enqueued"),
                    RedisFieldExtractor.intValue(data, "skippedSeenUrl"),
                    RedisFieldExtractor.intValue(data, "skippedDedup"),
                    RedisFieldExtractor.intValue(data, "skippedEmpty"),
                    RedisFieldExtractor.intValue(data, "skippedSticky"),
                    RedisFieldExtractor.intValue(data, "skippedBlocked"),
                    RedisFieldExtractor.intValue(data, "skippedUnknown"),
                    RedisFieldExtractor.intValue(data, "failed"),
                    RedisFieldExtractor.str(data, "recordedAt")
            );
        } catch (JsonProcessingException e) {
            return CrawlPipelineStatsResponse.empty();
        }
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
        String json = RedisFieldExtractor.str(raw, "failedSites");
        if (json.isBlank()) return List.of();
        try {
            return objectMapper.readerForListOf(String.class).readValue(json);
        } catch (JsonProcessingException e) {
            return List.of();
        }
    }

    private String key(String jobId) {
        return CRAWL_JOB_KEY_PREFIX + jobId;
    }
}
