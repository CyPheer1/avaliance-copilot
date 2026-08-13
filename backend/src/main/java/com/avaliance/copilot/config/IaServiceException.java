package com.avaliance.copilot.config;

/**
 * Exception thrown when the internal IA service (FastAPI) call fails.
 * Mapped to HTTP 502 Bad Gateway by the GlobalExceptionHandler.
 */
public class IaServiceException extends RuntimeException {

    public IaServiceException(String message) {
        super(message);
    }

    public IaServiceException(String message, Throwable cause) {
        super(message, cause);
    }
}
