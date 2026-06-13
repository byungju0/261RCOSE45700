package com.tracker.api.service;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.tracker.api.dto.StatsResponse;
import com.tracker.api.exception.InvalidFilterParamException;
import com.tracker.api.repository.StatsRepository;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.IntStream;

@Slf4j
@Service
public class StatsService {

    private static final int MIN_PERIOD_DAYS = 1;
    private static final int MAX_PERIOD_DAYS = 365;
    private static final String CRAWL_SOURCE_RUN_PREFIX = "crawl:source_runs:";

    private final StatsRepository statsRepository;
    private final ObjectMapper objectMapper;
    private final StringRedisTemplate mqRedisTemplate;
    private final StringRedisTemplate cacheRedisTemplate;

    public StatsService(StatsRepository statsRepository,
                        ObjectMapper objectMapper,
                        StringRedisTemplate mqRedisTemplate,
                        @Qualifier("cacheRedisTemplate") StringRedisTemplate cacheRedisTemplate) {
        this.statsRepository = statsRepository;
        this.objectMapper = objectMapper;
        this.mqRedisTemplate = mqRedisTemplate;
        this.cacheRedisTemplate = cacheRedisTemplate;
    }

    @Transactional(readOnly = true)
    public StatsResponse getStats(String period) {
        return getStats(period, null);
    }

    @Transactional(readOnly = true)
    public StatsResponse getStats(String period, Integer days) {
        Integer normalizedDays = normalizeDays(period, days);
        String cacheKey = buildCacheKey(normalizedDays);

        try {
            String cached = cacheRedisTemplate.opsForValue().get(cacheKey);
            if (cached != null) {
                return objectMapper.readValue(cached, StatsResponse.class);
            }
        } catch (Exception e) {
            log.warn("Redis cache read failed for key '{}': {}", cacheKey, e.getMessage());
        }

        StatsResponse response = buildStats(normalizedDays, LocalDate.now(ZoneOffset.UTC));

        try {
            String json = objectMapper.writeValueAsString(response);
            cacheRedisTemplate.opsForValue().set(cacheKey, json, Duration.ofSeconds(60));
        } catch (Exception e) {
            log.warn("Redis cache write failed for key '{}': {}", cacheKey, e.getMessage());
        }

        return response;
    }

    StatsResponse buildStats(Integer days, LocalDate today) {
        long todayCount = statsRepository.countToday(today);
        long yesterdayCount = statsRepository.countYesterday(today);
        long delta = todayCount - yesterdayCount;
        TimeRange periodRange = resolvePeriodRange(days, today);

        var typeDistributionRows = periodRange == null
                ? statsRepository.findTypeDistributionRaw()
                : statsRepository.findTypeDistributionRaw(periodRange.from(), periodRange.to());
        var typeDistribution = typeDistributionRows.stream()
                .filter(row -> row[0] != null)
                .map(row -> new StatsResponse.TypeDistributionItem((String) row[0], ((Number) row[1]).longValue()))
                .toList();

        var siteDistributionRows = periodRange == null
                ? statsRepository.findSiteDistributionRaw()
                : statsRepository.findSiteDistributionRaw(periodRange.from(), periodRange.to());
        var siteDistribution = siteDistributionRows.stream()
                .filter(row -> row[0] != null)
                .map(row -> new StatsResponse.SiteDistributionItem((String) row[0], ((Number) row[1]).longValue()))
                .toList();

        var langDistributionRows = periodRange == null
                ? statsRepository.findLangDistributionRaw()
                : statsRepository.findLangDistributionRaw(periodRange.from(), periodRange.to());
        var langDistribution = langDistributionRows.stream()
                .filter(row -> row[0] != null)
                .map(row -> new StatsResponse.LangDistributionItem((String) row[0], ((Number) row[1]).longValue()))
                .toList();

        List<StatsResponse.TrendItem> trend = buildTrend(days, today);

        Map<String, SourceRunSummary> sourceRuns = loadSourceRuns();
        Map<String, Instant> lastIngestedBySite = new TreeMap<>();
        statsRepository.findSourceHealthRaw().forEach(row ->
                lastIngestedBySite.put((String) row[0], toInstant(row[1])));
        sourceRuns.keySet().forEach(siteName -> lastIngestedBySite.putIfAbsent(siteName, null));
        var sourceHealth = lastIngestedBySite.entrySet().stream()
                .map(entry -> {
                    SourceRunSummary run = sourceRuns.get(entry.getKey());
                    return new StatsResponse.SourceHealthItem(
                            entry.getKey(),
                            run == null ? null : run.lastCheckedAt(),
                            entry.getValue(),
                            run == null ? 0 : run.fetched(),
                            run == null ? 0 : run.queued(),
                            run == null ? 0 : run.validatorSkipped(),
                            run == null ? 0 : run.failed());
                })
                .toList();

        return new StatsResponse(todayCount, delta, typeDistribution, siteDistribution, langDistribution, trend, sourceHealth);
    }

    private List<StatsResponse.TrendItem> buildTrend(Integer days, LocalDate today) {
        if (days == null) return List.of();

        TimeRange range = resolvePeriodRange(days, today);
        return toTrendItems(statsRepository.findTrendRaw(range.from(), range.to()), today.minusDays(days - 1L), days);
    }

    private TimeRange resolvePeriodRange(Integer days, LocalDate today) {
        if (days == null) return null;
        return new TimeRange(
                today.minusDays(days - 1L).atStartOfDay().toInstant(ZoneOffset.UTC),
                today.plusDays(1).atStartOfDay().toInstant(ZoneOffset.UTC));
    }

    private List<StatsResponse.TrendItem> toTrendItems(List<Object[]> rows, LocalDate fromDate, int days) {
        Map<String, Long> countsByDate = new HashMap<>();
        for (Object[] row : rows) {
            if (row[0] != null) {
                countsByDate.put(row[0].toString(), ((Number) row[1]).longValue());
            }
        }

        return IntStream.range(0, days)
                .mapToObj(offset -> {
                    String date = fromDate.plusDays(offset).toString();
                    return new StatsResponse.TrendItem(date, countsByDate.getOrDefault(date, 0L));
                })
                .toList();
    }

    private String buildCacheKey(Integer days) {
        return "cache:detections:stats" + (days != null ? ":days:" + days : "");
    }

    private Map<String, SourceRunSummary> loadSourceRuns() {
        Map<String, SourceRunSummary> runs = new HashMap<>();
        try {
            var keys = mqRedisTemplate.keys(CRAWL_SOURCE_RUN_PREFIX + "*");
            if (keys == null) return runs;
            for (String key : keys) {
                String json = mqRedisTemplate.opsForValue().get(key);
                if (json == null || json.isBlank()) continue;
                Map<String, Object> raw = objectMapper.readValue(json, new TypeReference<>() {});
                String siteName = strFrom(raw, "siteName");
                if (siteName.isBlank()) {
                    siteName = key.substring(CRAWL_SOURCE_RUN_PREFIX.length());
                }
                runs.put(siteName, new SourceRunSummary(
                        toInstant(strFrom(raw, "lastCheckedAt")),
                        longFrom(raw, "fetched"),
                        longFrom(raw, "queued"),
                        longFrom(raw, "validatorSkipped"),
                        longFrom(raw, "failed")));
            }
        } catch (Exception e) {
            log.warn("Redis source run read failed: {}", e.getMessage());
        }
        return runs;
    }

    private static Instant toInstant(Object value) {
        if (value == null) return null;
        if (value instanceof String s) return s.isBlank() ? null : Instant.parse(s);
        if (value instanceof OffsetDateTime odt) return odt.toInstant();
        if (value instanceof LocalDateTime ldt) return ldt.toInstant(ZoneOffset.UTC);
        if (value instanceof java.sql.Timestamp ts) return ts.toInstant();
        if (value instanceof Instant i) return i;
        throw new IllegalStateException("Unexpected timestamp type: " + value.getClass());
    }

    private Integer normalizeDays(String period, Integer days) {
        if (days != null) {
            return validateDays(days);
        }
        if (period == null || period.isBlank()) {
            return null;
        }

        String normalized = period.trim();
        if ("weekly".equals(normalized)) return 7;
        if ("monthly".equals(normalized)) return 30;

        throw new InvalidFilterParamException("days는 1~365 사이 숫자만 허용됩니다.");
    }

    private Integer validateDays(int days) {
        if (days >= MIN_PERIOD_DAYS && days <= MAX_PERIOD_DAYS) {
            return days;
        }
        throw new InvalidFilterParamException("days는 1~365 사이 숫자만 허용됩니다.");
    }

    private long longFrom(Map<String, Object> data, String key) {
        Object v = data.get(key);
        if (v == null) return 0;
        if (v instanceof Number n) return n.longValue();
        try {
            return Long.parseLong(v.toString());
        } catch (NumberFormatException e) {
            return 0;
        }
    }

    private String strFrom(Map<String, Object> data, String key) {
        Object v = data.get(key);
        return v == null ? "" : v.toString();
    }

    private record TimeRange(Instant from, Instant to) {}
    private record SourceRunSummary(
            Instant lastCheckedAt,
            long fetched,
            long queued,
            long validatorSkipped,
            long failed
    ) {}
}
