package com.tracker.api.exception;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.ConstraintViolationException;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;
import org.springframework.web.servlet.mvc.method.annotation.ResponseEntityExceptionHandler;
import org.springframework.web.context.request.WebRequest;
import java.util.UUID;

@RestControllerAdvice
public class GlobalExceptionHandler extends ResponseEntityExceptionHandler {

    @ExceptionHandler(DetectionNotFoundException.class)
    public ResponseEntity<ProblemDetail> handleDetectionNotFound(
            DetectionNotFoundException ex,
            HttpServletRequest request) {
        var pd = ProblemDetail.forStatusAndDetail(HttpStatus.NOT_FOUND, ex.getMessage());
        pd.setTitle("Detection Not Found");
        pd.setProperty("errorCode", "DETECTION_NOT_FOUND");
        return withCorrelationId(pd, request);
    }

    @ExceptionHandler(CrawlJobNotFoundException.class)
    public ResponseEntity<ProblemDetail> handleCrawlJobNotFound(
            CrawlJobNotFoundException ex,
            HttpServletRequest request) {
        var pd = ProblemDetail.forStatusAndDetail(HttpStatus.NOT_FOUND, ex.getMessage());
        pd.setTitle("Crawl Job Not Found");
        pd.setProperty("errorCode", "CRAWL_JOB_NOT_FOUND");
        return withCorrelationId(pd, request);
    }

    @ExceptionHandler(NotificationResourceNotFoundException.class)
    public ResponseEntity<ProblemDetail> handleNotificationResourceNotFound(
            NotificationResourceNotFoundException ex,
            HttpServletRequest request) {
        var pd = ProblemDetail.forStatusAndDetail(HttpStatus.NOT_FOUND, ex.getMessage());
        pd.setTitle("Notification Resource Not Found");
        pd.setProperty("errorCode", "NOTIFICATION_RESOURCE_NOT_FOUND");
        return withCorrelationId(pd, request);
    }

    @ExceptionHandler(InvalidFilterParamException.class)
    public ResponseEntity<ProblemDetail> handleInvalidFilterParam(
            InvalidFilterParamException ex,
            HttpServletRequest request) {
        return withCorrelationId(invalidFilterProblem(ex.getMessage()), request);
    }

    @ExceptionHandler(ConstraintViolationException.class)
    public ResponseEntity<ProblemDetail> handleConstraintViolation(
            ConstraintViolationException ex,
            HttpServletRequest request) {
        return withCorrelationId(invalidFilterProblem(ex.getMessage()), request);
    }

    @ExceptionHandler(MethodArgumentTypeMismatchException.class)
    public ResponseEntity<ProblemDetail> handleTypeMismatch(
            MethodArgumentTypeMismatchException ex,
            HttpServletRequest request) {
        return withCorrelationId(
                invalidFilterProblem("파라미터 '%s'의 값이 올바르지 않습니다: %s".formatted(
                        ex.getName(), ex.getValue())),
                request);
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<ProblemDetail> handleAll(Exception ex, HttpServletRequest request) {
        logger.error("Unhandled exception", ex);
        var pd = ProblemDetail.forStatusAndDetail(
                HttpStatus.INTERNAL_SERVER_ERROR,
                "서버 내부 오류가 발생했습니다.");
        pd.setTitle("Internal Server Error");
        pd.setProperty("errorCode", "INTERNAL_SERVER_ERROR");
        return withCorrelationId(pd, request);
    }

    @Override
    protected ResponseEntity<Object> handleExceptionInternal(
            Exception ex,
            Object body,
            HttpHeaders headers,
            HttpStatusCode statusCode,
            WebRequest request) {

        Object responseBody = body;
        if (responseBody instanceof ProblemDetail problemDetail) {
            problemDetail.setProperty("errorCode", errorCodeFor(statusCode));
        } else if (responseBody == null) {
            var problemDetail = ProblemDetail.forStatus(statusCode);
            problemDetail.setTitle(statusCode.is4xxClientError() ? "Invalid Parameter" : "Internal Server Error");
            problemDetail.setProperty("errorCode", errorCodeFor(statusCode));
            responseBody = problemDetail;
        }

        var responseHeaders = new HttpHeaders();
        responseHeaders.putAll(headers);
        responseHeaders.set("X-Correlation-ID", correlationIdFrom(request));

        return super.handleExceptionInternal(ex, responseBody, responseHeaders, statusCode, request);
    }

    private ProblemDetail invalidFilterProblem(String detail) {
        var pd = ProblemDetail.forStatusAndDetail(HttpStatus.BAD_REQUEST, detail);
        pd.setTitle("Invalid Parameter");
        pd.setProperty("errorCode", "INVALID_FILTER_PARAM");
        return pd;
    }

    private String errorCodeFor(HttpStatusCode statusCode) {
        return statusCode.is4xxClientError() ? "INVALID_FILTER_PARAM" : "INTERNAL_SERVER_ERROR";
    }

    private ResponseEntity<ProblemDetail> withCorrelationId(
            ProblemDetail problemDetail,
            HttpServletRequest request) {

        return ResponseEntity
                .status(problemDetail.getStatus())
                .header("X-Correlation-ID", correlationIdFrom(request))
                .body(problemDetail);
    }

    private String correlationIdFrom(HttpServletRequest request) {
        String correlationId = request.getHeader("X-Correlation-ID");
        if (correlationId == null || correlationId.isBlank()) {
            return UUID.randomUUID().toString();
        }
        return correlationId;
    }

    private String correlationIdFrom(WebRequest request) {
        String correlationId = request.getHeader("X-Correlation-ID");
        if (correlationId == null || correlationId.isBlank()) {
            return UUID.randomUUID().toString();
        }
        return correlationId;
    }
}
