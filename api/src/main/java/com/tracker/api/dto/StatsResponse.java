package com.tracker.api.dto;

import java.util.List;

public record StatsResponse(
        long todayCount,
        long deltaFromYesterday,
        List<DistributionItem> typeDistribution,
        List<DistributionItem> siteDistribution,
        List<DistributionItem> langDistribution,
        List<TrendItem> trend
) {
    public record DistributionItem(String label, long count) {}
    public record TrendItem(String date, long count) {}
}
