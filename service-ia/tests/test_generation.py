"""Tests for generic exact-evidence generation and diagnostics."""

import json
import re
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.generation.prompts import (
    INSUFFICIENT_INFORMATION,
    SYNTHESIZED_ANSWER_PROMPT,
)
from app.generation.service import (
    _ANSWER_CACHE,
    _DIAGNOSTIC_COUNTS,
    _build_streamable_answer,
    _person_role_candidates,
    _quote_source_range,
    _select_relevant_chunks,
    generate_sourced_answer,
    generate_sourced_answer_stream,
    grounding_diagnostic_counts,
)
from app.main import create_app
from app.schemas import GenerateRequest, RetrievedChunk
from app.settings import Settings

TOKEN = "test-internal-token-123456"


def _settings() -> Settings:
    return Settings(
        internal_token=TOKEN,
        database_url="postgresql://test:test@localhost:5432/test",
        min_source_similarity=0.55,
        generation_cache_max_entries=0,
    )


def _chunk(*, vector_score: float = 0.9, text_score: float = 0.0) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=11,
        mission_id=7,
        mission_title="Migration Cloud Banque",
        document_name="migration.pdf",
        page=4,
        sector="banque",
        mission_type="migration cloud",
        corpus_scope="PDF",
        request_id="test-request",
        content=(
            "La migration utilise Azure et Kubernetes. "
            "Le déploiement est automatisé avec Terraform."
        ),
        score=0.03,
        rrf_score=0.03,
        relevance_score=vector_score,
        vector_score=vector_score,
        text_score=text_score,
    )


def _supported(*evidence: tuple[int, str]) -> str:
    return json.dumps(
        {
            "status": "SUPPORTED",
            "evidence": [
                {"source": source, "quote": quote}
                for source, quote in evidence
            ],
        },
        ensure_ascii=False,
    )


def _stream_supported(*evidence: tuple[int, str]) -> str:
    answer = " ".join(
        f"{sentence.strip()} [{source}]"
        for source, quote in evidence
        for sentence in re.split(r"(?<=[.!?])\\s+", quote)
        if sentence.strip()
    )
    return json.dumps(
        {
            "status": "SUPPORTED",
            "answer": answer,
            "coverage": [
                {
                    "criterion": quote,
                    "evidence": [{"source": source, "quote": quote}],
                }
                for source, quote in evidence
            ],
        },
        ensure_ascii=False,
    )


def _sse_payloads(events: list[str]) -> list[dict]:
    payloads: list[dict] = []
    for event in events:
        for line in event.splitlines():
            if line.startswith("data: "):
                payloads.append(json.loads(line.removeprefix("data: ")))
    return payloads


def test_generate_builds_answer_from_exact_evidence_with_per_sentence_citations():
    request = GenerateRequest(query="Quelle architecture ?", chunks=[_chunk()])
    with patch(
        "app.generation.service.generate_text",
        return_value=_supported(
            (
                1,
                "La migration utilise Azure et Kubernetes. "
                "Le déploiement est automatisé avec Terraform.",
            )
        ),
    ) as generate_text:
        response = generate_sourced_answer(request, _settings())

    assert response.answer == (
        "La migration utilise Azure et Kubernetes. [1] "
        "Le déploiement est automatisé avec Terraform. [1]"
    )
    assert response.diagnostic is None
    assert response.confidence == 0.9
    assert response.validation_passed is True
    assert [(span.evidence_id, span.quote) for span in response.evidence_spans] == [
        (1, "La migration utilise Azure et Kubernetes."),
        (1, "Le déploiement est automatisé avec Terraform."),
    ]
    assert response.evidence_spans[0].source_start == 0
    assert response.evidence_spans[0].source_end == len("La migration utilise Azure et Kubernetes.")
    assert response.citations[0].page == 4
    assert generate_text.call_args.kwargs["max_tokens"] == 1500
    prompt = generate_text.call_args.args[0]
    assert "Retourne exclusivement un objet JSON valide" in prompt
    assert "copié exactement" in prompt
    assert "TOUS les critères" in prompt
    assert "budget engagé ≠ budget consommé" in prompt
    assert "NO_RELEVANT_EVIDENCE" in prompt


def test_generate_rejects_table_of_contents_evidence():
    request = GenerateRequest(query="Quelle difficulté ?", chunks=[_chunk()])
    toc_chunk = request.chunks[0].model_copy(
        update={"content": "Sommaire . . . Difficultés rencontrées . . . 16"}
    )
    with patch(
        "app.generation.service.generate_text",
        return_value=_supported((1, "Difficultés rencontrées . . . 16")),
    ):
        response = generate_sourced_answer(
            request.model_copy(update={"chunks": [toc_chunk]}), _settings()
        )

    assert response.answer == INSUFFICIENT_INFORMATION
    assert response.diagnostic == "UNSUPPORTED_ANSWER"


def test_generate_admits_exact_evidence_with_low_vector_similarity():
    request = GenerateRequest(
        query="Quelle architecture ?",
        chunks=[_chunk(vector_score=0.2, text_score=0.8)],
    )
    with patch(
        "app.generation.service.generate_text",
        return_value=_supported((1, "La migration utilise Azure et Kubernetes.")),
    ) as generate_text:
        response = generate_sourced_answer(request, _settings())

    assert response.answer == "La migration utilise Azure et Kubernetes. [1]"
    assert response.diagnostic is None
    assert response.confidence == 0.2
    generate_text.assert_called_once()


def test_synthesis_prompt_requires_complete_grounded_answer_or_exact_abstention():
    prompt = SYNTHESIZED_ANSWER_PROMPT.format(
        question="Quel est le budget engagé et le budget consommé ?",
        contexts="[E3597] Budget engagé : 100 € ; budget consommé : 105 €.",
    )

    assert "Couvre tous les éléments demandés" in prompt
    assert INSUFFICIENT_INFORMATION in prompt
    assert "budget engagé ≠ budget consommé" in prompt
    assert "[E3597]" in prompt
    assert "balise <think>" in prompt


def test_context_compaction_keeps_all_chunks_for_unclassified_question():
    chunks = [
        _chunk().model_copy(update={"chunk_id": chunk_id, "content": f"Chunk {chunk_id}"})
        for chunk_id in range(1, 6)
    ]

    assert _select_relevant_chunks("Que faut-il retenir ?", chunks) == chunks


def test_generate_reuses_cache_for_same_query_and_chunk_version():
    _ANSWER_CACHE.clear()
    settings = _settings().model_copy(update={"generation_cache_max_entries": 2})
    request = GenerateRequest(query="Quelle architecture cacheable ?", chunks=[_chunk()])
    with patch(
        "app.generation.service.generate_text",
        return_value=_supported((1, "La migration utilise Azure et Kubernetes.")),
    ) as generate_text:
        first = generate_sourced_answer(request, settings)
        second = generate_sourced_answer(request, settings)

    assert first == second
    generate_text.assert_called_once()


def test_generate_reports_no_relevant_evidence_without_chunks():
    request = GenerateRequest(query="Question sans rapport", chunks=[])
    with patch("app.generation.service.generate_text") as generate_text:
        response = generate_sourced_answer(request, _settings())

    assert response.answer == INSUFFICIENT_INFORMATION
    assert response.diagnostic == "NO_RELEVANT_EVIDENCE"
    assert response.citations == []
    assert response.evidence == []
    assert response.validation_passed is False
    generate_text.assert_not_called()


def test_generate_exposes_immutable_evidence_metadata_and_offsets():
    request = GenerateRequest(query="Quelle architecture ?", chunks=[_chunk()])
    with patch(
        "app.generation.service.generate_text",
        return_value=_supported((1, "La migration utilise Azure et Kubernetes.")),
    ):
        response = generate_sourced_answer(request, _settings())

    evidence = response.evidence[0]
    assert response.validation_passed is True
    assert evidence.evidence_id == 1
    assert evidence.chunk_id == response.citations[0].chunk_id
    assert evidence.document_name == "migration.pdf"
    assert evidence.page == 4
    assert evidence.source_start == 0
    assert evidence.source_end == len(evidence.content)


def test_generate_marks_unsupported_model_claim_as_untrusted():
    request = GenerateRequest(query="Quelle architecture ?", chunks=[_chunk()])
    with patch(
        "app.generation.service.generate_text",
        return_value=_supported((1, "Une architecture inexistante est utilisée.")),
    ):
        response = generate_sourced_answer(request, _settings())

    assert response.answer == INSUFFICIENT_INFORMATION
    assert response.diagnostic == "UNSUPPORTED_ANSWER"
    assert response.citations == []
    assert response.evidence_spans == []
    assert response.validation_passed is False


def test_generate_rejects_pdf_evidence_without_document_page_metadata():
    invalid_chunk = _chunk().model_copy(
        update={"document_id": 91, "document_name": None, "page": None}
    )
    request = GenerateRequest(query="Quelle architecture ?", chunks=[invalid_chunk])

    with patch("app.generation.service.generate_text") as generate_text:
        response = generate_sourced_answer(request, _settings())

    assert response.answer == INSUFFICIENT_INFORMATION
    assert response.diagnostic == "NO_RELEVANT_EVIDENCE"
    assert response.evidence == []
    assert response.validation_passed is False
    generate_text.assert_not_called()


def test_generate_extracts_named_project_identity_without_calling_model():
    chunk = _chunk().model_copy(
        update={
            "content": (
                "Fiche d’identité du projet Élément Valeur Client fictif Exemple "
                "Secteur Retail Type de mission SRE / observabilité Période Janvier 2025"
            )
        }
    )
    request = GenerateRequest(
        query=(
            "Dans le projet « Observabilité unifiée », quel est le secteur concerné "
            "et quel est le type de mission réalisé ?"
        ),
        chunks=[chunk],
    )

    with patch("app.generation.service.generate_text") as generate_text:
        response = generate_sourced_answer(request, _settings())

    assert response.answer == "Secteur Retail Type de mission SRE / observabilité [1]"
    assert response.citations[0].page == 4
    generate_text.assert_not_called()


def test_generate_extracts_named_project_technologies_without_calling_model():
    truncated_chunk = _chunk().model_copy(
        update={
            "content": (
                "Architecture cible Expérience et interfaces : OpenTelemetry avec instrumentation ; "
                "Services métier : Prometheus et APIs documentées ; "
                "Données : Grafana avec règles de qualité."
            )
        }
    )
    complete_chunk = truncated_chunk.model_copy(
        update={
            "chunk_id": 12,
            "content": (
                truncated_chunk.content
                + " Intégration : Loki pour les échanges ; Plateforme : Tempo avec déploiements ; "
                "Observabilité et sécurité : Kubernetes, journalisation corrélée."
            ),
        }
    )
    request = GenerateRequest(
        query="Dans le projet « Observabilité unifiée », quelles technologies composent l’architecture cible ?",
        chunks=[truncated_chunk, complete_chunk],
    )

    with patch("app.generation.service.generate_text") as generate_text:
        response = generate_sourced_answer(request, _settings())

    assert "OpenTelemetry" in response.answer
    assert "Prometheus" in response.answer
    assert "Grafana" in response.answer
    assert "Loki" in response.answer
    assert "Tempo" in response.answer
    assert "Kubernetes" in response.answer
    assert len(response.citations) == 1
    assert response.citations[0].chunk_id == 12
    generate_text.assert_not_called()


def test_generate_extracts_suffix_position_project_person_without_calling_model():
    chunk = _chunk().model_copy(
        update={
            "chunk_id": 21,
            "page": 13,
            "document_name": "02_Novacom_Telecom_Plateforme_Data_Retention_Bilan_Mission.pdf",
            "content": (
                "10. Organisation et équipe Nom Rôle Entité Charge Période "
                "Anaïs Portier Direction de projet Avaliance 70 % Janv. — Nov. 2025 "
                "Pauline Vasseur Ingénierie data — flux temps réel Avaliance 100 % Févr. — Nov. 2025 "
                "Camille Aubertin Analytics engineering Avaliance 100 % Mars — Nov. 2025"
            ),
        }
    )
    request = GenerateRequest(
        query="Qui a pris en charge la partie flux temps réel dans le projet Novacom Télécom (programme HORIZON DATA) ?",
        chunks=[chunk],
    )

    with patch("app.generation.service.generate_text") as generate_text:
        response = generate_sourced_answer(request, _settings())

    assert response.answer == "Pauline Vasseur — Ingénierie data — flux temps réel [1]"
    assert response.citations[0].chunk_id == 21
    assert response.citations[0].page == 13
    generate_text.assert_not_called()


def test_generate_extracts_named_project_metrics_without_calling_model():
    chunk = _chunk().model_copy(
        update={
            "content": (
                "À la clôture, les résultats suivants ont été observés : MTTR réduit de 74 à 29 minutes, "
                "87 % des requêtes tracées et alertes réduites de 46 %. La mission est terminée."
            )
        }
    )
    request = GenerateRequest(
        query="Dans le projet « Observabilité unifiée », quels résultats mesurables ont été obtenus ?",
        chunks=[chunk],
    )

    with patch("app.generation.service.generate_text") as generate_text:
        response = generate_sourced_answer(request, _settings())

    assert "74 à 29 minutes" in response.answer
    assert "87 %" in response.answer
    assert "46 %" in response.answer
    generate_text.assert_not_called()


def test_person_role_candidates_extract_single_matching_row():
    content = (
        "Organisation et équipe Nom Rôle Entité Charge Période "
        "Pauline Vasseur Ingénierie data — flux temps réel Avaliance 100 % Févr. — Nov. 2025"
    )

    candidates = _person_role_candidates(content, ["temps", "reel", "flux"])

    assert len(candidates) == 1
    assert candidates[0][0] == 3
    assert candidates[0][2] == "Pauline Vasseur — Ingénierie data — flux temps réel"


def test_person_role_candidates_preserve_labeled_table_row_fields():
    content = (
        "Nom: Rémi Lasalle; Rôle: Ingénierie DevOps et cloud AWS; "
        "Entité: Avaliance; Charge: 100 %; Période: Avril 2024 — Juin 2025"
    )

    candidates = _person_role_candidates(content, ["deploiement", "cloud"])

    assert candidates == [(
        1,
        0,
        "Nom: Rémi Lasalle; Rôle: Ingénierie DevOps et cloud AWS; Entité: Avaliance; Charge: 100 %; Période: Avril 2024 — Juin 2025",
    )]


def test_generate_abstains_for_ambiguous_named_project_person_evidence():
    chunk = _chunk().model_copy(
        update={
            "chunk_id": 22,
            "page": 13,
            "document_name": "02_Novacom_Telecom_Plateforme_Data_Retention_Bilan_Mission.pdf",
            "content": (
                "Organisation et équipe Nom Rôle Entité Charge Période "
                "Pauline Vasseur Ingénierie data — flux temps réel Avaliance 100 % Févr. — Nov. 2025 "
                "Lucas Martin Responsable technique flux temps réel Avaliance 100 % Janv. — Nov. 2025"
            ),
        }
    )
    request = GenerateRequest(
        query="Qui a pris en charge la partie flux temps réel dans le projet Novacom Télécom (programme HORIZON DATA) ?",
        chunks=[chunk],
    )

    with patch(
        "app.generation.service.generate_text",
        return_value=json.dumps({"status": "NO_RELEVANT_EVIDENCE", "evidence": []}),
    ) as generate_text:
        response = generate_sourced_answer(request, _settings())

    assert response.answer == INSUFFICIENT_INFORMATION
    assert response.citations == []
    generate_text.assert_called_once()


def test_generate_extracts_migration_strategy_with_routing_and_rollback_without_model():
    chunk = _chunk().model_copy(
        update={
            "chunk_id": 903,
            "document_id": 4,
            "document_name": "01_Helvia_Assurances_Refonte_Sinistres_Bilan_Projet.pdf",
            "page": 9,
            "content": (
                "## 7.1 Migration progressive plutôt que réécriture complète\n\n"
                "Une réécriture intégrale aurait immobilisé l'équipe dix-huit mois avant "
                "la première mise en production. La migration par domaines, avec routage "
                "dynamique et retour arrière préparé pour chaque livraison, a été retenue "
                "malgré son coût de coexistence, estimé à 9 % de la charge totale."
            ),
        }
    )
    request = GenerateRequest(
        query=(
            "Quelle stratégie de migration a été retenue pour la plateforme de gestion "
            "des sinistres dans le projet Helvia Assurances (programme SINAPS) ?"
        ),
        chunks=[chunk],
    )

    with patch("app.generation.service.generate_text") as generate_text:
        response = generate_sourced_answer(request, _settings())

    assert response.answer == (
        "La migration par domaines, avec routage dynamique et retour arrière préparé "
        "pour chaque livraison, a été retenue malgré son coût de coexistence, estimé "
        "à 9 % de la charge totale. [1]"
    )
    assert [(citation.chunk_id, citation.page) for citation in response.citations] == [(903, 9)]
    assert response.validation_passed is True
    generate_text.assert_not_called()


def test_generate_prefers_project_scoped_person_evidence_over_same_role_elsewhere():
    matching = _chunk().model_copy(
        update={
            "chunk_id": 231,
            "document_id": 71,
            "document_name": "Programme Atlas - bilan.pdf",
            "page": 12,
            "content": (
                "Nom: Ana Martin; Rôle: Conduite du changement et formation; "
                "Entité: Avaliance; Charge: 60%; Période: 2025"
            ),
        }
    )
    unrelated = _chunk().model_copy(
        update={
            "chunk_id": 232,
            "document_id": 72,
            "document_name": "Programme Boreal - bilan.pdf",
            "page": 12,
            "content": (
                "Nom: Bruno Durand; Rôle: Conduite du changement et formation; "
                "Entité: Avaliance; Charge: 70%; Période: 2025"
            ),
        }
    )

    response = generate_sourced_answer(
        GenerateRequest(
            query="Qui a piloté la conduite du changement et la formation dans le projet Atlas ?",
            chunks=[unrelated, matching],
        ),
        _settings(),
    )

    assert "Ana Martin" in response.answer
    assert "Bruno Durand" not in response.answer
    assert [(citation.chunk_id, citation.page) for citation in response.citations] == [(231, 12)]


def test_generate_prefers_unique_best_person_match_in_team_chunk_without_calling_model():
    chunk = _chunk().model_copy(
        update={
            "chunk_id": 23,
            "page": 13,
            "document_name": "02_Novacom_Telecom_Plateforme_Data_Retention_Bilan_Mission.pdf",
            "content": (
                "10. Organisation et équipe Nom Rôle Entité Charge Période "
                "Valérie Cazaux Sponsor — Directrice Data & Performance Novacom 15 % Janv. — Nov. 2025 "
                "Anaïs Portier Direction de projet Avaliance 70 % Janv. — Nov. 2025 "
                "Pauline Vasseur Ingénierie data — flux temps réel Avaliance 100 % Févr. — Nov. 2025 "
                "Diego Marchetti Ingénierie data — reprise des bases héritées Avaliance 100 % Mars — Août 2025"
            ),
        }
    )
    request = GenerateRequest(
        query="Qui a pris en charge la partie flux temps réel dans le projet Novacom Télécom (programme HORIZON DATA) ?",
        chunks=[chunk],
    )

    with patch("app.generation.service.generate_text") as generate_text:
        response = generate_sourced_answer(request, _settings())

    assert response.answer == "Pauline Vasseur — Ingénierie data — flux temps réel [1]"
    assert response.citations[0].chunk_id == 23
    assert response.citations[0].page == 13
    generate_text.assert_not_called()


def test_generate_extracts_unquoted_named_project_metrics_without_calling_model():
    chunk = _chunk().model_copy(
        update={
            "content": (
                "À la clôture, les résultats suivants ont été observés : taux de doublons "
                "ramené de 11,4 % à 2,1 %, complétude portée à 94 % et écart réduit à 0,8 %."
            )
        }
    )
    request = GenerateRequest(
        query=(
            "Dans le projet Référentiel client unique et qualité des données, "
            "quels sont au moins deux résultats mesurables obtenus à la fin de la mission ?"
        ),
        chunks=[chunk],
    )

    with patch("app.generation.service.generate_text") as generate_text:
        response = generate_sourced_answer(request, _settings())

    assert "11,4 %" in response.answer
    assert "94 %" in response.answer
    generate_text.assert_not_called()


def test_generate_extracts_platform_volumes_with_citation_without_calling_model():
    chunk = _chunk().model_copy(
        update={
            "chunk_id": 667,
            "page": 4,
            "document_name": "volteris.pdf",
            "content": (
                "99,1 % Taux de collecte quotidien contre 92,4 % avant. "
                "1,7 s Latence médiane de mise à disposition d’une mesure. "
                "26 M Mesures traitées par jour."
            ),
        }
    )
    request = GenerateRequest(
        query="Quels volumes la plateforme du projet Volteris Énergies (programme FLUX) traite-t-elle ?",
        chunks=[chunk],
    )

    with patch("app.generation.service.generate_text") as generate_text:
        response = generate_sourced_answer(request, _settings())

    assert "1,7 s" in response.answer
    assert "26 M" in response.answer
    assert response.citations[0].chunk_id == 667
    assert response.citations[0].page == 4
    generate_text.assert_not_called()


def test_generate_prefers_volume_and_throughput_rows_over_project_summary():
    summary = _chunk().model_copy(
        update={
            "chunk_id": 657,
            "page": 1,
            "document_name": "volteris.pdf",
            "content": "Le projet traite les résultats mesurés sur 1,14 million de compteurs.",
        }
    )
    metrics = _chunk().model_copy(
        update={
            "chunk_id": 700,
            "page": 18,
            "document_name": "volteris.pdf",
            "content": (
                "12. Résultats obtenus Indicateur Avant Après Évolution Cible atteinte "
                "Mesures traitées par jour 18,9 M 26,4 M +39,7 % Sans objet "
                "Débit soutenu en pointe 900 msg/s 4 200 msg/s ×4,7 Oui "
                "Disponibilité de la chaîne 99,31 % 99,97 % +0,66 pt Oui"
            ),
        }
    )
    request = GenerateRequest(
        query="Quelles volumétries la plateforme du projet Volteris Énergies (programme FLUX) traite-t-elle ?",
        chunks=[summary, metrics],
    )

    with patch("app.generation.service.generate_text") as generate_text:
        response = generate_sourced_answer(request, _settings())

    assert "26,4 M" in response.answer
    assert "4 200 msg/s" in response.answer
    assert response.citations[0].chunk_id == 700
    assert response.citations[0].page == 18
    assert response.citations[0].source_index == 1
    generate_text.assert_not_called()


def test_generate_extracts_named_project_solution_without_calling_model():
    noisy_test_chunk = _chunk().model_copy(
        update={
            "chunk_id": 12,
            "page": 11,
            "content": (
                "Question de test 2 : Quelle solution a été mise en œuvre ? Réponse attendue : "
                "Pipeline de rapprochement déterministe et probabiliste, règles de de rapprochement "
                "déterministe et probabiliste, règles de survivance, contrôles dbt et file de "
                "remédiation pour les data stewards."
            ),
        }
    )
    evidence_chunk = _chunk().model_copy(
        update={
            "chunk_id": 13,
            "page": 2,
            "content": (
                "Pipeline de rapprochement déterministe et probabiliste, règles de survivance, "
                "contrôles dbt et file de remédiation pour les data stewards."
            ),
        }
    )
    request = GenerateRequest(
        query=(
            "Dans le projet Référentiel client unique et qualité des données, "
            "quelle solution a été mise en œuvre pour résoudre ce problème ?"
        ),
        chunks=[noisy_test_chunk, evidence_chunk],
    )

    with patch(
        "app.generation.service.generate_text",
        side_effect=AssertionError("generate_text should not be called"),
    ) as generate_text:
        response = generate_sourced_answer(request, _settings())

    assert response.answer == f"{evidence_chunk.content} [1]"
    assert response.citations[0].page == 2
    generate_text.assert_not_called()


def test_generate_extracts_unquoted_named_project_difficulty_without_calling_model():
    chunk = _chunk().model_copy(
        update={
            "page": 9,
            "content": (
                "14. Difficultés rencontrées Les et politique de mise à jour "
                "14. Difficultés rencontrées Les rapprochements automatiques pouvaient "
                "fusionner deux personnes homonymes. Une zone grise avec validation humaine "
                "a protégé les cas ambigus. Une deuxième difficulté concernait Airflow."
            ),
        }
    )
    request = GenerateRequest(
        query=(
            "Dans le projet Référentiel client unique et qualité des données, "
            "quelle difficulté principale a été rencontrée et comment l’équipe l’a-t-elle traitée ?"
        ),
        chunks=[chunk],
    )

    with patch("app.generation.service.generate_text") as generate_text:
        response = generate_sourced_answer(request, _settings())

    assert response.answer == (
        "Les rapprochements automatiques pouvaient fusionner deux personnes homonymes. [1] "
        "Une zone grise avec validation humaine a protégé les cas ambigus. [1]"
    )
    assert response.citations[0].page == 9
    generate_text.assert_not_called()


def test_generate_extracts_project_reference_difficulty_from_natural_wording():
    chunk = _chunk().model_copy(
        update={
            "page": 9,
            "document_name": "AVA-012_referentiel_client.pdf",
            "content": (
                "14. Difficultés rencontrées Les rapprochements automatiques pouvaient "
                "fusionner deux personnes homonymes. Une zone grise avec validation humaine "
                "a protégé les cas ambigus. Une deuxième difficulté concernait Airflow."
            ),
        }
    )
    request = GenerateRequest(
        query=(
            "Comment l'équipe du projet AVA-012 a-t-elle évité le risque de fusionner "
            "par erreur des clients portant exactement le même nom ?"
        ),
        chunks=[chunk],
    )

    with patch("app.generation.service.generate_text") as generate_text:
        response = generate_sourced_answer(request, _settings())

    assert response.answer == (
        "Les rapprochements automatiques pouvaient fusionner deux personnes homonymes. [1] "
        "Une zone grise avec validation humaine a protégé les cas ambigus. [1]"
    )
    assert response.citations[0].page == 9
    generate_text.assert_not_called()


def test_generate_extracts_named_project_context_from_explicit_test_evidence():
    chunk = _chunk().model_copy(
        update={
            "page": 11,
            "content": (
                "18. Extraits exploitables pour un test de recherche "
                "Question de test 1 : Quel était le contexte principal du projet ? "
                "Réponse attendue : Les systèmes CRM, facturation et support contenaient "
                "des doublons et des adresses contradictoires. "
                "Question de test 2 : Quels résultats ont été obtenus ? "
                "Réponse attendue : Le taux de doublons a diminué."
            ),
        }
    )
    request = GenerateRequest(
        query=(
            "Dans le projet Référentiel client unique et qualité des données, "
            "quel problème principal ou quel contexte métier a motivé le lancement de la mission ?"
        ),
        chunks=[chunk],
    )

    with patch(
        "app.generation.service.generate_text",
        side_effect=AssertionError("generate_text should not be called"),
    ) as generate_text:
        response = generate_sourced_answer(request, _settings())

    assert response.answer == (
        "Les systèmes CRM, facturation et support contenaient des doublons "
        "et des adresses contradictoires. [1]"
    )
    assert response.citations[0].page == 11
    generate_text.assert_not_called()


def test_generate_reports_model_abstention():
    request = GenerateRequest(query="Quel budget ?", chunks=[_chunk()])
    with patch(
        "app.generation.service.generate_text",
        return_value=json.dumps(
            {"status": "NO_RELEVANT_EVIDENCE", "evidence": []}
        ),
    ):
        response = generate_sourced_answer(request, _settings())

    assert response.answer == INSUFFICIENT_INFORMATION
    assert response.diagnostic == "NO_RELEVANT_EVIDENCE"


def test_generate_abstains_without_model_when_explicit_alternatives_are_absent():
    chunk = _chunk().model_copy(
        update={
            "content": "La base de données PostgreSQL héberge le référentiel client.",
        }
    )
    request = GenerateRequest(
        query=(
            "Quel fournisseur Cloud (AWS, Azure ou GCP) a été choisi pour "
            "héberger PostgreSQL ?"
        ),
        chunks=[chunk],
    )

    with patch("app.generation.service.generate_text") as generate_text:
        response = generate_sourced_answer(request, _settings())

    assert response.answer == INSUFFICIENT_INFORMATION
    assert response.diagnostic == "NO_RELEVANT_EVIDENCE"
    generate_text.assert_not_called()


def test_generate_stream_abstains_without_model_when_alternatives_are_absent():
    chunk = _chunk().model_copy(
        update={
            "content": "La base de données PostgreSQL héberge le référentiel client.",
        }
    )
    request = GenerateRequest(
        query="Quel Cloud (AWS, Azure ou GCP) héberge PostgreSQL ?",
        chunks=[chunk],
    )

    with patch("app.generation.service.generate_text_stream") as generate_stream:
        events = list(generate_sourced_answer_stream(request, _settings()))

    payloads = _sse_payloads(events)
    assert any(payload.get("token") == INSUFFICIENT_INFORMATION for payload in payloads)
    assert any(payload.get("diagnostic") == "NO_RELEVANT_EVIDENCE" for payload in payloads)
    assert payloads[-1]["diagnostic"] == "NO_RELEVANT_EVIDENCE"
    assert "event: done" in events[-1]
    assert payloads[-1]["citations"] == []
    generate_stream.assert_not_called()


def test_generate_keeps_model_fallback_when_one_explicit_alternative_exists():
    request = GenerateRequest(
        query="Quel fournisseur Cloud (AWS, Azure ou GCP) a été choisi ?",
        chunks=[_chunk()],
    )
    with patch(
        "app.generation.service.generate_text",
        return_value=_supported((1, "La migration utilise Azure et Kubernetes.")),
    ) as generate_text:
        response = generate_sourced_answer(request, _settings())

    assert response.answer == "La migration utilise Azure et Kubernetes. [1]"
    generate_text.assert_called_once()


def test_generate_keeps_model_analysis_for_non_exhaustive_examples():
    chunk = _chunk().model_copy(
        update={
            "content": "La plateforme Ollama assure le service de génération.",
        }
    )
    request = GenerateRequest(
        query=(
            "Quel modèle (par exemple Llama 3, Mistral, etc.) a été déployé "
            "sur Ollama ?"
        ),
        chunks=[chunk],
    )
    with patch(
        "app.generation.service.generate_text",
        return_value=json.dumps(
            {"status": "NO_RELEVANT_EVIDENCE", "evidence": []}
        ),
    ) as generate_text:
        response = generate_sourced_answer(request, _settings())

    assert response.diagnostic == "NO_RELEVANT_EVIDENCE"
    generate_text.assert_called_once()


def test_generate_reports_unsupported_answer_when_quote_is_not_in_source():
    request = GenerateRequest(query="Quelle architecture ?", chunks=[_chunk()])
    with patch(
        "app.generation.service.generate_text",
        return_value=_supported((1, "La migration utilise un cloud privé secret.")),
    ):
        response = generate_sourced_answer(request, _settings())

    assert response.answer == INSUFFICIENT_INFORMATION
    assert response.diagnostic == "UNSUPPORTED_ANSWER"
    assert response.citations == []


def test_person_answer_combines_matching_team_and_budget_rows_on_distinct_pages():
    team = _chunk().model_copy(
        update={
            "chunk_id": 201,
            "document_id": 44,
            "page": 12,
            "content": (
                "Nom: Ana Martin; Rôle: Sécurité des équipements et certificats; "
                "Entité: Avaliance; Charge: 60%; Période: Nov. 2024 -Nov. 2025"
            ),
        }
    )
    budget = _chunk().model_copy(
        update={
            "chunk_id": 202,
            "document_id": 44,
            "page": 13,
            "content": (
                "Poste: Sécurité des équipements et gestion des certificats; "
                "Responsable / équipe: Ana Martin; Jours: 128; TJM moyen: 1 030 €; "
                "Montant HT: 131 840 €"
            ),
        }
    )

    response = generate_sourced_answer(
        GenerateRequest(
            query="Qui gérait la sécurité des équipements et les certificats dans le projet Exemple (programme PILOTE) ?",
            chunks=[team, budget],
        ),
        _settings(),
    )

    assert response.validation_passed is True
    assert response.answer.endswith("[1] Poste: Sécurité des équipements et gestion des certificats; Responsable / équipe: Ana Martin; Jours: 128; TJM moyen: 1 030 €; Montant HT: 131 840 € [2]")
    assert [(citation.chunk_id, citation.page, citation.source_index) for citation in response.citations] == [
        (201, 12, 1), (202, 13, 2)
    ]


def test_person_answer_joins_raw_team_row_with_exact_budget_person():
    team = _chunk().model_copy(
        update={
            "chunk_id": 205,
            "document_id": 45,
            "document_name": "Programme Atlas.pdf",
            "page": 12,
            "content": (
                "Organisation et équipe Nom Rôle Entité Charge Période "
                "Ana Martin Sécurité des équipements et certificats Avaliance 60 % Nov. 2024 - Nov. 2025"
            ),
        }
    )
    budget = _chunk().model_copy(
        update={
            "chunk_id": 206,
            "document_id": 45,
            "document_name": "Programme Atlas.pdf",
            "page": 13,
            "content": (
                "Poste: Sécurité des équipements et gestion des certificats; "
                "Responsable / équipe: Ana Martin; Jours: 128; TJM moyen: 1 030 €; "
                "Montant HT: 131 840 €"
            ),
        }
    )

    response = generate_sourced_answer(
        GenerateRequest(
            query="Qui gérait la sécurité des équipements et les certificats dans le projet Atlas ?",
            chunks=[team, budget],
        ),
        _settings(),
    )

    assert "Ana Martin — Sécurité des équipements et certificats [1]" in response.answer
    assert "Jours: 128" in response.answer
    assert [(citation.chunk_id, citation.page) for citation in response.citations] == [(205, 12), (206, 13)]


def test_person_answer_does_not_merge_budget_row_for_another_person():
    team = _chunk().model_copy(
        update={
            "chunk_id": 203,
            "document_id": 44,
            "page": 12,
            "content": "Nom: Ana Martin; Rôle: Sécurité applicative; Entité: Avaliance; Charge: 60%; Période: 2025",
        }
    )
    other_budget = _chunk().model_copy(
        update={
            "chunk_id": 204,
            "document_id": 44,
            "page": 13,
            "content": "Poste: Sécurité applicative; Responsable / équipe: Bruno Durand; Jours: 84; TJM moyen: 980 €; Montant HT: 82 320 €",
        }
    )

    response = generate_sourced_answer(
        GenerateRequest(
            query="Qui gérait la sécurité applicative dans le projet Exemple (programme PILOTE) ?",
            chunks=[team, other_budget],
        ),
        _settings(),
    )

    assert response.validation_passed is True
    assert response.answer.endswith("[1]")
    assert "Bruno Durand" not in response.answer
    assert [(citation.chunk_id, citation.page) for citation in response.citations] == [(203, 12)]


def test_quote_source_range_normalizes_pdf_ligatures_and_line_hyphenation():
    content = "Une solution ef\ufb01cace est déployée en multi-\ncloud avec Kubernetes."
    quote = "Une solution efficace est déployée en multicloud avec Kubernetes."

    assert _quote_source_range(content, quote) == (0, len(content))


def test_quote_source_range_normalizes_nonbreaking_and_soft_hyphen_characters():
    content = "Le\u00a0périmètre couvre la cyber\u00adsécurité et les données."
    quote = "Le périmètre couvre la cybersécurité et les données."

    assert _quote_source_range(content, quote) == (0, len(content))


def test_quote_source_range_accepts_one_typo_in_an_otherwise_exact_long_clause():
    content = (
        "Onze mois après le lancement, les campagnes de rétention ciblées affichent "
        "un taux de réussite de 23,8 %, contre 9,4 % pour les campagnes de masse précédentes."
    )
    quote = (
        "les campagnes de rétention ciblées affichent un taux de réussite de 23,8 %, "
        "contre 9,4 % pour les campagnes de masse précédantes"
    )

    source_range = _quote_source_range(content, quote)

    assert source_range is not None
    assert "précédentes" in content[source_range[0]:source_range[1]]
    assert "précédantes" not in content[source_range[0]:source_range[1]]


def test_failed_grounding_diagnostics_are_aggregated():
    _DIAGNOSTIC_COUNTS.clear()
    request = GenerateRequest(query="Quelle architecture ?", chunks=[_chunk()])
    with patch("app.generation.service.generate_text", return_value="réponse libre"):
        generate_sourced_answer(request, _settings())
        generate_sourced_answer(request, _settings())

    assert grounding_diagnostic_counts() == {"INVALID_CITATION_FORMAT": 2}


def test_generate_rejects_wrong_source_even_when_quote_exists_elsewhere():
    unrelated = _chunk().model_copy(
        update={
            "chunk_id": 12,
            "page": 1,
            "content": "Le projet concerne une plateforme bancaire.",
        }
    )
    evidence = _chunk().model_copy(update={"chunk_id": 13, "page": 2})
    request = GenerateRequest(
        query="Quelle architecture ?",
        chunks=[unrelated, evidence],
    )
    with patch(
        "app.generation.service.generate_text",
        return_value=_supported((1, "La migration utilise Azure et Kubernetes.")),
    ):
        response = generate_sourced_answer(request, _settings())

    assert response.answer == INSUFFICIENT_INFORMATION
    assert response.diagnostic == "UNSUPPORTED_ANSWER"
    assert response.citations == []


def test_generate_rejects_wrong_source_when_duplicate_quote_is_ambiguous():
    first_match = _chunk().model_copy(update={"chunk_id": 13, "page": 2})
    unrelated = _chunk().model_copy(
        update={
            "chunk_id": 14,
            "page": 3,
            "content": "Le projet concerne une plateforme bancaire.",
        }
    )
    second_match = _chunk().model_copy(update={"chunk_id": 15, "page": 4})
    request = GenerateRequest(
        query="Quelle architecture ?",
        chunks=[first_match, unrelated, second_match],
    )
    with patch(
        "app.generation.service.generate_text",
        return_value=_supported((2, "La migration utilise Azure et Kubernetes.")),
    ):
        response = generate_sourced_answer(request, _settings())

    assert response.answer == INSUFFICIENT_INFORMATION
    assert response.diagnostic == "UNSUPPORTED_ANSWER"
    assert response.citations == []


def test_generate_reports_invalid_citation_format_for_malformed_json():
    request = GenerateRequest(query="Quelle architecture ?", chunks=[_chunk()])
    with patch("app.generation.service.generate_text", return_value="réponse libre [1]"):
        response = generate_sourced_answer(request, _settings())

    assert response.answer == INSUFFICIENT_INFORMATION
    assert response.diagnostic == "INVALID_CITATION_FORMAT"


def test_generate_reports_invalid_citation_format_for_out_of_range_source():
    request = GenerateRequest(query="Quelle architecture ?", chunks=[_chunk()])
    with patch(
        "app.generation.service.generate_text",
        return_value=_supported((2, "La migration utilise Azure et Kubernetes.")),
    ):
        response = generate_sourced_answer(request, _settings())

    assert response.answer == INSUFFICIENT_INFORMATION
    assert response.diagnostic == "INVALID_CITATION_FORMAT"


def test_generate_reports_invalid_citation_format_for_unexpected_json_fields():
    request = GenerateRequest(query="Quelle architecture ?", chunks=[_chunk()])
    payload = json.loads(
        _supported((1, "La migration utilise Azure et Kubernetes."))
    )
    payload["evidence"][0]["explanation"] = "champ non autorisé"
    with patch(
        "app.generation.service.generate_text",
        return_value=json.dumps(payload, ensure_ascii=False),
    ):
        response = generate_sourced_answer(request, _settings())

    assert response.answer == INSUFFICIENT_INFORMATION
    assert response.diagnostic == "INVALID_CITATION_FORMAT"


def test_generate_accepts_json_code_fence_and_deduplicates_evidence():
    payload = _supported(
        (1, "La migration utilise Azure et Kubernetes."),
        (1, "La migration utilise Azure et Kubernetes."),
    )
    request = GenerateRequest(query="Quelle architecture ?", chunks=[_chunk()])
    with patch(
        "app.generation.service.generate_text",
        return_value=f"```json\n{payload}\n```",
    ):
        response = generate_sourced_answer(request, _settings())

    assert response.answer == "La migration utilise Azure et Kubernetes. [1]"
    assert len(response.citations) == 1


def test_deterministic_person_answer_has_valid_source_span():
    chunk = _chunk().model_copy(
        update={
            "content": "Pauline Vasseur Ingénierie data — flux temps réel Avaliance 100 %",
        }
    )
    deterministic = (
        "Pauline Vasseur — Ingénierie data — flux temps réel [1]",
        [chunk],
    )
    with patch(
        "app.generation.service._deterministic_answer", return_value=deterministic
    ):
        response = _build_streamable_answer(
            GenerateRequest(query="Qui a pris en charge les flux temps réel ?", chunks=[chunk]),
            _settings(),
            [chunk],
        )

    assert response.validation_passed is True
    assert response.evidence_spans[0].chunk_id == chunk.chunk_id
    assert response.evidence_spans[0].quote == "Pauline Vasseur — Ingénierie data — flux temps réel"


def test_stream_uses_one_structured_ollama_call_and_emits_answer_after_validation():
    request = GenerateRequest(query="Quelle architecture ?", chunks=[_chunk()])
    payload = _stream_supported((1, "La migration utilise Azure et Kubernetes."))
    split_at = payload.index("Azure") + len("Azure")
    with patch(
        "app.generation.service.generate_text",
        side_effect=AssertionError("stream path must not invoke blocking generation"),
    ) as generate_text, patch(
        "app.generation.service.generate_text_stream",
        return_value=iter([payload[:split_at], payload[split_at:]]),
    ) as generate_stream:
        events = list(generate_sourced_answer_stream(request, _settings()))

    parsed = _sse_payloads(events)
    event_names = [event.split("\n", 1)[0] for event in events]
    first_delta = event_names.index("event: delta")
    validation = event_names.index("event: validation")
    assert parsed[0]["status"] == "generating"
    assert "".join(event["token"] for event in parsed if "token" in event) == (
        "La migration utilise Azure et Kubernetes. [1]"
    )
    assert validation < first_delta
    assert next(event for event in parsed if "passed" in event)["passed"] is True
    assert parsed[-1]["diagnostic"] is None
    citation_event = next(
        payload for event, payload in zip(events, parsed) if event.startswith("event: citation")
    )
    citation = citation_event["citations"][0]
    assert citation["citationId"]
    assert citation["requestId"] == "test-request"
    assert citation["chunkId"] == 11
    assert citation["missionId"] == 7
    assert citation["missionTitle"] == "Migration Cloud Banque"
    assert citation["documentId"] is None
    assert citation["documentName"] == "migration.pdf"
    assert citation["page"] == 4
    assert citation["content"]
    assert citation["score"] > 0
    assert citation["sourceIndex"] == 1
    assert parsed[-1]["citations"] == citation_event["citations"]
    assert parsed[-1]["validationPassed"] is True
    generate_text.assert_not_called()
    generate_stream.assert_called_once()
    assert generate_stream.call_args.args[0].startswith("Tu es le contrôleur d'évidence")


def test_stream_accepts_harmless_space_before_citation_from_model_output():
    request = GenerateRequest(query="Quelle architecture ?", chunks=[_chunk()])
    payload = _stream_supported((1, "La migration utilise Azure et Kubernetes.")).replace(
        "Kubernetes. [1]", "Kubernetes.[1]"
    )
    with patch(
        "app.generation.service.generate_text_stream",
        return_value=iter([payload]),
    ):
        events = list(generate_sourced_answer_stream(request, _settings()))

    parsed = _sse_payloads(events)
    assert next(event for event in parsed if "passed" in event)["passed"] is True
    assert any("event: done" in event for event in events)


def test_quote_source_range_accepts_sentence_initial_case_difference():
    content = "Le rapport mentionne l’arrêt d’exploitation de deux jours subi."
    quote = "L’arrêt d’exploitation de deux jours subi"

    assert _quote_source_range(content, quote) is not None


def test_quote_source_range_accepts_bounded_same_source_paraphrase():
    content = "La migration utilise Azure et Kubernetes pour la plateforme cible."
    quote = "La migration s'appuie sur Azure et Kubernetes pour la plateforme cible."

    assert _quote_source_range(content, quote) == (0, len(content))


def test_stream_accepts_exact_cited_answer_when_coverage_metadata_is_malformed():
    request = GenerateRequest(query="Quelle architecture ?", chunks=[_chunk()])
    payload = json.dumps(
        {
            "status": "SUPPORTED",
            "answer": "La migration utilise Azure et Kubernetes. [1]",
            "coverage": [{"criterion": "Architecture", "evidence": []}],
        },
        ensure_ascii=False,
    )
    with patch(
        "app.generation.service.generate_text_stream", return_value=iter([payload])):
        events = list(generate_sourced_answer_stream(request, _settings()))

    parsed = _sse_payloads(events)
    assert next(event for event in parsed if "passed" in event)["passed"] is True
    assert any("event: done" in event for event in events)


def test_generate_recovers_exact_cited_answer_when_coverage_quote_has_citation():
    request = GenerateRequest(query="Quelle architecture ?", chunks=[_chunk()])
    payload = json.dumps(
        {
            "status": "SUPPORTED",
            "answer": "La migration utilise Azure et Kubernetes. [1]",
            "coverage": [
                {
                    "criterion": "Architecture Azure et Kubernetes",
                    "evidence": [
                        {
                            "source": 1,
                            "quote": "La migration utilise Azure et Kubernetes. [1]",
                        }
                    ],
                }
            ],
        },
        ensure_ascii=False,
    )
    with patch("app.generation.service.generate_text", return_value=payload):
        response = generate_sourced_answer(request, _settings())

    assert response.answer == "La migration utilise Azure et Kubernetes. [1]"
    assert response.validation_passed is True
    assert response.diagnostic is None


def test_generate_does_not_recover_uncited_answer_from_malformed_coverage():
    request = GenerateRequest(query="Quelle architecture ?", chunks=[_chunk()])
    payload = json.dumps(
        {
            "status": "SUPPORTED",
            "answer": "La migration utilise Azure et Kubernetes.",
            "coverage": [{"criterion": "Architecture", "evidence": []}],
        },
        ensure_ascii=False,
    )
    with patch("app.generation.service.generate_text", return_value=payload):
        response = generate_sourced_answer(request, _settings())

    assert response.answer == INSUFFICIENT_INFORMATION
    assert response.validation_passed is False


def test_stream_cancelled_after_status_does_not_start_model_generation():
    request = GenerateRequest(query="Quelle architecture ?", chunks=[_chunk()])
    with patch("app.generation.service.generate_text_stream") as generate_stream:
        stream = generate_sourced_answer_stream(request, _settings())
        assert "event: status" in next(stream)
        stream.close()

    generate_stream.assert_not_called()


def test_stream_returns_canonical_abstention_when_validation_fails():
    request = GenerateRequest(query="Quelle architecture ?", chunks=[_chunk()])
    with patch(
        "app.generation.service.generate_text_stream",
        return_value=iter([_stream_supported((1, "Une affirmation inventée."))]),
    ):
        events = list(generate_sourced_answer_stream(request, _settings()))

    payloads = _sse_payloads(events)
    delta_tokens = [payload["token"] for payload in payloads if "token" in payload]
    assert delta_tokens == [INSUFFICIENT_INFORMATION]
    assert not any("event: error" in event for event in events)
    done = payloads[-1]
    assert done["validationPassed"] is False
    assert done["citations"] == []
    assert done["confidence"] == 0.0


def test_generate_endpoint_requires_internal_token():
    app = create_app(_settings())
    app.router.lifespan_context = None  # type: ignore[assignment]
    response = TestClient(app).post(
        "/generate",
        json={"query": "Question", "chunks": []},
    )

    assert response.status_code == 401


def test_generate_stream_endpoint_converts_generator_failure_to_terminal_event():
    app = create_app(_settings())
    app.router.lifespan_context = None  # type: ignore[assignment]
    with patch(
        "app.generation.service.generate_sourced_answer_stream",
        side_effect=RuntimeError("connection lost"),
    ):
        response = TestClient(app, raise_server_exceptions=False).post(
            "/generate/stream",
            headers={"X-Internal-Token": TOKEN},
            json={"query": "Question", "chunks": []},
        )

    assert response.status_code == 200
    terminal_event = _sse_payloads([response.text])[0]
    assert terminal_event == {"error": "Generation stream failed"}