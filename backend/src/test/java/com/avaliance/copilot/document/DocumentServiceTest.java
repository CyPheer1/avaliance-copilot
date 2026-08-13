package com.avaliance.copilot.document;

import com.avaliance.copilot.auth.entity.AppUser;
import com.avaliance.copilot.auth.repository.AppUserRepository;
import com.avaliance.copilot.document.dto.DocumentResponse;
import com.avaliance.copilot.document.entity.DocumentStatus;
import com.avaliance.copilot.document.entity.SourceDocument;
import com.avaliance.copilot.document.repository.SourceDocumentRepository;
import com.avaliance.copilot.document.service.DocumentService;
import com.avaliance.copilot.document.service.DocumentStorageService;
import com.avaliance.copilot.search.service.IaClientService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.mock.web.MockMultipartFile;

import java.util.Map;
import java.util.Optional;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

@ExtendWith(MockitoExtension.class)
class DocumentServiceTest {

    @Mock
    SourceDocumentRepository documentRepository;
    @Mock
    AppUserRepository userRepository;
    @Mock
    DocumentStorageService storageService;
    @Mock
    IaClientService iaClientService;

    DocumentService service;
    AppUser admin;
    DocumentStorageService.StoredDocument stored;

    @BeforeEach
    void setUp() {
        service = new DocumentService(documentRepository, userRepository, storageService, iaClientService);
        admin = AppUser.builder().id(7L).username("admin").role("ADMIN").passwordHash("hash").build();
        stored = new DocumentStorageService.StoredDocument(
                "mission.pdf", "generated.pdf", "application/pdf", 128, "a".repeat(64));
        when(userRepository.findByUsername("admin")).thenReturn(Optional.of(admin));
        when(storageService.store(any())).thenReturn(stored);
        when(storageService.read("generated.pdf")).thenReturn(new byte[]{1, 2, 3});
        when(documentRepository.saveAndFlush(any())).thenAnswer(invocation -> {
            SourceDocument document = invocation.getArgument(0);
            document.setId(42L);
            return document;
        });
    }

    @Test
    void uploadMarksDocumentIndexedWithIaCounts() {
        when(iaClientService.ingestDocument(42L, "mission.pdf", "application/pdf", new byte[]{1, 2, 3}))
                .thenReturn(Map.of("page_count", 4, "chunks_inserted", 12));

        DocumentResponse response = service.upload(file(), "admin");

        assertThat(response.status()).isEqualTo(DocumentStatus.INDEXED);
        assertThat(response.pageCount()).isEqualTo(4);
        assertThat(response.chunkCount()).isEqualTo(12);
        assertThat(response.errorMessage()).isNull();
        verify(documentRepository, atLeastOnce()).save(any(SourceDocument.class));
    }

    @Test
    void uploadRetainsDocumentAndMarksFailedWhenIaRejectsIt() {
        when(iaClientService.ingestDocument(anyLong(), anyString(), anyString(), any()))
                .thenThrow(new IllegalStateException("Ce PDF ne contient pas de texte exploitable."));

        DocumentResponse response = service.upload(file(), "admin");

        assertThat(response.status()).isEqualTo(DocumentStatus.FAILED);
        assertThat(response.errorMessage()).contains("pas de texte exploitable");
        verify(storageService, never()).delete(anyString());
    }

    private MockMultipartFile file() {
        return new MockMultipartFile("file", "mission.pdf", "application/pdf", new byte[]{1, 2, 3});
    }
}