package com.tracker.api.notification.repository;

import com.tracker.api.notification.domain.NotificationEvent;
import com.tracker.api.notification.domain.NotificationEventStatus;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.List;
import java.util.Optional;
import java.time.Instant;

public interface NotificationEventRepository extends JpaRepository<NotificationEvent, Long> {

    @Query(value = """
            SELECT id
            FROM notification_events
            WHERE (
                status = 'PENDING'
                OR (status = 'PROCESSING' AND claimed_at < NOW() - (:staleAfterSeconds * INTERVAL '1 second'))
            )
              AND attempts < :maxAttempts
            ORDER BY created_at ASC
            LIMIT :limit
            FOR UPDATE SKIP LOCKED
            """, nativeQuery = true)
    List<Long> findPendingIdsForUpdate(
            @Param("limit") int limit,
            @Param("maxAttempts") int maxAttempts,
            @Param("staleAfterSeconds") int staleAfterSeconds);

    @Modifying
    @Query("""
            UPDATE NotificationEvent e
            SET e.status = :status,
                e.attempts = e.attempts + 1,
                e.lastError = null,
                e.claimedAt = :claimedAt
            WHERE e.id IN :ids
            """)
    int markClaimed(
            @Param("ids") List<Long> ids,
            @Param("status") NotificationEventStatus status,
            @Param("claimedAt") Instant claimedAt);

    @Query("""
            SELECT e FROM NotificationEvent e
            LEFT JOIN FETCH e.detection d
            LEFT JOIN FETCH d.post p
            LEFT JOIN FETCH p.source s
            WHERE e.id = :id
            """)
    Optional<NotificationEvent> findByIdFetched(@Param("id") Long id);
}
