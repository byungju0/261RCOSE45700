package com.tracker.api.controller;

import com.tracker.api.dto.DetectionListResponse;
import com.tracker.api.dto.DetectionResponse;
import com.tracker.api.exception.DetectionNotFoundException;
import com.tracker.api.dto.CrawlJobStatusResponse;
import com.tracker.api.dto.CrawlPipelineStatsResponse;
import com.tracker.api.service.CrawlTriggerService;
import com.tracker.api.service.DetectionService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import java.time.LocalDate;
import java.util.List;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@WebMvcTest({ DetectionController.class, CrawlController.class })
class DetectionControllerTest {

        @Autowired
        MockMvc mockMvc;
        @MockitoBean
        DetectionService detectionService;
        @MockitoBean
        CrawlTriggerService crawlTriggerService;

        @Test
        void getDetections_returnsOk() throws Exception {
                var mockDetection = new DetectionResponse(1L, true, "매크로_판매", "T2", 0.95,
                                "이유", "원문", null, "http://example.com", "tailstar.net", "zh-CN",
                                "2026-04-24T14:30:00Z");
                when(detectionService.getDetections(any(), any(), any(), any(), any(), eq(0), eq(20)))
                                .thenReturn(new DetectionListResponse(List.of(mockDetection), 0, 20, 1L));

                mockMvc.perform(get("/api/detections"))
                                .andExpect(status().isOk())
                                .andExpect(jsonPath("$.content").isArray())
                                .andExpect(jsonPath("$.totalElements").value(1))
                                .andExpect(jsonPath("$.content[0].isIllegal").value(true))
                                .andExpect(jsonPath("$.content[0].tier").value("T2"))
                                .andExpect(jsonPath("$.content[0].detectedAt").value("2026-04-24T14:30:00Z"))
                                .andExpect(header().exists("X-Correlation-ID"));
        }

        @Test
        void getDetections_emptyResult_returns200() throws Exception {
                when(detectionService.getDetections(any(), any(), any(), any(), any(), eq(0), eq(20)))
                                .thenReturn(new DetectionListResponse(List.of(), 0, 20, 0L));

                mockMvc.perform(get("/api/detections"))
                                .andExpect(status().isOk())
                                .andExpect(jsonPath("$.content").isEmpty())
                                .andExpect(jsonPath("$.totalElements").value(0));
        }

        @Test
        void getDetections_invalidDateFormat_returns400ProblemDetail() throws Exception {
                mockMvc.perform(get("/api/detections").param("date", "not-a-date"))
                                .andExpect(status().isBadRequest())
                                .andExpect(jsonPath("$.errorCode").value("INVALID_FILTER_PARAM"))
                                .andExpect(jsonPath("$.status").value(400));
        }

        @Test
        void getDetections_invalidPage_returns400ProblemDetail() throws Exception {
                mockMvc.perform(get("/api/detections").param("page", "-1"))
                                .andExpect(status().isBadRequest())
                                .andExpect(jsonPath("$.errorCode").value("INVALID_FILTER_PARAM"))
                                .andExpect(jsonPath("$.status").value(400));
        }

        @Test
        void getDetections_passesFilterParametersToService() throws Exception {
                when(detectionService.getDetections(
                                eq(LocalDate.of(2026, 4, 24)),
                                eq(null),
                                eq("tailstar.net"),
                                eq("매크로_판매"),
                                eq("ko"),
                                eq(1),
                                eq(10)))
                                .thenReturn(new DetectionListResponse(List.of(), 1, 10, 0L));

                mockMvc.perform(get("/api/detections")
                                .param("date", "2026-04-24")
                                .param("site", "tailstar.net")
                                .param("type", "매크로_판매")
                                .param("lang", "ko")
                                .param("page", "1")
                                .param("size", "10"))
                                .andExpect(status().isOk());

                verify(detectionService).getDetections(
                                LocalDate.of(2026, 4, 24),
                                null,
                                "tailstar.net",
                                "매크로_판매",
                                "ko",
                                1,
                                10);
        }

        @Test
        void getDetections_passesRangeParameterToService() throws Exception {
                when(detectionService.getDetections(
                                eq(null),
                                eq("7d"),
                                eq(null),
                                eq(null),
                                eq(null),
                                eq(0),
                                eq(20)))
                                .thenReturn(new DetectionListResponse(List.of(), 0, 20, 0L));

                mockMvc.perform(get("/api/detections").param("range", "7d"))
                                .andExpect(status().isOk());

                verify(detectionService).getDetections(null, "7d", null, null, null, 0, 20);
        }

        @Test
        void getDetection_returnsOk() throws Exception {
                var mockDetection = new DetectionResponse(1L, true, "매크로_판매", "T2", 0.95,
                                "이유", "원문", "번역문", "http://example.com", "tailstar.net", "zh-CN",
                                "2026-04-24T14:30:00Z");
                when(detectionService.getDetectionById(1L)).thenReturn(mockDetection);

                mockMvc.perform(get("/api/detections/1"))
                                .andExpect(status().isOk())
                                .andExpect(jsonPath("$.id").value(1))
                                .andExpect(jsonPath("$.isIllegal").value(true))
                                .andExpect(jsonPath("$.type").value("매크로_판매"))
                                .andExpect(jsonPath("$.tier").value("T2"))
                                .andExpect(jsonPath("$.confidence").value(0.95))
                                .andExpect(jsonPath("$.reason").value("이유"))
                                .andExpect(jsonPath("$.rawText").value("원문"))
                                .andExpect(jsonPath("$.translatedText").value("번역문"))
                                .andExpect(jsonPath("$.postUrl").value("http://example.com"))
                                .andExpect(jsonPath("$.siteName").value("tailstar.net"))
                                .andExpect(jsonPath("$.language").value("zh-CN"))
                                .andExpect(jsonPath("$.detectedAt").value("2026-04-24T14:30:00Z"))
                                .andExpect(header().exists("X-Correlation-ID"));
        }

        @Test
        void getDetection_notFound_returns404() throws Exception {
                when(detectionService.getDetectionById(999L))
                                .thenThrow(new DetectionNotFoundException(999L));

                mockMvc.perform(get("/api/detections/999")
                                .header("X-Correlation-ID", "not-found-cid"))
                                .andExpect(status().isNotFound())
                                .andExpect(jsonPath("$.errorCode").value("DETECTION_NOT_FOUND"))
                                .andExpect(jsonPath("$.status").value(404))
                                .andExpect(header().string("X-Correlation-ID", "not-found-cid"));
        }

        @Test
        void postCrawlTrigger_returns202() throws Exception {
                when(crawlTriggerService.trigger("test-cid-1234")).thenReturn("job-1234");

                mockMvc.perform(post("/api/crawl/trigger")
                                .header("X-Correlation-ID", "test-cid-1234"))
                                .andExpect(status().isAccepted())
                                .andExpect(jsonPath("$.jobId").value("job-1234"))
                                .andExpect(jsonPath("$.status").value("triggered"))
                                .andExpect(jsonPath("$.estimatedMinutes").value(3))
                                .andExpect(jsonPath("$.statusUrl").value("/api/crawl/jobs/job-1234"))
                                .andExpect(header().string("X-Correlation-ID", "test-cid-1234"));

                verify(crawlTriggerService).trigger("test-cid-1234");
        }

        @Test
        void getCrawlJobStatus_returnsOk() throws Exception {
                when(crawlTriggerService.getStatus("job-1234")).thenReturn(new CrawlJobStatusResponse(
                                "job-1234", "running", 8, 3, 38, "bahamut",
                                "bahamut 처리 중", List.of(), "2026-05-28T00:00:00Z",
                                "2026-05-28T00:00:01Z", "2026-05-28T00:01:00Z", ""));

                mockMvc.perform(get("/api/crawl/jobs/job-1234"))
                                .andExpect(status().isOk())
                                .andExpect(jsonPath("$.jobId").value("job-1234"))
                                .andExpect(jsonPath("$.status").value("running"))
                                .andExpect(jsonPath("$.totalSites").value(8))
                                .andExpect(jsonPath("$.completedSites").value(3))
                                .andExpect(jsonPath("$.percent").value(38))
                                .andExpect(jsonPath("$.currentSite").value("bahamut"));
        }

        @Test
        void getCrawlStats_returnsLatestPipelineStats() throws Exception {
                when(crawlTriggerService.getLatestPipelineStats()).thenReturn(new CrawlPipelineStatsResponse(
                                41, 2136, 1140, 0, 2136,
                                0, 0, 48, 62,
                                95, 76, 1, 2, 5, 1, 2, 2, 0,
                                "2026-06-07T02:48:36Z"));

                mockMvc.perform(get("/api/crawl/stats"))
                                .andExpect(status().isOk())
                                .andExpect(jsonPath("$.listingBoards").value(41))
                                .andExpect(jsonPath("$.listingDiscoveredTotal").value(2136))
                                .andExpect(jsonPath("$.listingUrlsSelected").value(1140))
                                .andExpect(jsonPath("$.selectedP2").value(48))
                                .andExpect(jsonPath("$.selectedP3").value(62))
                                .andExpect(jsonPath("$.attempted").value(95))
                                .andExpect(jsonPath("$.enqueued").value(76))
                                .andExpect(jsonPath("$.recordedAt").value("2026-06-07T02:48:36Z"));
        }

        @Test
        void postCrawlTrigger_publishFailure_returns500WithCorrelationId() throws Exception {
                doThrow(new RuntimeException("redis unavailable"))
                                .when(crawlTriggerService).trigger("redis-fail-cid");

                mockMvc.perform(post("/api/crawl/trigger")
                                .header("X-Correlation-ID", "redis-fail-cid"))
                                .andExpect(status().isInternalServerError())
                                .andExpect(jsonPath("$.errorCode").value("INTERNAL_SERVER_ERROR"))
                                .andExpect(header().string("X-Correlation-ID", "redis-fail-cid"));
        }
}
