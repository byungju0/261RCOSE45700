package com.tracker.api.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.data.redis.core.HashOperations;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.ValueOperations;
import java.time.Duration;
import java.util.Map;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.argThat;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class CrawlTriggerServiceTest {

    @Mock
    StringRedisTemplate stringRedisTemplate;

    @Mock
    HashOperations<String, Object, Object> hashOperations;

    @Mock
    ValueOperations<String, String> valueOperations;

    @Test
    void trigger_initializesJobAndPublishesJsonCommand() {
        when(stringRedisTemplate.opsForHash()).thenReturn(hashOperations);
        var service = new CrawlTriggerService(stringRedisTemplate, new ObjectMapper());

        String jobId = service.trigger("cid-1234");

        assertThat(jobId).isNotBlank();
        verify(hashOperations).putAll(eq("crawl:jobs:" + jobId), argThat(map ->
                jobId.equals(map.get("jobId"))
                        && "queued".equals(map.get("status"))
                        && "0".equals(map.get("percent"))));
        verify(stringRedisTemplate).expire("crawl:jobs:" + jobId, Duration.ofHours(6));
        verify(stringRedisTemplate).convertAndSend(eq("crawl:trigger"), argThat(payload ->
                payload.toString().contains("\"jobId\":\"" + jobId + "\"")
                        && payload.toString().contains("\"correlationId\":\"cid-1234\"")));
    }

    @Test
    void trigger_acceptsZeroSubscribersAsPublishCommandAccepted() {
        when(stringRedisTemplate.opsForHash()).thenReturn(hashOperations);
        when(stringRedisTemplate.convertAndSend(eq("crawl:trigger"), anyString())).thenReturn(0L);
        var service = new CrawlTriggerService(stringRedisTemplate, new ObjectMapper());

        service.trigger("cid-0000");

        verify(stringRedisTemplate).convertAndSend(eq("crawl:trigger"), anyString());
    }

    @Test
    void getStatus_readsJobHash() {
        when(stringRedisTemplate.opsForHash()).thenReturn(hashOperations);
        when(hashOperations.entries("crawl:jobs:job-1234")).thenReturn(Map.ofEntries(
                Map.entry("jobId", "job-1234"),
                Map.entry("status", "running"),
                Map.entry("totalSites", "8"),
                Map.entry("completedSites", "3"),
                Map.entry("percent", "38"),
                Map.entry("currentSite", "bahamut"),
                Map.entry("message", "bahamut 처리 중"),
                Map.entry("failedSites", "[\"tieba\"]"),
                Map.entry("requestedAt", "2026-05-28T00:00:00Z"),
                Map.entry("startedAt", "2026-05-28T00:00:01Z"),
                Map.entry("updatedAt", "2026-05-28T00:01:00Z"),
                Map.entry("finishedAt", "")
        ));
        var service = new CrawlTriggerService(stringRedisTemplate, new ObjectMapper());

        var status = service.getStatus("job-1234");

        assertThat(status.status()).isEqualTo("running");
        assertThat(status.totalSites()).isEqualTo(8);
        assertThat(status.completedSites()).isEqualTo(3);
        assertThat(status.percent()).isEqualTo(38);
        assertThat(status.failedSites()).containsExactly("tieba");
    }

    @Test
    void getLatestPipelineStats_readsStatsJson() {
        when(stringRedisTemplate.opsForValue()).thenReturn(valueOperations);
        when(valueOperations.get("crawl:stats:latest")).thenReturn("""
                {
                  "listingBoards": 41,
                  "listingDiscoveredTotal": 2136,
                  "listingUrlsSelected": 1140,
                  "listingKeywordMatched": 0,
                  "listingKeywordUnmatched": 2136,
                  "selectedP0": 0,
                  "selectedP1": 0,
                  "selectedP2": 48,
                  "selectedP3": 62,
                  "attempted": 95,
                  "enqueued": 76,
                  "skippedSeenUrl": 1,
                  "skippedDedup": 2,
                  "skippedEmpty": 5,
                  "skippedSticky": 1,
                  "skippedBlocked": 2,
                  "skippedUnknown": 2,
                  "failed": 0,
                  "recordedAt": "2026-06-07T02:48:36Z"
                }
                """);
        var service = new CrawlTriggerService(stringRedisTemplate, new ObjectMapper());

        var stats = service.getLatestPipelineStats();

        assertThat(stats.listingBoards()).isEqualTo(41);
        assertThat(stats.listingDiscoveredTotal()).isEqualTo(2136);
        assertThat(stats.listingUrlsSelected()).isEqualTo(1140);
        assertThat(stats.selectedP2()).isEqualTo(48);
        assertThat(stats.selectedP3()).isEqualTo(62);
        assertThat(stats.attempted()).isEqualTo(95);
        assertThat(stats.enqueued()).isEqualTo(76);
        assertThat(stats.recordedAt()).isEqualTo("2026-06-07T02:48:36Z");
    }

    @Test
    void getLatestPipelineStats_returnsZerosWhenMissing() {
        when(stringRedisTemplate.opsForValue()).thenReturn(valueOperations);
        when(valueOperations.get("crawl:stats:latest")).thenReturn(null);
        var service = new CrawlTriggerService(stringRedisTemplate, new ObjectMapper());

        var stats = service.getLatestPipelineStats();

        assertThat(stats.listingBoards()).isZero();
        assertThat(stats.enqueued()).isZero();
        assertThat(stats.recordedAt()).isEmpty();
    }
}
