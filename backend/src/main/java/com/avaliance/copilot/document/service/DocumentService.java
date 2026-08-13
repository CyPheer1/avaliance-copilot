package com.avaliance.copilot.document.service;

import com.avaliance.copilot.auth.entity.AppUser;
import com.avaliance.copilot.auth.repository.AppUserRepository;
import com.avaliance.copilot.document.dto.DocumentResponse;
import com.avaliance.copilot.document.entity.DocumentStatus;
import com.avaliance.copilot.document.entity.SourceDocument;
import com.avaliance.copilot.document.repository.SourceDocumentRepository;
import com.avaliance.copilot.search.service.IaClientService;
import jakarta.persistence.EntityNotFoundException;
import lombok.RequiredArgsConstructor;
import org.springframework.core.io.Resource;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;

import java.time.OffsetDateTime;
import java.util.Map;

@Service
@RequiredArgsConstructor
public class DocumentService {

    private final SourceDocumentRepository documentRepository;
    private final AppUserRepository userRepository;
    private final DocumentStorageService storageService;
    private final IaClientService iaClientService;

    public DocumentResponse upload(MultipartFile file, String username) {
        AppUser uploader = userRepository.findByUsername(username)
                .orElseThrow(() -> new EntityNotFoundException("Utilisateur introuvable."));
        DocumentStorageService.StoredDocument stored = storageService.store(file);
        SourceDocument document = SourceDocument.builder()
                .originalFilename(stored.originalFilename())
                .storageKey(stored.storageKey())
                .mediaType(stored.mediaType())
                .sizeBytes(stored.sizeBytes())
                .sha256(stored.sha256())
                .status(DocumentStatus.STORED)
                .uploadedBy(uploader)
                .build();
        documentRepository.saveAndFlush(document);
        indexDocument(document);
        return toResponse(document);
    }

    @Transactional(readOnly = true)
    public Page<DocumentResponse> list(Pageable pageable) {
        return documentRepository.findAll(pageable).map(this::toResponse);
    }

    @Transactional
    public DocumentResponse retryIndex(Long id) {
        SourceDocument document = find(id);
        indexDocument(document);
        return toResponse(document);
    }

    @Transactional(readOnly = true)
    public DownloadedDocument download(Long id) {
        SourceDocument document = find(id);
        return new DownloadedDocument(
                storageService.resource(document.getStorageKey()),
                document.getOriginalFilename(),
                document.getMediaType()
        );
    }

    @Transactional
    public void delete(Long id) {
        SourceDocument document = find(id);
        storageService.delete(document.getStorageKey());
        documentRepository.delete(document);
    }

    private void indexDocument(SourceDocument document) {
        document.setStatus(DocumentStatus.PROCESSING);
        document.setErrorMessage(null);
        documentRepository.saveAndFlush(document);
        try {
            Map<String, Object> result = iaClientService.ingestDocument(
                    document.getId(),
                    document.getOriginalFilename(),
                    document.getMediaType(),
                    storageService.read(document.getStorageKey())
            );
            document.setPageCount(number(result.get("page_count")));
            document.setChunkCount(number(result.get("chunks_inserted")));
            document.setStatus(DocumentStatus.INDEXED);
            document.setIndexedAt(OffsetDateTime.now());
        } catch (RuntimeException exception) {
            document.setStatus(DocumentStatus.FAILED);
            document.setErrorMessage(safeError(exception));
        }
        documentRepository.save(document);
    }

    private SourceDocument find(Long id) {
        return documentRepository.findById(id)
                .orElseThrow(() -> new EntityNotFoundException("Document introuvable."));
    }

    private DocumentResponse toResponse(SourceDocument document) {
        return new DocumentResponse(
                document.getId(),
                document.getOriginalFilename(),
                document.getMediaType(),
                document.getSizeBytes(),
                document.getSha256(),
                document.getStatus(),
                document.getUploadedBy().getUsername(),
                document.getPageCount(),
                document.getChunkCount(),
                document.getErrorMessage(),
                document.getCreatedAt(),
                document.getIndexedAt()
        );
    }

    private static Integer number(Object value) {
        return value instanceof Number number ? number.intValue() : null;
    }

    private static String safeError(RuntimeException exception) {
        String message = exception.getMessage();
        if (message == null || message.isBlank()) {
            return "L'indexation du document a échoué.";
        }
        return message.length() > 1000 ? message.substring(0, 1000) : message;
    }

    public record DownloadedDocument(Resource resource, String filename, String mediaType) {
    }
}