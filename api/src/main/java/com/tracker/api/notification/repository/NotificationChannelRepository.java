package com.tracker.api.notification.repository;

import com.tracker.api.notification.domain.NotificationChannel;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;

public interface NotificationChannelRepository extends JpaRepository<NotificationChannel, Long> {
    List<NotificationChannel> findAllByOrderByCreatedAtDesc();
}
