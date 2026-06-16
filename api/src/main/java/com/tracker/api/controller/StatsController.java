package com.tracker.api.controller;

import com.tracker.api.dto.StatsResponse;
import com.tracker.api.service.StatsService;
import com.tracker.api.util.CorrelationIdUtil;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.servlet.http.HttpServletRequest;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
@RequiredArgsConstructor
@Tag(name = "Stats", description = "탐지 통계 조회")
public class StatsController {

    private final StatsService statsService;

    @GetMapping("/stats")
    @Operation(summary = "탐지 통계 조회",
               description = "오늘 탐지 현황 및 유형/사이트/언어별 분포. days=1~365 로 최근 N일 추이 포함.")
    public ResponseEntity<StatsResponse> getStats(
            @RequestParam(required = false) String period,
            @RequestParam(required = false) Integer days,
            HttpServletRequest request) {

        StatsResponse stats = statsService.getStats(period, days);
        return ResponseEntity.ok()
                .header("X-Correlation-ID", CorrelationIdUtil.resolve(request))
                .body(stats);
    }
}
