package com.tracker.api.repository;

import com.tracker.api.domain.Detection;
import com.tracker.api.domain.Post;
import com.tracker.api.domain.Source;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.test.util.ReflectionTestUtils;

import java.time.Instant;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest(properties = {
        "spring.flyway.enabled=false",
        "spring.jpa.hibernate.ddl-auto=create-drop",
        "spring.jpa.database-platform=org.hibernate.dialect.H2Dialect"
})
class DetectionRepositoryTest {

    @Autowired DetectionRepository detectionRepository;
    @Autowired TestEntityManager entityManager;

    @Test
    void findFiltered_appliesFiltersAndConfidenceThreshold() {
        persistDetection("tailstar.net", "매크로_판매", "ko", 0.95,
                Instant.parse("2026-04-24T14:30:00Z"));
        persistDetection("tailstar.net", "매크로_판매", "ko", 0.69,
                Instant.parse("2026-04-24T15:30:00Z"));
        persistDetection("other.net", "매크로_판매", "ko", 0.97,
                Instant.parse("2026-04-24T16:30:00Z"));
        entityManager.flush();
        entityManager.clear();

        var result = detectionRepository.findFiltered(
                Instant.parse("2026-04-24T00:00:00Z"),
                Instant.parse("2026-04-25T00:00:00Z"),
                "tailstar.net",
                "매크로_판매",
                "ko",
                PageRequest.of(0, 20, Sort.by(Sort.Direction.DESC, "confidence")));

        assertThat(result.getTotalElements()).isEqualTo(1);
        assertThat(result.getContent()).singleElement()
                .satisfies(detection -> {
                    assertThat(detection.getConfidence()).isEqualTo(0.95);
                    assertThat(detection.getPost().getSource().getSiteName()).isEqualTo("tailstar.net");
                    assertThat(detection.getPost().getLanguage()).isEqualTo("ko");
                });
    }

    @Test
    void findFiltered_ordersByActionPriorityThenLatestDetection() {
        persistDetection("tailstar.net", "매크로_판매", "ko", "T2", 0.99,
                Instant.parse("2026-04-24T14:32:00Z"));
        persistDetection("tailstar.net", "핵_치트", "ko", "T1", 0.80,
                Instant.parse("2026-04-24T14:31:00Z"));
        persistDetection("tailstar.net", "핵_치트", "ko", "T1", 0.75,
                Instant.parse("2026-04-24T14:33:00Z"));
        entityManager.flush();
        entityManager.clear();

        var result = detectionRepository.findFiltered(
                null,
                null,
                null,
                null,
                null,
                PageRequest.of(
                        0,
                        20,
                        Sort.by(
                                Sort.Order.asc("tier"),
                                Sort.Order.desc("detectedAt"),
                                Sort.Order.desc("confidence"),
                                Sort.Order.desc("id"))));

        assertThat(result.getContent())
                .extracting(Detection::getTier, Detection::getConfidence, Detection::getDetectedAt)
                .containsExactly(
                        org.assertj.core.groups.Tuple.tuple("T1", 0.75, Instant.parse("2026-04-24T14:33:00Z")),
                        org.assertj.core.groups.Tuple.tuple("T1", 0.80, Instant.parse("2026-04-24T14:31:00Z")),
                        org.assertj.core.groups.Tuple.tuple("T2", 0.99, Instant.parse("2026-04-24T14:32:00Z")));
    }

    private void persistDetection(
            String siteName,
            String type,
            String language,
            double confidence,
            Instant detectedAt) {
        persistDetection(siteName, type, language, "T2", confidence, detectedAt);
    }

    private void persistDetection(
            String siteName,
            String type,
            String language,
            String tier,
            double confidence,
            Instant detectedAt) {

        var source = new Source();
        ReflectionTestUtils.setField(source, "siteName", siteName);
        ReflectionTestUtils.setField(source, "baseUrl", "https://" + siteName);
        entityManager.persist(source);

        var post = new Post();
        ReflectionTestUtils.setField(post, "source", source);
        ReflectionTestUtils.setField(post, "postIdAtSource", siteName + "-" + confidence);
        ReflectionTestUtils.setField(post, "body", "raw text");
        ReflectionTestUtils.setField(post, "postUrl", "https://" + siteName + "/posts/" + confidence);
        ReflectionTestUtils.setField(post, "language", language);
        ReflectionTestUtils.setField(post, "crawledAt", detectedAt);
        entityManager.persist(post);

        var detection = new Detection();
        ReflectionTestUtils.setField(detection, "post", post);
        ReflectionTestUtils.setField(detection, "illegal", true);
        ReflectionTestUtils.setField(detection, "type", type);
        ReflectionTestUtils.setField(detection, "tier", tier);
        ReflectionTestUtils.setField(detection, "confidence", confidence);
        ReflectionTestUtils.setField(detection, "reason", "reason");
        ReflectionTestUtils.setField(detection, "modelVersion", "test-model");
        ReflectionTestUtils.setField(detection, "detectedAt", detectedAt);
        entityManager.persist(detection);
    }
}
