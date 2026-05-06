package com.tracker.api.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.tracker.api.dto.StatsResponse;
import com.tracker.api.repository.StatsRepository;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.List;

@Slf4j
@Service
public class StatsService {

    private final StatsRepository statsRepository;
    private final ObjectMapper objectMapper;
    private final StringRedisTemplate cacheRedisTemplate;

    public StatsService(StatsRepository statsRepository,
                        ObjectMapper objectMapper,
                        @Qualifier("cacheRedisTemplate") StringRedisTemplate cacheRedisTemplate) {
        this.statsRepository = statsRepository;
        this.objectMapper = objectMapper;
        this.cacheRedisTemplate = cacheRedisTemplate;
    }

    public StatsResponse getStats(String period) {
        String cacheKey = buildCacheKey(period);

        try {
            String cached = cacheRedisTemplate.opsForValue().get(cacheKey);
            if (cached != null) {
                return objectMapper.readValue(cached, StatsResponse.class);
            }
        } catch (Exception e) {
            log.warn("Redis cache read failed for key '{}': {}", cacheKey, e.getMessage());
        }

        StatsResponse response = buildStats(period);

        try {
            String json = objectMapper.writeValueAsString(response);
            cacheRedisTemplate.opsForValue().set(cacheKey, json, Duration.ofSeconds(60));
        } catch (Exception e) {
            log.warn("Redis cache write failed for key '{}': {}", cacheKey, e.getMessage());
        }

        return response;
    }

    @Transactional(readOnly = true)
    StatsResponse buildStats(String period) {
        long todayCount = statsRepository.countToday();
        long yesterdayCount = statsRepository.countYesterday();
        long delta = todayCount - yesterdayCount;

        var typeDistribution = statsRepository.findTypeDistributionRaw().stream()
                .filter(row -> row[0] != null)
                .map(row -> new StatsResponse.DistributionItem((String) row[0], ((Number) row[1]).longValue()))
                .toList();

        var siteDistribution = statsRepository.findSiteDistributionRaw().stream()
                .filter(row -> row[0] != null)
                .map(row -> new StatsResponse.DistributionItem((String) row[0], ((Number) row[1]).longValue()))
                .toList();

        var langDistribution = statsRepository.findLangDistributionRaw().stream()
                .filter(row -> row[0] != null)
                .map(row -> new StatsResponse.DistributionItem((String) row[0], ((Number) row[1]).longValue()))
                .toList();

        List<StatsResponse.TrendItem> trend = buildTrend(period);

        return new StatsResponse(todayCount, delta, typeDistribution, siteDistribution, langDistribution, trend);
    }

    private List<StatsResponse.TrendItem> buildTrend(String period) {
        if ("weekly".equals(period)) {
            Instant to = LocalDate.now(ZoneOffset.UTC).plusDays(1).atStartOfDay().toInstant(ZoneOffset.UTC);
            Instant from = LocalDate.now(ZoneOffset.UTC).minusDays(6).atStartOfDay().toInstant(ZoneOffset.UTC);
            return toTrendItems(statsRepository.findTrendRaw(from, to));
        } else if ("monthly".equals(period)) {
            Instant to = LocalDate.now(ZoneOffset.UTC).plusDays(1).atStartOfDay().toInstant(ZoneOffset.UTC);
            Instant from = LocalDate.now(ZoneOffset.UTC).minusDays(29).atStartOfDay().toInstant(ZoneOffset.UTC);
            return toTrendItems(statsRepository.findTrendRaw(from, to));
        }
        return List.of();
    }

    private List<StatsResponse.TrendItem> toTrendItems(List<Object[]> rows) {
        return rows.stream()
                .map(row -> new StatsResponse.TrendItem(row[0].toString(), ((Number) row[1]).longValue()))
                .toList();
    }

    private String buildCacheKey(String period) {
        if (period != null && !period.isBlank()) {
            return "cache:detections:stats:" + period;
        }
        return "cache:detections:stats";
    }
}
