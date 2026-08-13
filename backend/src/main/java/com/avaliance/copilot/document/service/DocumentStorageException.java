package com.avaliance.copilot.document.service;

public class DocumentStorageException extends RuntimeException {
    public DocumentStorageException(String message, Throwable cause) {
        super(message, cause);
    }
}