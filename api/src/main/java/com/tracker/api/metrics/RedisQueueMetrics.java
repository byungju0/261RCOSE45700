package com.tracker.api.metrics;

import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.binder.MeterBinder;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

@Component
public class RedisQueueMetrics implements MeterBinder {

    private final StringRedisTemplate mqRedisTemplate;

    public RedisQueueMetrics(StringRedisTemplate mqRedisTemplate) {
        this.mqRedisTemplate = mqRedisTemplate;
    }

    @Override
    public void bindTo(MeterRegistry registry) {
        Gauge.builder("redis.queue.size", this, m -> getLen("posts:queue"))
             .tag("queue", "posts:queue")
             .description("Redis posts:queue 리스트 길이")
             .register(registry);
        Gauge.builder("redis.queue.size", this, m -> getLen("posts:dlq"))
             .tag("queue", "posts:dlq")
             .description("Redis posts:dlq 리스트 길이")
             .register(registry);
    }

    private double getLen(String key) {
        try {
            Long size = mqRedisTemplate.opsForList().size(key);
            return size != null ? size : 0.0;
        } catch (Exception e) {
            return 0.0;
        }
    }
}
