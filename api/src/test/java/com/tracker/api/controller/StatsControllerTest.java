package com.tracker.api.controller;

import com.tracker.api.dto.StatsResponse;
import com.tracker.api.service.StatsService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import java.util.List;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@WebMvcTest(StatsController.class)
class StatsControllerTest {

    @Autowired MockMvc mockMvc;
    @MockitoBean StatsService statsService;

    @Test
    void getStats_returnsOk() throws Exception {
        var typeItem = new StatsResponse.DistributionItem("매크로_판매", 5L);
        var siteItem = new StatsResponse.DistributionItem("tailstar.net", 3L);
        var langItem = new StatsResponse.DistributionItem("zh-CN", 4L);
        var response = new StatsResponse(10L, 2L,
                List.of(typeItem), List.of(siteItem), List.of(langItem), List.of());
        when(statsService.getStats(null)).thenReturn(response);

        mockMvc.perform(get("/api/stats"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.todayCount").value(10))
                .andExpect(jsonPath("$.deltaFromYesterday").value(2))
                .andExpect(jsonPath("$.typeDistribution[0].label").value("매크로_판매"))
                .andExpect(jsonPath("$.typeDistribution[0].count").value(5))
                .andExpect(jsonPath("$.siteDistribution[0].label").value("tailstar.net"))
                .andExpect(jsonPath("$.langDistribution[0].label").value("zh-CN"))
                .andExpect(jsonPath("$.trend").isArray())
                .andExpect(header().exists("X-Correlation-ID"));
    }

    @Test
    void getStats_withPeriodWeekly_returnsTrend() throws Exception {
        var trendItem = new StatsResponse.TrendItem("2026-04-30", 5L);
        var response = new StatsResponse(10L, 2L, List.of(), List.of(), List.of(), List.of(trendItem));
        when(statsService.getStats("weekly")).thenReturn(response);

        mockMvc.perform(get("/api/stats").param("period", "weekly"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.trend[0].date").value("2026-04-30"))
                .andExpect(jsonPath("$.trend[0].count").value(5));

        verify(statsService).getStats("weekly");
    }

    @Test
    void getStats_withPeriodMonthly_returnsTrend() throws Exception {
        var response = new StatsResponse(10L, 2L, List.of(), List.of(), List.of(), List.of());
        when(statsService.getStats("monthly")).thenReturn(response);

        mockMvc.perform(get("/api/stats").param("period", "monthly"))
                .andExpect(status().isOk());

        verify(statsService).getStats("monthly");
    }
}
