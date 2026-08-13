package com.avaliance.copilot.config;

/**
 * Exception thrown when the IA service is unavailable (e.g. timeout or connection refused).
 * Mapped to 503 Service Unavailable by GlobalExceptionHandler.
 */
public class IaServiceUnavailableException extends IaServiceException {

    public IaServiceUnavailableException(String message) {
        super(message);
    }
    
    public IaServiceUnavailableException(String message, Throwable cause) {
        super(message, cause);
    }
}
