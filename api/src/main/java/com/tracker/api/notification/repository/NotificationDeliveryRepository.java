package com.tracker.api.notification.repository;

import com.tracker.api.notification.domain.NotificationDelivery;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface NotificationDeliveryRepository extends JpaRepository<NotificationDelivery, Long> {
    List<NotificationDelivery> findTop20ByOrderByAttemptedAtDesc();
}
