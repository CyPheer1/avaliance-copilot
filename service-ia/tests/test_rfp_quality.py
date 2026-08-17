"""Quality gates for the structured, isolated RFP generation path."""

import json
from unittest.mock import patch

import pytest

from app.generation.rfp_proposal import (
    RFP_19_SECTIONS,
    RfpGenerationError,
    RfpInputError,
    RfpValidationError,
)
from app.generation.service import _extract_rfp_requirements, generate_rfp_structure
from app.schemas import RfpRequest
from app.settings import Settings


TOKEN = "test-internal-token-123456"


def _settings() -> Settings:
    return Settings(internal_token=TOKEN, database_url="postgresql://test:test@localhost:5432/test", llm_model="test-model")


def _response_for(requirements) -> str:
    sections = [
        {
            "key": spec["key"],
            "title": spec["title"],
            "status": "complete",
            "narrative": [f"Traitement pour {requirements.atomic_needs[0].text}."],
            "claims": [{"id": f"c-{spec['key']}", "text": requirements.atomic_needs[0].text, "kind": "recommendation", "source_ids": []}],
            "bullets": [],
            "tables": [],
            "questions": [],
        }
        for spec in RFP_19_SECTIONS
    ]
    return json.dumps({"sections": sections}, ensure_ascii=False)


@pytest.mark.parametrize("description,expected_terms", [
    ("Consolider des bases de données, harmoniser les KPI et produire un reporting chaque lundi. Databricks reste une option à évaluer.", ("consolider", "kpi", "lundi", "databricks")),
    ("Respecter NIS2, segmenter le réseau, déployer MFA et centraliser les journaux SIEM.", ("nis2", "segmenter", "mfa", "siem")),
    ("Migrer l'application vers le cloud, préserver l'historique et sécuriser les API.", ("migrer", "historique", "api")),
    ("Créer un portail patient interopérable avec les contraintes HDS et des interfaces API.", ("portail", "interopérable", "hds", "api")),
    ("Refondre le portail client, réduire les doublons d'identité et améliorer la qualité des données.", ("portail", "doublons", "qualité")),
    ("Mettre en place une gouvernance des données, les livrables de recette et un registre des risques.", ("gouvernance", "livrables", "risques")),
])
def test_six_briefs_are_covered_by_a_tailored_model_response(description, expected_terms):
    requirements = _extract_rfp_requirements(description, None)
    assert requirements.atomic_needs
    with patch("app.generation.rfp_proposal.retrieve_rfp_pdf_evidence", return_value=([], [])), \
         patch("app.generation.rfp_proposal.generate_text", side_effect=Exception("Deterministic fallback")):
        response = generate_rfp_structure(RfpRequest(description=description, request_id="quality-test"), _settings())
    assert len(response.proposal.sections) == 19
    rendered = " ".join(item for section in response.proposal.sections for item in section.recommendations + section.narrative + section.facts_from_brief).casefold()
    assert all(term.casefold() in rendered for term in expected_terms)


def test_invalid_generations_are_rejected_without_a_success_fallback():
    description = "Consolider les données et harmoniser les KPI commerciaux."
    # When persistent violations exist after repair, RfpValidationError is raised
    with patch("app.generation.rfp_proposal.retrieve_rfp_pdf_evidence", return_value=([], [])), \
         patch("app.generation.rfp_proposal.generate_text", side_effect=lambda *args, **kwargs: json.dumps({
        "sections": [
            {
                "key": spec["key"],
                "title": spec["title"],
                "status": "complete",
                "narrative": ["Engagement ferme de 99.9% de disponibilité."],
                "claims": [{"id": f"c-{spec['key']}", "text": "99.9%", "kind": "recommendation", "source_ids": []}],
                "bullets": [],
                "tables": [],
                "questions": [],
            }
            for spec in RFP_19_SECTIONS
        ]
    })):
        with pytest.raises(RfpValidationError):
            generate_rfp_structure(RfpRequest(description=description, request_id="invalid-test"), _settings())


def test_greeting_proposal_is_rejected():
    with patch("app.generation.rfp_proposal.generate_text"):
        with pytest.raises((RfpInputError, RfpGenerationError, ValueError)):
            generate_rfp_structure(RfpRequest(description="Bonjour !", request_id="greeting-test"), _settings())
