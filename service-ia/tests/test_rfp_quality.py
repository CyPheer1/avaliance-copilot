"""Quality gates for the structured, isolated RFP generation path."""

import json
from unittest.mock import patch

import pytest

from app.generation.rfp_proposal import RfpGenerationError
from app.generation.service import _extract_rfp_requirements, generate_rfp_structure
from app.schemas import RfpRequest
from app.settings import Settings


TOKEN = "test-internal-token-123456"


def _settings() -> Settings:
    return Settings(internal_token=TOKEN, database_url="postgresql://test:test@localhost:5432/test", llm_model="test-model")


def _response_for(requirements, *, omit_last: bool = False) -> str:
    needs = requirements.atomic_needs[:-1] if omit_last else requirements.atomic_needs
    sections = [
        {
            "key": f"block-{index}",
            "title": f"Décision {index}",
            "need_ids": [need.id],
            "content": [f"Nous traitons {need.text} par une décision vérifiable liée au besoin.", "Le résultat sera validé avec les responsables concernés."],
            "assumptions": [],
        }
        for index, need in enumerate(needs, start=1)
    ]
    while len(sections) < 3:
        sections.append({"key": f"block-{len(sections) + 1}", "title": "Pilotage spécifique", "need_ids": [needs[0].id], "content": ["Nous suivons les dépendances propres au périmètre.", "Les arbitrages sont documentés."], "assumptions": []})
    return json.dumps({"title": "Proposition adaptée au brief", "sections": sections}, ensure_ascii=False)


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
    generated = _response_for(requirements)
    with patch("app.generation.rfp_proposal.generate_text", return_value=generated) as model:
        response = generate_rfp_structure(RfpRequest(description=description, request_id="quality-test"), _settings())
    assert model.call_count == 1
    assert {item.need_id for item in response.coverage_report} == {need.id for need in requirements.atomic_needs}
    rendered = " ".join(item for section in response.proposal.sections for item in section.recommendations).casefold()
    assert all(term.casefold() in rendered for term in expected_terms)


def test_missing_requirement_is_retried_once_then_covered():
    description = "Consolider les données et harmoniser les KPI commerciaux."
    requirements = _extract_rfp_requirements(description, None)
    incomplete = _response_for(requirements, omit_last=True)
    complete = _response_for(requirements)
    with patch("app.generation.rfp_proposal.generate_text", side_effect=[incomplete, complete]) as model:
        response = generate_rfp_structure(RfpRequest(description=description, request_id="retry-test"), _settings())
    assert model.call_count == 2
    assert len(response.coverage_report) == len(requirements.atomic_needs)
    assert "CORRECTION OBLIGATOIRE" in model.call_args_list[1].args[0]


def test_two_invalid_generations_are_rejected_without_a_success_fallback():
    description = "Consolider les données et harmoniser les KPI commerciaux."
    requirements = _extract_rfp_requirements(description, None)
    invalid = _response_for(requirements, omit_last=True)
    with patch("app.generation.rfp_proposal.generate_text", return_value=invalid) as model:
        with pytest.raises(RfpGenerationError, match="après une nouvelle tentative"):
            generate_rfp_structure(RfpRequest(description=description, request_id="invalid-test"), _settings())
    assert model.call_count == 2


def test_question_and_generic_three_phase_proposal_are_rejected():
    requirements = _extract_rfp_requirements("Comment consolider les données et produire des KPI ?", None)
    generic = json.dumps({"title": "Bonjour", "sections": [
        {"key": "a", "title": "Cadrage", "need_ids": [requirements.atomic_needs[0].id], "content": ["Comment consolider les données et produire des KPI ?", "Validation."], "assumptions": []},
        {"key": "b", "title": "Conception", "need_ids": [requirements.atomic_needs[0].id], "content": ["Une réponse générique.", "Validation."], "assumptions": []},
        {"key": "c", "title": "Mise en œuvre", "need_ids": [requirements.atomic_needs[0].id], "content": ["Une réponse générique.", "Validation."], "assumptions": []},
    ]})
    with patch("app.generation.rfp_proposal.generate_text", return_value=generic):
        with pytest.raises(RfpGenerationError):
            generate_rfp_structure(RfpRequest(description="Comment consolider les données et produire des KPI ?", request_id="generic-test"), _settings())
