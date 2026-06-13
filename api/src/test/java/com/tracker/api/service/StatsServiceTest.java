package com.tracker.api.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
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
    @Mock StringRedisTemplate mqRedisTemplate;
    @Mock StringRedisTemplate cacheRedisTemplate;
    @Mock ValueOperations<String, String> valueOps;

    ObjectMapper objectMapper = new ObjectMapper().registerModule(new JavaTimeModule());
    StatsService statsService;

    @BeforeEach
    void setUp() {
        statsService = new StatsService(statsRepository, objectMapper, mqRedisTemplate, cacheRedisTemplate);
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
        when(statsRepository.findSourceHealthRaw()).thenReturn(List.<Object[]>of(new Object[]{"52pojie", null}));
        when(mqRedisTemplate.keys("crawl:source_runs:*")).thenReturn(java.util.Set.of(
                "crawl:source_runs:52pojie",
                "crawl:source_runs:github"));
        when(mqRedisTemplate.opsForValue()).thenReturn(valueOps);
        when(valueOps.get("crawl:source_runs:52pojie")).thenReturn(
                "{\"siteName\":\"52pojie\",\"lastCheckedAt\":\"2026-06-13T11:53:14Z\","
                + "\"fetched\":5,\"queued\":0,\"validatorSkipped\":5,\"failed\":0}");
        when(valueOps.get("crawl:source_runs:github")).thenReturn(
                "{\"siteName\":\"github\",\"lastCheckedAt\":\"2026-06-13T11:54:00Z\","
                + "\"fetched\":12,\"queued\":6,\"validatorSkipped\":0,\"failed\":0}");

        StatsResponse result = statsService.getStats(null);

        assertThat(result.todayCount()).isEqualTo(10L);
        assertThat(result.deltaFromYesterday()).isEqualTo(2L);
        assertThat(result.typeDistribution().getFirst().type()).isEqualTo("매크로_판매");
        assertThat(result.siteDistribution().getFirst().site()).isEqualTo("tailstar.net");
        assertThat(result.langDistribution().getFirst().lang()).isEqualTo("zh-CN");
        assertThat(result.sourceHealth().getFirst().siteName()).isEqualTo("52pojie");
        assertThat(result.sourceHealth().getFirst().lastCrawledAt()).isEqualTo(Instant.parse("2026-06-13T11:53:14Z"));
        assertThat(result.sourceHealth().getFirst().lastIngestedAt()).isNull();
        assertThat(result.sourceHealth().getFirst().fetched()).isEqualTo(5);
        assertThat(result.sourceHealth().getFirst().queued()).isZero();
        assertThat(result.sourceHealth().getFirst().validatorSkipped()).isEqualTo(5);
        assertThat(result.sourceHealth()).extracting(StatsResponse.SourceHealthItem::siteName)
                .containsExactly("52pojie", "github");
        assertThat(result.sourceHealth().get(1).lastIngestedAt()).isNull();
        assertThat(result.sourceHealth().get(1).queued()).isEqualTo(6);
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
        when(statsRepository.findSourceHealthRaw()).thenReturn(List.of());

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
    void getStats_days_fillsZeroCountTrendDays() {
        LocalDate today = LocalDate.now(ZoneOffset.UTC);
        when(cacheRedisTemplate.opsForValue()).thenReturn(valueOps);
        when(valueOps.get("cache:detections:stats:days:14")).thenReturn(null);
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
        when(statsRepository.findSourceHealthRaw()).thenReturn(List.of());

        StatsResponse result = statsService.getStats(null, 14);

        assertThat(result.trend()).hasSize(14);
        assertThat(result.trend().getFirst().date()).isEqualTo(today.minusDays(13).toString());
        assertThat(result.trend().getFirst().count()).isZero();
        assertThat(result.trend().getLast().date()).isEqualTo(today.toString());
        assertThat(result.trend().getLast().count()).isEqualTo(5L);
        verify(statsRepository).findTypeDistributionRaw(
                eq(today.minusDays(13).atStartOfDay().toInstant(ZoneOffset.UTC)),
                eq(today.plusDays(1).atStartOfDay().toInstant(ZoneOffset.UTC)));
        verify(valueOps).set(eq("cache:detections:stats:days:14"), any(String.class), eq(Duration.ofSeconds(60)));
    }

    @Test
    void getStats_weeklyPeriodRemainsBackwardCompatible() {
        when(cacheRedisTemplate.opsForValue()).thenReturn(valueOps);
        when(valueOps.get("cache:detections:stats:days:7")).thenReturn(null);
        when(statsRepository.countToday(any(LocalDate.class))).thenReturn(5L);
        when(statsRepository.countYesterday(any(LocalDate.class))).thenReturn(4L);
        when(statsRepository.findTypeDistributionRaw(any(Instant.class), any(Instant.class)))
                .thenReturn(List.of());
        when(statsRepository.findSiteDistributionRaw(any(Instant.class), any(Instant.class)))
                .thenReturn(List.of());
        when(statsRepository.findLangDistributionRaw(any(Instant.class), any(Instant.class)))
                .thenReturn(List.of());
        when(statsRepository.findTrendRaw(any(Instant.class), any(Instant.class)))
                .thenReturn(List.of());
        when(statsRepository.findSourceHealthRaw()).thenReturn(List.of());

        StatsResponse result = statsService.getStats("weekly");

        assertThat(result.trend()).hasSize(7);
    }
}
