package com.tracker.api.dto;

public record CrawlTriggerResponse(
        String jobId,
        String status,
        int estimatedMinutes,
        String statusUrl
) {}
