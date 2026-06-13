package com.tracker.api.dto;

public record CrawlTriggerResponse(
        String jobId,
        String status,
        String statusUrl
) {}
