package com.tracker.api.config;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.connection.RedisStandaloneConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;
import org.springframework.data.redis.core.StringRedisTemplate;

@Configuration
public class RedisConfig {

    @Value("${spring.data.redis.host:localhost}")
    private String redisHost;

    @Value("${spring.data.redis.port:6379}")
    private int redisPort;

    @Value("${spring.data.redis.cache.database:3}")
    private int cacheDb;

    // DB0 primary bean — @ConditionalOnMissingBean suppresses auto-config when cacheRedisTemplate exists
    @Bean
    @Primary
    public StringRedisTemplate stringRedisTemplate(RedisConnectionFactory redisConnectionFactory) {
        return new StringRedisTemplate(redisConnectionFactory);
    }

    @Bean("cacheRedisTemplate")
    public StringRedisTemplate cacheRedisTemplate() {
        var config = new RedisStandaloneConfiguration(redisHost, redisPort);
        config.setDatabase(cacheDb);
        var cf = new LettuceConnectionFactory(config);
        cf.afterPropertiesSet();
        return new StringRedisTemplate(cf);
    }
}
