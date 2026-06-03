package com.tracker.api.service;

import com.tracker.api.dto.DetectionListResponse;
import com.tracker.api.dto.DetectionResponse;
import com.tracker.api.exception.DetectionNotFoundException;
import com.tracker.api.exception.InvalidFilterParamException;
import com.tracker.api.repository.DetectionRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.util.StringUtils;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;

@Service
@RequiredArgsConstructor
public class DetectionService {

    private final DetectionRepository detectionRepository;

    @Transactional(readOnly = true)
    public DetectionListResponse getDetections(
            LocalDate date, String range, String site, String type, String lang, int page, int size) {

        Instant fromTime = resolveFromTime(date, range);
        Instant toTime   = date != null ? date.plusDays(1).atStartOfDay(ZoneOffset.UTC).toInstant() : null;

        // 빈 문자열은 null로 변환 (JPQL IS NULL 조건 올바르게 동작)
        String siteParam = StringUtils.hasText(site) ? site : null;
        String typeParam = StringUtils.hasText(type) ? type : null;
        String langParam = StringUtils.hasText(lang) ? lang : null;

        var pageable = PageRequest.of(
                page,
                size,
                Sort.by(
                        Sort.Order.asc("tier"),
                        Sort.Order.desc("detectedAt"),
                        Sort.Order.desc("confidence"),
                        Sort.Order.desc("id")));

        Page<com.tracker.api.domain.Detection> resultPage =
                detectionRepository.findFiltered(fromTime, toTime, siteParam, typeParam, langParam, pageable);

        var content = resultPage.getContent().stream()
                .map(DetectionResponse::from)
                .toList();

        return new DetectionListResponse(content, page, size, resultPage.getTotalElements());
    }

    private Instant resolveFromTime(LocalDate date, String range) {
        if (date != null) {
            return date.atStartOfDay(ZoneOffset.UTC).toInstant();
        }
        if (!StringUtils.hasText(range)) {
            return null;
        }

        LocalDate today = LocalDate.now(ZoneOffset.UTC);
        return switch (range) {
            case "7d" -> today.minusDays(6).atStartOfDay(ZoneOffset.UTC).toInstant();
            case "30d" -> today.minusDays(29).atStartOfDay(ZoneOffset.UTC).toInstant();
            default -> throw new InvalidFilterParamException("range는 7d 또는 30d만 허용됩니다.");
        };
    }

    @Transactional(readOnly = true)
    public DetectionResponse getDetectionById(Long id) {
        return detectionRepository.findByIdFetched(id)
                .map(DetectionResponse::from)
                .orElseThrow(() -> new DetectionNotFoundException(id));
    }

}
