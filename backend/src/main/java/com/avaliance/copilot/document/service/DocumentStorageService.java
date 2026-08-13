package com.avaliance.copilot.document.service;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.FileSystemResource;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;
import java.util.Locale;
import java.util.Set;
import java.util.UUID;

@Service
public class DocumentStorageService {

    private static final Set<String> SUPPORTED_EXTENSIONS = Set.of(".pdf", ".docx", ".txt");
    private final Path root;

    public DocumentStorageService(@Value("${app.document-storage.path}") String storagePath) {
        root = Path.of(storagePath).toAbsolutePath().normalize();
        try {
            Files.createDirectories(root);
        } catch (IOException exception) {
            throw new DocumentStorageException("Impossible d'initialiser le stockage documentaire.", exception);
        }
    }

    public StoredDocument store(MultipartFile file) {
        String filename = safeFilename(file.getOriginalFilename());
        String extension = extension(filename);
        if (!SUPPORTED_EXTENSIONS.contains(extension)) {
            throw new UnsupportedDocumentTypeException(
                    "Format non pris en charge. Utilisez un fichier PDF, DOCX ou TXT.");
        }
        if (file.isEmpty()) {
            throw new IllegalArgumentException("Le document est vide.");
        }

        String storageKey = UUID.randomUUID() + extension;
        Path destination = resolve(storageKey);
        Path temporary = resolve(storageKey + ".tmp");
        try {
            byte[] bytes = file.getBytes();
            Files.write(temporary, bytes);
            Files.move(temporary, destination, StandardCopyOption.ATOMIC_MOVE);
            return new StoredDocument(
                    filename,
                    storageKey,
                    file.getContentType() == null ? "application/octet-stream" : file.getContentType(),
                    bytes.length,
                    sha256(bytes)
            );
        } catch (IOException exception) {
            try {
                Files.deleteIfExists(temporary);
            } catch (IOException ignored) {
                // Preserve the original storage exception.
            }
            throw new DocumentStorageException("Impossible de stocker le document.", exception);
        }
    }

    public byte[] read(String storageKey) {
        try {
            return Files.readAllBytes(resolve(storageKey));
        } catch (IOException exception) {
            throw new DocumentStorageException("Le fichier original est introuvable.", exception);
        }
    }

    public FileSystemResource resource(String storageKey) {
        Path path = resolve(storageKey);
        if (!Files.isRegularFile(path)) {
            throw new DocumentStorageException("Le fichier original est introuvable.", null);
        }
        return new FileSystemResource(path);
    }

    public void delete(String storageKey) {
        try {
            Files.deleteIfExists(resolve(storageKey));
        } catch (IOException exception) {
            throw new DocumentStorageException("Impossible de supprimer le fichier original.", exception);
        }
    }

    private Path resolve(String storageKey) {
        Path path = root.resolve(storageKey).normalize();
        if (!path.startsWith(root)) {
            throw new IllegalArgumentException("Clé de stockage invalide.");
        }
        return path;
    }

    private static String safeFilename(String originalFilename) {
        if (originalFilename == null || originalFilename.isBlank()) {
            throw new IllegalArgumentException("Le nom du document est obligatoire.");
        }
        String filename = originalFilename.replace('\\', '/');
        filename = filename.substring(filename.lastIndexOf('/') + 1).trim();
        if (filename.isBlank()) {
            throw new IllegalArgumentException("Le nom du document est obligatoire.");
        }
        return filename.length() > 255 ? filename.substring(filename.length() - 255) : filename;
    }

    private static String extension(String filename) {
        int dot = filename.lastIndexOf('.');
        return dot < 0 ? "" : filename.substring(dot).toLowerCase(Locale.ROOT);
    }

    private static String sha256(byte[] bytes) {
        try {
            return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException("SHA-256 indisponible.", exception);
        }
    }

    public record StoredDocument(
            String originalFilename,
            String storageKey,
            String mediaType,
            long sizeBytes,
            String sha256
    ) {
    }
}