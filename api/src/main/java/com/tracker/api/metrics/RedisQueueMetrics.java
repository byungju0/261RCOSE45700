package com.tracker.api.metrics;

import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.binder.MeterBinder;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

@Component
public class RedisQueueMetrics implements MeterBinder {

    private final StringRedisTemplate mqRedisTemplate;
    private volatile boolean redisAvailable = true;

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
        Gauge.builder("redis.queue.scrape.failure", this, RedisQueueMetrics::getFailureState)
             .description("Redis queue metric scrape failure state; 1 means the last scrape failed")
             .register(registry);
    }

    private double getLen(String key) {
        try {
            Long size = mqRedisTemplate.opsForList().size(key);
            redisAvailable = true;
            return size != null ? size : 0.0;
        } catch (Exception e) {
            redisAvailable = false;
            return 0.0;
        }
    }

    private double getFailureState() {
        return redisAvailable ? 0.0 : 1.0;
    }
}
