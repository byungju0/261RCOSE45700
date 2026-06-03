package com.tracker.api.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.tracker.api.dto.StatsResponse;
import com.tracker.api.exception.InvalidFilterParamException;
import com.tracker.api.repository.StatsRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.ValueOperations;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.List;

import static org.assertj.core.api.Assertions.assertThatThrownBy;
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
        StatsResponse expected = new StatsResponse(5L, 1L, List.of(), List.of(), List.of(), List.of(), List.of());
        String cachedJson = objectMapper.writeValueAsString(expected);

        when(cacheRedisTemplate.opsForValue()).thenReturn(valueOps);
        when(valueOps.get("cache:detections:stats")).thenReturn(cachedJson);

        StatsResponse result = statsService.getStats(null);

        assertThat(result.todayCount()).isEqualTo(5L);
        assertThat(result.deltaFromYesterday()).isEqualTo(1L);
        verify(statsRepository, never()).countToday(any(LocalDate.class));
        verify(statsRepository, never()).countYesterday(any(LocalDate.class));
    }

    @Test
    void getStats_cacheMiss_queriesDbAndSetsCache() throws Exception {
        when(cacheRedisTemplate.opsForValue()).thenReturn(valueOps);
        when(valueOps.get("cache:detections:stats")).thenReturn(null);
        when(statsRepository.countToday(any(LocalDate.class))).thenReturn(10L);
        when(statsRepository.countYesterday(any(LocalDate.class))).thenReturn(8L);
        when(statsRepository.findTypeDistributionRaw()).thenReturn(List.<Object[]>of(new Object[]{"매크로_판매", 4L}));
        when(statsRepository.findSiteDistributionRaw()).thenReturn(List.<Object[]>of(new Object[]{"tailstar.net", 3L}));
        when(statsRepository.findLangDistributionRaw()).thenReturn(List.<Object[]>of(new Object[]{"zh-CN", 2L}));

        StatsResponse result = statsService.getStats(null);

        assertThat(result.todayCount()).isEqualTo(10L);
        assertThat(result.deltaFromYesterday()).isEqualTo(2L);
        assertThat(result.typeDistribution().getFirst().type()).isEqualTo("매크로_판매");
        assertThat(result.siteDistribution().getFirst().site()).isEqualTo("tailstar.net");
        assertThat(result.langDistribution().getFirst().lang()).isEqualTo("zh-CN");
        verify(statsRepository).countToday(any(LocalDate.class));
        verify(valueOps).set(eq("cache:detections:stats"), any(String.class), eq(Duration.ofSeconds(60)));
    }

    @Test
    void getStats_redisFails_fallbackToDb() {
        when(cacheRedisTemplate.opsForValue()).thenThrow(new RuntimeException("Redis connection refused"));
        when(statsRepository.countToday(any(LocalDate.class))).thenReturn(3L);
        when(statsRepository.countYesterday(any(LocalDate.class))).thenReturn(2L);
        when(statsRepository.findTypeDistributionRaw()).thenReturn(List.of());
        when(statsRepository.findSiteDistributionRaw()).thenReturn(List.of());
        when(statsRepository.findLangDistributionRaw()).thenReturn(List.of());

        StatsResponse result = statsService.getStats(null);

        assertThat(result.todayCount()).isEqualTo(3L);
        assertThat(result.deltaFromYesterday()).isEqualTo(1L);
        verify(statsRepository).countToday(any(LocalDate.class));
    }

    @Test
    void getStats_withInvalidPeriod_rejectsBeforeCacheAccess() {
        assertThatThrownBy(() -> statsService.getStats("daily"))
                .isInstanceOf(InvalidFilterParamException.class);

        verifyNoInteractions(cacheRedisTemplate);
        verifyNoInteractions(statsRepository);
    }

    @Test
    void getStats_weekly_fillsZeroCountTrendDays() {
        LocalDate today = LocalDate.now(ZoneOffset.UTC);
        when(cacheRedisTemplate.opsForValue()).thenReturn(valueOps);
        when(valueOps.get("cache:detections:stats:weekly")).thenReturn(null);
        when(statsRepository.countToday(any(LocalDate.class))).thenReturn(5L);
        when(statsRepository.countYesterday(any(LocalDate.class))).thenReturn(4L);
        when(statsRepository.findTypeDistributionRaw(any(Instant.class), any(Instant.class)))
                .thenReturn(List.of());
        when(statsRepository.findSiteDistributionRaw(any(Instant.class), any(Instant.class)))
                .thenReturn(List.of());
        when(statsRepository.findLangDistributionRaw(any(Instant.class), any(Instant.class)))
                .thenReturn(List.of());
        when(statsRepository.findTrendRaw(any(Instant.class), any(Instant.class)))
                .thenReturn(List.<Object[]>of(new Object[]{today, 5L}));

        StatsResponse result = statsService.getStats("weekly");

        assertThat(result.trend()).hasSize(7);
        assertThat(result.trend().getFirst().date()).isEqualTo(today.minusDays(6).toString());
        assertThat(result.trend().getFirst().count()).isZero();
        assertThat(result.trend().getLast().date()).isEqualTo(today.toString());
        assertThat(result.trend().getLast().count()).isEqualTo(5L);
        verify(statsRepository).findTypeDistributionRaw(
                eq(today.minusDays(6).atStartOfDay().toInstant(ZoneOffset.UTC)),
                eq(today.plusDays(1).atStartOfDay().toInstant(ZoneOffset.UTC)));
        verify(valueOps).set(eq("cache:detections:stats:weekly"), any(String.class), eq(Duration.ofSeconds(60)));
    }
}
