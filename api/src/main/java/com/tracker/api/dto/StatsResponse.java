package com.tracker.api.dto;

import java.time.Instant;
import java.util.List;

public record StatsResponse(
        long todayCount,
        long deltaFromYesterday,
        List<TypeDistributionItem> typeDistribution,
        List<SiteDistributionItem> siteDistribution,
        List<LangDistributionItem> langDistribution,
        List<TrendItem> trend,
        List<SourceHealthItem> sourceHealth
) {
    public record TypeDistributionItem(String type, long count) {}
    public record SiteDistributionItem(String site, long count) {}
    public record LangDistributionItem(String lang, long count) {}
    public record TrendItem(String date, long count) {}
    public record SourceHealthItem(
            String siteName,
            Instant lastCrawledAt,
            Instant lastIngestedAt,
            long fetched,
            long queued,
            long validatorSkipped,
            long failed
    ) {}
}
