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
    public long countToday(LocalDate today) {
        Instant from = today.atStartOfDay().toInstant(ZoneOffset.UTC);
        return countInRange(from, from.plus(1, ChronoUnit.DAYS));
    }

    @Transactional(readOnly = true)
    public long countYesterday(LocalDate today) {
        Instant to = today.atStartOfDay().toInstant(ZoneOffset.UTC);
        return countInRange(to.minus(1, ChronoUnit.DAYS), to);
    }

    private long countInRange(Instant from, Instant to) {
        return (Long) em.createQuery(
                "SELECT COUNT(d) FROM Detection d WHERE d.detectedAt >= :from AND d.detectedAt < :to AND d.confidence >= 0.70 AND d.illegal = true")
                .setParameter("from", from)
                .setParameter("to", to)
                .getSingleResult();
    }

    @Transactional(readOnly = true)
    @SuppressWarnings("unchecked")
    public List<Object[]> findTypeDistributionRaw() {
        return em.createQuery(
                "SELECT d.type, COUNT(d) FROM Detection d WHERE d.confidence >= 0.70 AND d.illegal = true GROUP BY d.type ORDER BY COUNT(d) DESC")
                .getResultList();
    }

    @Transactional(readOnly = true)
    @SuppressWarnings("unchecked")
    public List<Object[]> findTypeDistributionRaw(Instant from, Instant to) {
        return em.createQuery(
                "SELECT d.type, COUNT(d) FROM Detection d " +
                "WHERE d.detectedAt >= :from AND d.detectedAt < :to AND d.confidence >= 0.70 AND d.illegal = true " +
                "GROUP BY d.type ORDER BY COUNT(d) DESC")
                .setParameter("from", from)
                .setParameter("to", to)
                .getResultList();
    }

    @Transactional(readOnly = true)
    @SuppressWarnings("unchecked")
    public List<Object[]> findSiteDistributionRaw() {
        return em.createQuery(
                "SELECT s.siteName, COUNT(d) FROM Detection d JOIN d.post p JOIN p.source s WHERE d.confidence >= 0.70 AND d.illegal = true GROUP BY s.siteName ORDER BY COUNT(d) DESC")
                .getResultList();
    }

    @Transactional(readOnly = true)
    @SuppressWarnings("unchecked")
    public List<Object[]> findSiteDistributionRaw(Instant from, Instant to) {
        return em.createQuery(
                "SELECT s.siteName, COUNT(d) FROM Detection d JOIN d.post p JOIN p.source s " +
                "WHERE d.detectedAt >= :from AND d.detectedAt < :to AND d.confidence >= 0.70 AND d.illegal = true " +
                "GROUP BY s.siteName ORDER BY COUNT(d) DESC")
                .setParameter("from", from)
                .setParameter("to", to)
                .getResultList();
    }

    @Transactional(readOnly = true)
    @SuppressWarnings("unchecked")
    public List<Object[]> findLangDistributionRaw() {
        return em.createQuery(
                "SELECT p.language, COUNT(d) FROM Detection d JOIN d.post p WHERE d.confidence >= 0.70 AND d.illegal = true GROUP BY p.language ORDER BY COUNT(d) DESC")
                .getResultList();
    }

    @Transactional(readOnly = true)
    @SuppressWarnings("unchecked")
    public List<Object[]> findLangDistributionRaw(Instant from, Instant to) {
        return em.createQuery(
                "SELECT p.language, COUNT(d) FROM Detection d JOIN d.post p " +
                "WHERE d.detectedAt >= :from AND d.detectedAt < :to AND d.confidence >= 0.70 AND d.illegal = true " +
                "GROUP BY p.language ORDER BY COUNT(d) DESC")
                .setParameter("from", from)
                .setParameter("to", to)
                .getResultList();
    }

    @Transactional(readOnly = true)
    @SuppressWarnings("unchecked")
    public List<Object[]> findSourceHealthRaw() {
        return (List<Object[]>) em.createNativeQuery(
                "SELECT s.site_name, MAX(p.crawled_at) AS last_crawled_at " +
                "FROM sources s LEFT JOIN posts p ON p.source_id = s.id " +
                "GROUP BY s.site_name ORDER BY s.site_name")
                .getResultList();
    }

    @Transactional(readOnly = true)
    @SuppressWarnings("unchecked")
    public List<Object[]> findTrendRaw(Instant from, Instant to) {
        return em.createNativeQuery(
                "SELECT CAST(detected_at AT TIME ZONE 'UTC' AS DATE) AS day, COUNT(*) AS cnt " +
                "FROM detections " +
                "WHERE detected_at >= :from AND detected_at < :to AND confidence >= 0.70 AND is_illegal = true " +
                "GROUP BY CAST(detected_at AT TIME ZONE 'UTC' AS DATE) " +
                "ORDER BY CAST(detected_at AT TIME ZONE 'UTC' AS DATE)")
                .setParameter("from", from)
                .setParameter("to", to)
                .getResultList();
    }
}
