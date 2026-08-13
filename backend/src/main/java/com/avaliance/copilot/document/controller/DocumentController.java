package com.avaliance.copilot.document.controller;

import com.avaliance.copilot.document.dto.DocumentResponse;
import com.avaliance.copilot.document.service.DocumentService;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequestMapping("/api/documents")
@RequiredArgsConstructor
public class DocumentController {

    private final DocumentService documentService;

    @PostMapping(consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    @PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<DocumentResponse> upload(
            @RequestPart("file") MultipartFile file,
            Authentication authentication) {
        return ResponseEntity.status(201).body(documentService.upload(file, authentication.getName()));
    }

    @GetMapping
    @PreAuthorize("hasRole('ADMIN')")
    public Page<DocumentResponse> list(Pageable pageable) {
        return documentService.list(pageable);
    }

    @GetMapping("/{id}/content")
    @PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<?> download(@PathVariable Long id) {
        DocumentService.DownloadedDocument document = documentService.download(id);
        MediaType mediaType;
        try {
            mediaType = MediaType.parseMediaType(document.mediaType());
        } catch (IllegalArgumentException exception) {
            mediaType = MediaType.APPLICATION_OCTET_STREAM;
        }
        ContentDisposition disposition = ContentDisposition.attachment()
                .filename(document.filename())
                .build();
        return ResponseEntity.ok()
                .contentType(mediaType)
                .header(HttpHeaders.CONTENT_DISPOSITION, disposition.toString())
                .body(document.resource());
    }

    @PostMapping("/{id}/index")
    @PreAuthorize("hasRole('ADMIN')")
    public DocumentResponse retryIndex(@PathVariable Long id) {
        return documentService.retryIndex(id);
    }

    @DeleteMapping("/{id}")
    @PreAuthorize("hasRole('ADMIN')")
    public ResponseEntity<Void> delete(@PathVariable Long id) {
        documentService.delete(id);
        return ResponseEntity.noContent().build();
    }
}