package com.avaliance.copilot.document.service;

public class UnsupportedDocumentTypeException extends RuntimeException {
    public UnsupportedDocumentTypeException(String message) {
        super(message);
    }
}