package com.tracker.api.repository;

import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.time.temporal.ChronoUnit;
import java.util.List;

@Repository
public class StatsRepository {

    @PersistenceContext
    private EntityManager em;

    @Transactional(readOnly = true)
    public long countToday() {
        Instant from = LocalDate.now(ZoneOffset.UTC).atStartOfDay().toInstant(ZoneOffset.UTC);
        Instant to = from.plus(1, ChronoUnit.DAYS);
        return (Long) em.createQuery(
                "SELECT COUNT(d) FROM Detection d WHERE d.detectedAt >= :from AND d.detectedAt < :to AND d.confidence >= 0.70")
                .setParameter("from", from)
                .setParameter("to", to)
                .getSingleResult();
    }

    @Transactional(readOnly = true)
    public long countYesterday() {
        Instant to = LocalDate.now(ZoneOffset.UTC).atStartOfDay().toInstant(ZoneOffset.UTC);
        Instant from = to.minus(1, ChronoUnit.DAYS);
        return (Long) em.createQuery(
                "SELECT COUNT(d) FROM Detection d WHERE d.detectedAt >= :from AND d.detectedAt < :to AND d.confidence >= 0.70")
                .setParameter("from", from)
                .setParameter("to", to)
                .getSingleResult();
    }

    @Transactional(readOnly = true)
    @SuppressWarnings("unchecked")
    public List<Object[]> findTypeDistributionRaw() {
        return em.createQuery(
                "SELECT d.type, COUNT(d) FROM Detection d WHERE d.confidence >= 0.70 GROUP BY d.type ORDER BY COUNT(d) DESC")
                .getResultList();
    }

    @Transactional(readOnly = true)
    @SuppressWarnings("unchecked")
    public List<Object[]> findSiteDistributionRaw() {
        return em.createQuery(
                "SELECT s.siteName, COUNT(d) FROM Detection d JOIN d.post p JOIN p.source s WHERE d.confidence >= 0.70 GROUP BY s.siteName ORDER BY COUNT(d) DESC")
                .getResultList();
    }

    @Transactional(readOnly = true)
    @SuppressWarnings("unchecked")
    public List<Object[]> findLangDistributionRaw() {
        return em.createQuery(
                "SELECT p.language, COUNT(d) FROM Detection d JOIN d.post p WHERE d.confidence >= 0.70 GROUP BY p.language ORDER BY COUNT(d) DESC")
                .getResultList();
    }

    @Transactional(readOnly = true)
    @SuppressWarnings("unchecked")
    public List<Object[]> findTrendRaw(Instant from, Instant to) {
        return em.createNativeQuery(
                "SELECT CAST(detected_at AT TIME ZONE 'UTC' AS DATE) AS day, COUNT(*) AS cnt " +
                "FROM detections " +
                "WHERE detected_at >= :from AND detected_at < :to AND confidence >= 0.70 " +
                "GROUP BY CAST(detected_at AT TIME ZONE 'UTC' AS DATE) " +
                "ORDER BY CAST(detected_at AT TIME ZONE 'UTC' AS DATE)")
                .setParameter("from", from)
                .setParameter("to", to)
                .getResultList();
    }
}
