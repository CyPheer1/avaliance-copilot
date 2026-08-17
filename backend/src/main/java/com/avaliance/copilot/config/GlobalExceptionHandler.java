package com.avaliance.copilot.config;

import jakarta.persistence.EntityNotFoundException;
import com.avaliance.copilot.document.service.DocumentStorageException;
import com.avaliance.copilot.document.service.UnsupportedDocumentTypeException;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.bind.support.WebExchangeBindException;
import org.springframework.web.multipart.MaxUploadSizeExceededException;

import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.stream.Collectors;

/**
 * Centralized exception handler — returns uniform JSON error responses.
 */
@Slf4j
@RestControllerAdvice
public class GlobalExceptionHandler {

    // --- 400 Bad Request (validation) ---
    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<Map<String, Object>> handleValidation(MethodArgumentNotValidException ex) {
        String details = ex.getBindingResult().getFieldErrors().stream()
                .map(FieldError::getDefaultMessage)
                .collect(Collectors.joining("; "));
        return buildResponse(HttpStatus.BAD_REQUEST, "Validation failed", details);
    }

    @ExceptionHandler(WebExchangeBindException.class)
    public ResponseEntity<Map<String, Object>> handleWebFluxValidation(WebExchangeBindException ex) {
        String details = ex.getBindingResult().getFieldErrors().stream()
                .map(FieldError::getDefaultMessage)
                .collect(Collectors.joining("; "));
        return buildResponse(HttpStatus.BAD_REQUEST, "Validation failed", details);
    }

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<Map<String, Object>> handleIllegalArgument(IllegalArgumentException ex) {
        return buildResponse(HttpStatus.BAD_REQUEST, "Bad request", ex.getMessage());
    }

    // --- 422 Unprocessable Entity (IA validation / RfpInputError) ---
    @ExceptionHandler(IaValidationException.class)
    public ResponseEntity<Map<String, Object>> handleIaValidation(IaValidationException ex) {
        return buildResponse(HttpStatus.UNPROCESSABLE_ENTITY, "Unprocessable Entity", ex.getMessage());
    }

    @ExceptionHandler(UnsupportedDocumentTypeException.class)
    public ResponseEntity<Map<String, Object>> handleUnsupportedDocument(UnsupportedDocumentTypeException ex) {
        return buildResponse(HttpStatus.UNSUPPORTED_MEDIA_TYPE, "Unsupported document", ex.getMessage());
    }

    @ExceptionHandler(MaxUploadSizeExceededException.class)
    public ResponseEntity<Map<String, Object>> handleUploadTooLarge(MaxUploadSizeExceededException ex) {
        return buildResponse(HttpStatus.PAYLOAD_TOO_LARGE, "Document too large", "La taille maximale est de 20 Mo.");
    }

    @ExceptionHandler(DocumentStorageException.class)
    public ResponseEntity<Map<String, Object>> handleDocumentStorage(DocumentStorageException ex) {
        log.error("Document storage error: {}", ex.getMessage(), ex);
        return buildResponse(HttpStatus.INTERNAL_SERVER_ERROR, "Document storage error", ex.getMessage());
    }

    // --- 401 Unauthorized ---
    @ExceptionHandler(BadCredentialsException.class)
    public ResponseEntity<Map<String, Object>> handleBadCredentials(BadCredentialsException ex) {
        return buildResponse(HttpStatus.UNAUTHORIZED, "Unauthorized", "Invalid username or password");
    }

    // --- 403 Forbidden ---
    @ExceptionHandler(AccessDeniedException.class)
    public ResponseEntity<Map<String, Object>> handleAccessDenied(AccessDeniedException ex) {
        return buildResponse(HttpStatus.FORBIDDEN, "Forbidden", ex.getMessage());
    }

    // --- 404 Not Found ---
    @ExceptionHandler(EntityNotFoundException.class)
    public ResponseEntity<Map<String, Object>> handleNotFound(EntityNotFoundException ex) {
        return buildResponse(HttpStatus.NOT_FOUND, "Not found", ex.getMessage());
    }

    // --- 503 Service Unavailable (IA service timeout/offline) ---
    @ExceptionHandler(IaServiceUnavailableException.class)
    public ResponseEntity<Map<String, Object>> handleIaServiceUnavailable(IaServiceUnavailableException ex) {
        log.error("IA service unavailable (timeout/offline): {}", ex.getMessage(), ex);
        return buildResponse(HttpStatus.SERVICE_UNAVAILABLE, "IA service unavailable", ex.getMessage());
    }

    // --- 502 Bad Gateway (IA service error) ---
    @ExceptionHandler(IaServiceException.class)
    public ResponseEntity<Map<String, Object>> handleIaServiceError(IaServiceException ex) {
        log.error("IA service error (bad response): {}", ex.getMessage(), ex);
        return buildResponse(HttpStatus.BAD_GATEWAY, "IA service error", ex.getMessage());
    }

    // --- 500 catch-all ---
    @ExceptionHandler(Exception.class)
    public ResponseEntity<Map<String, Object>> handleGeneric(Exception ex) {
        log.error("Unexpected error: {}", ex.getMessage(), ex);
        return buildResponse(HttpStatus.INTERNAL_SERVER_ERROR, "Internal server error", "An unexpected error occurred");
    }

    private ResponseEntity<Map<String, Object>> buildResponse(HttpStatus status, String error, String message) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("status", status.value());
        body.put("error", error);
        body.put("message", message);
        body.put("timestamp", Instant.now().toString());
        return ResponseEntity.status(status).body(body);
    }
}
