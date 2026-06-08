package com.tracker.api.dto;

public record CrawlPipelineStatsResponse(
        int listingBoards,
        int listingDiscoveredTotal,
        int listingUrlsSelected,
        int listingKeywordMatched,
        int listingKeywordUnmatched,
        int selectedP0,
        int selectedP1,
        int selectedP2,
        int selectedP3,
        int attempted,
        int enqueued,
        int skippedSeenUrl,
        int skippedDedup,
        int skippedEmpty,
        int skippedSticky,
        int skippedBlocked,
        int skippedUnknown,
        int failed,
        String recordedAt
) {}
