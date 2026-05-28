package com.tracker.api.exception;

public class CrawlJobNotFoundException extends RuntimeException {

    public CrawlJobNotFoundException(String jobId) {
        super("Crawl job not found: " + jobId);
    }
}
