package com.tracker.api.notification.repository;

import com.tracker.api.notification.domain.NotificationEventType;
import com.tracker.api.notification.domain.NotificationRule;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.List;

public interface NotificationRuleRepository extends JpaRepository<NotificationRule, Long> {

    @Query("""
            SELECT r FROM NotificationRule r
            JOIN FETCH r.channel c
            WHERE r.enabled = true
              AND c.enabled = true
              AND r.eventType = :eventType
            ORDER BY r.createdAt ASC
            """)
    List<NotificationRule> findEnabledRules(@Param("eventType") NotificationEventType eventType);

    @Query("""
            SELECT r FROM NotificationRule r
            JOIN FETCH r.channel c
            ORDER BY r.createdAt DESC
            """)
    List<NotificationRule> findAllFetched();
}
