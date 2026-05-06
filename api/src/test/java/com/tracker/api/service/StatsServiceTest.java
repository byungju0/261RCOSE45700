package com.tracker.api.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.tracker.api.dto.StatsResponse;
import com.tracker.api.repository.StatsRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.ValueOperations;
import java.time.Duration;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class StatsServiceTest {

    @Mock StatsRepository statsRepository;
    @Mock StringRedisTemplate cacheRedisTemplate;
    @Mock ValueOperations<String, String> valueOps;

    ObjectMapper objectMapper = new ObjectMapper();
    StatsService statsService;

    @BeforeEach
    void setUp() {
        statsService = new StatsService(statsRepository, objectMapper, cacheRedisTemplate);
    }

    @Test
    void getStats_cacheHit_returnsWithoutDbCall() throws Exception {
        StatsResponse expected = new StatsResponse(5L, 1L, List.of(), List.of(), List.of(), List.of());
        String cachedJson = objectMapper.writeValueAsString(expected);

        when(cacheRedisTemplate.opsForValue()).thenReturn(valueOps);
        when(valueOps.get("cache:detections:stats")).thenReturn(cachedJson);

        StatsResponse result = statsService.getStats(null);

        assertThat(result.todayCount()).isEqualTo(5L);
        assertThat(result.deltaFromYesterday()).isEqualTo(1L);
        verify(statsRepository, never()).countToday();
        verify(statsRepository, never()).countYesterday();
    }

    @Test
    void getStats_cacheMiss_queriesDbAndSetsCache() throws Exception {
        when(cacheRedisTemplate.opsForValue()).thenReturn(valueOps);
        when(valueOps.get("cache:detections:stats")).thenReturn(null);
        when(statsRepository.countToday()).thenReturn(10L);
        when(statsRepository.countYesterday()).thenReturn(8L);
        when(statsRepository.findTypeDistributionRaw()).thenReturn(List.of());
        when(statsRepository.findSiteDistributionRaw()).thenReturn(List.of());
        when(statsRepository.findLangDistributionRaw()).thenReturn(List.of());

        StatsResponse result = statsService.getStats(null);

        assertThat(result.todayCount()).isEqualTo(10L);
        assertThat(result.deltaFromYesterday()).isEqualTo(2L);
        verify(statsRepository).countToday();
        verify(valueOps).set(eq("cache:detections:stats"), any(String.class), eq(Duration.ofSeconds(60)));
    }

    @Test
    void getStats_redisFails_fallbackToDb() {
        when(cacheRedisTemplate.opsForValue()).thenThrow(new RuntimeException("Redis connection refused"));
        when(statsRepository.countToday()).thenReturn(3L);
        when(statsRepository.countYesterday()).thenReturn(2L);
        when(statsRepository.findTypeDistributionRaw()).thenReturn(List.of());
        when(statsRepository.findSiteDistributionRaw()).thenReturn(List.of());
        when(statsRepository.findLangDistributionRaw()).thenReturn(List.of());

        StatsResponse result = statsService.getStats(null);

        assertThat(result.todayCount()).isEqualTo(3L);
        assertThat(result.deltaFromYesterday()).isEqualTo(1L);
        verify(statsRepository).countToday();
    }
}
