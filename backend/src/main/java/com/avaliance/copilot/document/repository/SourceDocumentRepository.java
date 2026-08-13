package com.avaliance.copilot.document.repository;

import com.avaliance.copilot.document.entity.SourceDocument;
import org.springframework.data.jpa.repository.JpaRepository;

public interface SourceDocumentRepository extends JpaRepository<SourceDocument, Long> {
}