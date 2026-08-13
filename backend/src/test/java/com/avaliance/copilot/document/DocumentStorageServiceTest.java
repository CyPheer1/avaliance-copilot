package com.avaliance.copilot.document;

import com.avaliance.copilot.document.service.DocumentStorageService;
import com.avaliance.copilot.document.service.DocumentStorageException;
import com.avaliance.copilot.document.service.UnsupportedDocumentTypeException;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.mock.web.MockMultipartFile;

import java.nio.file.Path;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class DocumentStorageServiceTest {

    @TempDir
    Path temporaryDirectory;

    @Test
    void storesReadsAndDeletesDocumentWithGeneratedKeyAndHash() {
        DocumentStorageService storage = new DocumentStorageService(temporaryDirectory.toString());
        byte[] content = "Mission cloud sécurisée".getBytes();
        MockMultipartFile file = new MockMultipartFile(
                "file", "mission.txt", "text/plain", content);

        DocumentStorageService.StoredDocument stored = storage.store(file);

        assertThat(stored.storageKey()).endsWith(".txt").doesNotContain("mission");
        assertThat(stored.sha256()).hasSize(64);
        assertThat(storage.read(stored.storageKey())).isEqualTo(content);
        storage.delete(stored.storageKey());
        assertThatThrownBy(() -> storage.resource(stored.storageKey()))
            .isInstanceOf(DocumentStorageException.class)
            .hasMessageContaining("introuvable");
    }

    @Test
    void rejectsLegacyDocFormat() {
        DocumentStorageService storage = new DocumentStorageService(temporaryDirectory.toString());
        MockMultipartFile file = new MockMultipartFile(
                "file", "legacy.doc", "application/msword", new byte[]{1});

        assertThatThrownBy(() -> storage.store(file))
                .isInstanceOf(UnsupportedDocumentTypeException.class)
                .hasMessageContaining("PDF, DOCX ou TXT");
    }

        @Test
        void preservesUnicodeDisplayFilenameWhileUsingGeneratedStorageKey() {
                DocumentStorageService storage = new DocumentStorageService(temporaryDirectory.toString());
                MockMultipartFile file = new MockMultipartFile(
                                "file", "Projet crédit, à valider.pdf", "application/pdf", new byte[]{1});

                DocumentStorageService.StoredDocument stored = storage.store(file);

                assertThat(stored.originalFilename()).isEqualTo("Projet crédit, à valider.pdf");
                assertThat(stored.storageKey()).doesNotContain("crédit");
        }
}