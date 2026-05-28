package com.tracker.api.repository;

import com.tracker.api.domain.Detection;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import java.time.Instant;
import java.util.Optional;

public interface DetectionRepository extends JpaRepository<Detection, Long> {

    @Query(value = """
            SELECT d FROM Detection d
            JOIN FETCH d.post p
            JOIN FETCH p.source s
            WHERE d.confidence >= 0.70
            AND d.isIllegal = true
            AND (cast(:fromTime as Instant) IS NULL OR d.detectedAt >= :fromTime)
            AND (cast(:toTime   as Instant) IS NULL OR d.detectedAt <  :toTime)
            AND (cast(:site     as String)  IS NULL OR s.siteName = :site)
            AND (cast(:type     as String)  IS NULL OR d.type = :type)
            AND (cast(:lang     as String)  IS NULL OR p.language = :lang)
            """,
            countQuery = """
            SELECT COUNT(d) FROM Detection d
            JOIN d.post p JOIN p.source s
            WHERE d.confidence >= 0.70
            AND d.isIllegal = true
            AND (cast(:fromTime as Instant) IS NULL OR d.detectedAt >= :fromTime)
            AND (cast(:toTime   as Instant) IS NULL OR d.detectedAt <  :toTime)
            AND (cast(:site     as String)  IS NULL OR s.siteName = :site)
            AND (cast(:type     as String)  IS NULL OR d.type = :type)
            AND (cast(:lang     as String)  IS NULL OR p.language = :lang)
            """)
    Page<Detection> findFiltered(
            @Param("fromTime") Instant fromTime,
            @Param("toTime")   Instant toTime,
            @Param("site")     String site,
            @Param("type")     String type,
            @Param("lang")     String lang,
            Pageable pageable);

    @Query("""
            SELECT d FROM Detection d
            JOIN FETCH d.post p
            JOIN FETCH p.source s
            WHERE d.id = :id
            """)
    Optional<Detection> findByIdFetched(@Param("id") Long id);
}
