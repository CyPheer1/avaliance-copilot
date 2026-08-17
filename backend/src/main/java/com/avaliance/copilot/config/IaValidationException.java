package com.avaliance.copilot.config;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ResponseStatus;

/**
 * Exception thrown when the IA service rejects input as unprocessable (e.g. empty or greeting-only brief).
 * Mapped to HTTP 422 Unprocessable Entity by GlobalExceptionHandler.
 */
@ResponseStatus(HttpStatus.UNPROCESSABLE_ENTITY)
public class IaValidationException extends RuntimeException {
    public IaValidationException(String message) {
        super(message);
    }
}
