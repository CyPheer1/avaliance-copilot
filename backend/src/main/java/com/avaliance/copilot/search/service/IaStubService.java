package com.avaliance.copilot.search.service;

import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.Map;

/**
 * Stub service for IA client to allow the backend to run in isolation for development/demo.
 * Returns deterministic French responses.
 */
@Slf4j
@Service
public class IaStubService {

    public Map<String, Object> retrieve(Map<String, Object> request) {
        log.info("[STUB] retrieve() called with request: {}", request);
        return Map.of(
            "chunks", List.of(
                Map.of(
                    "chunk_id", 101,
                    "mission_id", 1,
                    "content", "Ceci est un document de test simulé pour la mission de modernisation.",
                    "score", 0.95
                )
            )
        );
    }

    public Map<String, Object> generate(Map<String, Object> request) {
        log.info("[STUB] generate() called with request: {}", request);
        return Map.of(
            "answer", "Ceci est une réponse générée par le STUB. Le vrai service IA n'est pas connecté.",
            "confidence", 0.99,
            "citations", List.of(
                Map.of(
                    "chunk_id", 101,
                    "mission_id", 1,
                    "mission_title", "Mission de modernisation [STUB]",
                    "content", "Ceci est un document de test simulé pour la mission de modernisation.",
                    "score", 0.95
                )
            )
        );
    }

    public Map<String, Object> similar(Map<String, Object> request) {
        log.info("[STUB] similar() called with request: {}", request);
        return Map.of(
            "missions", List.of(
                Map.of(
                    "id", 1,
                    "title", "Mission Similaire [STUB]",
                    "sector", "Banque",
                    "mission_type", "Cloud",
                    "technologies", List.of("Java", "Spring Boot"),
                    "year", 2024,
                    "summary", "Ceci est une mission retournée par le STUB.",
                    "similarity_score", 0.88
                )
            )
        );
    }

    public Map<String, Object> rfp(Map<String, Object> request) {
        log.info("[STUB] rfp() called with request: {}", request);
        List<String> sectionTitles = List.of(
            "Synthèse exécutive", "Compréhension du contexte et des enjeux",
            "Hypothèses et questions de cadrage", "Solution fonctionnelle proposée",
            "Architecture technique cible", "Intégrations et interfaces",
            "Sécurité, conformité et gouvernance des données", "Approche de migration et de déploiement",
            "Phases détaillées et livrables", "Planning et jalons", "Équipe, rôles et gouvernance",
            "Stratégie de tests et de recette", "Conduite du changement et formation",
            "Exploitation, support et maintenance", "Risques, mesures de maîtrise et dépendances",
            "Résultats attendus et indicateurs", "Périmètre inclus et exclu",
            "Références internes pertinentes", "Éléments à confirmer avec le client"
        );
        List<Map<String, Object>> sections = sectionTitles.stream().map(title -> Map.<String, Object>of(
            "key", "stub-" + title.hashCode(),
            "title", title,
            "facts_from_brief", List.of("Brief traité par le mode STUB."),
            "verified_references", List.of(),
            "recommendations", List.of("Valider le cadrage avant tout engagement."),
            "assumptions_to_confirm", List.of("Les contraintes client restent à confirmer."),
            "tables", List.of()
        )).toList();
        return Map.of(
            "requirements", Map.of(),
            "proposal", Map.of("title", "Proposition de réponse (STUB)", "sections", sections),
            "citations", List.of(),
            "similar_missions", List.of(),
            "evidence_validation_passed", false,
            "diagnostic", "NO_RELEVANT_PDF_EVIDENCE"
        );
    }

    public Map<String, Object> health() {
        return Map.of("status", "ok", "mode", "stub");
    }
}
