package com.tracker.api.dto;

import java.util.List;

public record CrawlJobStatusResponse(
        String jobId,
        String status,
        int totalSites,
        int completedSites,
        int percent,
        String currentSite,
        String message,
        List<String> failedSites,
        String requestedAt,
        String startedAt,
        String updatedAt,
        String finishedAt
) {}
