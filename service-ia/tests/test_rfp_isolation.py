"""Regression tests proving sequential RFP briefs do not share generated content."""

import json
from unittest.mock import patch

from app.generation.rfp_proposal import RfpGenerationError
from app.generation.service import _extract_rfp_requirements, generate_rfp_structure
from app.schemas import RfpRequest
from app.settings import Settings


FORBIDDEN_DATA_RESPONSE_TERMS = (
    "nis2",
    "segmentation",
    "mfa",
    "siem",
    "actifs critiques",
    "échéance réglementaire",
    "exercice de reprise",
)


def _settings() -> Settings:
    return Settings(
        internal_token="test-internal-token-123456",
        database_url="postgresql://test:test@localhost:5432/test",
    )


def _response_text(response) -> str:
    return " ".join([response.proposal.title, *[item for section in response.proposal.sections for item in [section.title, *section.facts_from_brief, *section.recommendations]]]).casefold()


def _model_response(requirements) -> str:
    sections = [{"key": f"block-{index}", "title": f"Décision {index}", "need_ids": [need.id], "content": [need.text, "Le résultat attendu est vérifié avec les responsables."], "assumptions": []} for index, need in enumerate(requirements.atomic_needs, 1)]
    while len(sections) < 3:
        sections.append({"key": f"block-{len(sections)}", "title": "Pilotage", "need_ids": [requirements.atomic_needs[0].id], "content": ["Les dépendances sont tracées.", "Les décisions sont documentées."], "assumptions": []})
    return json.dumps({"title": "Proposition adaptée", "sections": sections}, ensure_ascii=False)


def test_data_brief_does_not_inherit_nis2_content_after_prior_request():
    nis2 = RfpRequest(
        request_id="nis2-request",
        description=(
            "NIS2 : segmenter le réseau, généraliser MFA, centraliser les journaux "
            "dans un SIEM et préparer un exercice de reprise."
        ),
    )
    data = RfpRequest(
        request_id="data-request",
        description=(
            "Nous consolidons quatorze bases de données afin de produire des KPI commerciaux "
            "unifiés et des rapports d'attrition clients. Databricks est une option à confirmer."
        ),
    )

    with patch("app.generation.rfp_proposal.generate_text", side_effect=lambda _prompt, _settings, **_kwargs: _model_response(_extract_rfp_requirements(nis2.description if "nis2" in _prompt.casefold() else data.description, None))):
        first = generate_rfp_structure(nis2, _settings())
        second = generate_rfp_structure(data, _settings())

    assert first.request_id == "nis2-request"
    assert second.request_id == "data-request"
    rendered = _response_text(second)
    assert "quatorze bases de données" in rendered
    assert "kpi commerciaux" in rendered
    assert all(term not in rendered for term in FORBIDDEN_DATA_RESPONSE_TERMS)
    assert second.citations == []
    assert second.similar_missions == []


def test_blank_or_greeting_only_brief_has_no_deterministic_fallback():
    with patch("app.generation.rfp_proposal.generate_text") as model:
        try:
            generate_rfp_structure(RfpRequest(request_id="greeting", description="Bonjour"), _settings())
        except RfpGenerationError:
            pass
        else:
            raise AssertionError("A greeting-only brief must not produce a fallback proposal")
    model.assert_not_called()
