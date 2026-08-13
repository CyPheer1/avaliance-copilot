package com.avaliance.copilot.document.dto;

import com.avaliance.copilot.document.entity.DocumentStatus;

import java.time.OffsetDateTime;

public record DocumentResponse(
        Long id,
        String filename,
        String mediaType,
        Long sizeBytes,
        String sha256,
        DocumentStatus status,
        String uploadedBy,
        Integer pageCount,
        Integer chunkCount,
        String errorMessage,
        OffsetDateTime createdAt,
        OffsetDateTime indexedAt
) {
}