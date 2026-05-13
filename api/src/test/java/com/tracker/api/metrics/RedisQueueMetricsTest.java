package com.tracker.api.metrics;

import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.data.redis.core.ListOperations;
import org.springframework.data.redis.core.StringRedisTemplate;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class RedisQueueMetricsTest {

    @Mock
    private StringRedisTemplate redisTemplate;

    @Mock
    private ListOperations<String, String> listOps;

    private SimpleMeterRegistry registry;
    private RedisQueueMetrics metrics;

    @BeforeEach
    void setUp() {
        when(redisTemplate.opsForList()).thenReturn(listOps);
        registry = new SimpleMeterRegistry();
        metrics = new RedisQueueMetrics(redisTemplate);
        metrics.bindTo(registry);
    }

    @Test
    void queueGauge_returnsLlen() {
        when(listOps.size("posts:queue")).thenReturn(5L);

        Gauge gauge = registry.find("redis.queue.size").tag("queue", "posts:queue").gauge();
        assertThat(gauge).isNotNull();
        assertThat(gauge.value()).isEqualTo(5.0);
        assertThat(failureGauge().value()).isEqualTo(0.0);
    }

    @Test
    void dlqGauge_returnsLlen() {
        when(listOps.size("posts:dlq")).thenReturn(3L);

        Gauge gauge = registry.find("redis.queue.size").tag("queue", "posts:dlq").gauge();
        assertThat(gauge).isNotNull();
        assertThat(gauge.value()).isEqualTo(3.0);
    }

    @Test
    void gauge_redisFails_returnsZero() {
        when(listOps.size("posts:queue")).thenThrow(new RuntimeException("Redis connection failed"));

        Gauge gauge = registry.find("redis.queue.size").tag("queue", "posts:queue").gauge();
        assertThat(gauge).isNotNull();
        assertThat(gauge.value()).isEqualTo(0.0);
        assertThat(failureGauge().value()).isEqualTo(1.0);
    }

    @Test
    void failureGauge_recoversAfterSuccessfulScrape() {
        when(listOps.size("posts:queue"))
                .thenThrow(new RuntimeException("Redis connection failed"))
                .thenReturn(2L);

        Gauge queueGauge = registry.find("redis.queue.size").tag("queue", "posts:queue").gauge();
        assertThat(queueGauge).isNotNull();
        assertThat(queueGauge.value()).isEqualTo(0.0);
        assertThat(failureGauge().value()).isEqualTo(1.0);

        assertThat(queueGauge.value()).isEqualTo(2.0);
        assertThat(failureGauge().value()).isEqualTo(0.0);
    }

    private Gauge failureGauge() {
        Gauge gauge = registry.find("redis.queue.scrape.failure").gauge();
        assertThat(gauge).isNotNull();
        return gauge;
    }
}
