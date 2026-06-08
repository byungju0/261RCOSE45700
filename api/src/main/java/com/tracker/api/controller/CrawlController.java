package com.tracker.api.controller;

import com.tracker.api.dto.CrawlTriggerResponse;
import com.tracker.api.dto.CrawlJobStatusResponse;
import com.tracker.api.dto.CrawlPipelineStatsResponse;
import com.tracker.api.service.CrawlTriggerService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.servlet.http.HttpServletRequest;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import java.util.UUID;

@RestController
@RequestMapping("/api")
@RequiredArgsConstructor
@Tag(name = "Crawl", description = "수동 크롤링 트리거")
public class CrawlController {

    private final CrawlTriggerService crawlTriggerService;

    @PostMapping("/crawl/trigger")
    @Operation(summary = "수동 크롤링 트리거", description = "Redis crawl:trigger 채널에 PUBLISH하고 jobId를 반환. 완료까지 약 3분 소요.")
    public ResponseEntity<CrawlTriggerResponse> trigger(HttpServletRequest request) {

        String raw = request.getHeader("X-Correlation-ID");
        String correlationId = (raw != null && !raw.isBlank()) ? raw : UUID.randomUUID().toString();

        String jobId = crawlTriggerService.trigger(correlationId);

        return ResponseEntity.accepted()
                .header("X-Correlation-ID", correlationId)
                .body(new CrawlTriggerResponse(jobId, "triggered", 3, "/api/crawl/jobs/" + jobId));
    }

    @GetMapping("/crawl/jobs/{jobId}")
    @Operation(summary = "수동 크롤링 진행 상태 조회", description = "Redis에 저장된 수동 크롤링 job 진행률을 반환.")
    public ResponseEntity<CrawlJobStatusResponse> getJobStatus(@PathVariable String jobId) {
        return ResponseEntity.ok(crawlTriggerService.getStatus(jobId));
    }

    @GetMapping("/crawl/stats")
    @Operation(summary = "최근 파이프라인 funnel 통계 조회", description = "마지막 크롤링 run 의 listing/validator/dedup 단계별 통계를 반환.")
    public ResponseEntity<CrawlPipelineStatsResponse> getPipelineStats() {
        return ResponseEntity.ok(crawlTriggerService.getLatestPipelineStats());
    }
}
