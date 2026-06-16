package com.tracker.api.util;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.web.context.request.WebRequest;

import java.util.UUID;

public final class CorrelationIdUtil {

    private CorrelationIdUtil() {
    }

    public static String resolve(HttpServletRequest request) {
        return resolve(request.getHeader("X-Correlation-ID"));
    }

    public static String resolve(WebRequest request) {
        return resolve(request.getHeader("X-Correlation-ID"));
    }

    private static String resolve(String headerValue) {
        return (headerValue != null && !headerValue.isBlank()) ? headerValue : UUID.randomUUID().toString();
    }
}
