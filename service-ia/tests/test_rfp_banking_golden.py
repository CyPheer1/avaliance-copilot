"""Golden regression for authoritative banking-brief fidelity and PDF provenance."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.generation.rfp_proposal import (
    BRIEF_SECTIONS,
    RfpInputError,
    _generate_batch_async,
    _normalize_atomic_needs,
    generate_standard_rfp_async,
)
from app.generation.rfp_quality import validate_section
from app.schemas import EvidencePacket, RfpRequest, RfpSection, RfpSectionEvidence
from app.settings import Settings


BANKING_BRIEF = (
    "Banque de détail : le taux de réussite actuel est de 90 % et la latence "
    "des paiements doit rester supérieure à 800 ms pendant la migration."
)
FORBIDDEN_INVENTED_FACTS = ("92 %", "19 heures", "65 %", "6 mois")


def _settings() -> Settings:
    return Settings(
        internal_token="test-internal-token-123456",
        database_url="postgresql://test:test@localhost:5432/test",
        llm_model="test-model",
    )


def _evidence(evidence_id: str = "pdf-001", quote: str = "Réussite mesurée à 90 %.") -> RfpSectionEvidence:
    return RfpSectionEvidence(
        id=evidence_id,
        source_document_id=1,
        document_name="01_Credalis_Banque_NovaShield_Bilan_Projet.pdf",
        page=3,
        chunk_id=42,
        quote=quote,
    )


def test_banking_brief_anchor_is_verbatim_and_rejects_rewritten_values() -> None:
    needs = _normalize_atomic_needs(
        [{
            "id": "req-01",
            "text": "Atteindre 92 % avec une durée de 19 heures",
            "category": "performance",
            "priority": "MUST",
            "brief_anchor": "le taux de réussite actuel est de 90 % et la latence des paiements doit rester supérieure à 800 ms",
        }],
        BANKING_BRIEF,
    )

    assert len(needs) == 1
    assert needs[0].text == needs[0].source_excerpt
    assert "90 %" in needs[0].text
    assert "800 ms" in needs[0].text
    assert all(value not in needs[0].text for value in FORBIDDEN_INVENTED_FACTS)

    assert _normalize_atomic_needs(
        [{"id": "req-02", "text": "92 %", "brief_anchor": "taux de réussite de 92 %"}],
        BANKING_BRIEF,
    ) == []


def test_banking_brief_duplicate_anchors_create_one_coverage_obligation() -> None:
    anchor = "le taux de réussite actuel est de 90 % et la latence des paiements doit rester supérieure à 800 ms"
    needs = _normalize_atomic_needs(
        [
            {"id": "req-01", "brief_anchor": anchor, "category": "performance"},
            {"id": "req-02", "brief_anchor": anchor, "category": "architecture"},
        ],
        BANKING_BRIEF,
    )

    assert len(needs) == 1
    assert needs[0].id == "req-01"


def test_batch_prompt_retains_the_authoritative_banking_brief() -> None:
    request = RfpRequest(description=BANKING_BRIEF, mode="brief")
    needs = _normalize_atomic_needs(
        [{"id": "req-01", "text": "ignored", "brief_anchor": "le taux de réussite actuel est de 90 % et la latence des paiements doit rester supérieure à 800 ms"}],
        BANKING_BRIEF,
    )

    with patch(
        "app.generation.rfp_proposal.generate_text_async",
        new_callable=AsyncMock,
        return_value='{"sections": []}',
    ) as generate:
        asyncio.run(_generate_batch_async(request, _settings(), float("inf"), BRIEF_SECTIONS, needs, []))

    prompt = generate.call_args.kwargs["prompt"]
    assert BANKING_BRIEF in prompt
    assert "90 %" in prompt and "800 ms" in prompt
    assert "[pdf-001]" in prompt


def test_quality_gate_rejects_invented_banking_values_and_irrelevant_evidence() -> None:
    evidence = _evidence(quote="Cette référence porte sur des certificats IoT pour des capteurs industriels.")
    section = RfpSection(
        key="proposed_solution",
        title="Solution",
        body="Le taux atteindra 92 % sous 19 heures avec une cible de 65 % sous 6 mois [pdf-001].",
        evidence=[evidence],
    )

    warnings = validate_section(section, {"pdf-001": evidence, "__brief__": BANKING_BRIEF})

    assert any("92 %" in warning for warning in warnings)
    assert any("19 heures" in warning for warning in warnings)
    assert any("65 %" in warning for warning in warnings)
    assert any("6 mois" in warning for warning in warnings)
    assert any("non pertinente" in warning for warning in warnings)


def test_quality_gate_requires_resolvable_canonical_citations_without_orphans() -> None:
    evidence = _evidence(quote="La réussite mesurée est de 90 %.")
    section = RfpSection(
        key="executive_summary",
        title="Synthèse",
        body="Le taux de réussite est de 90 % [pdf-999].",
        evidence=[evidence],
    )

    warnings = validate_section(section, {"pdf-001": evidence, "__brief__": BANKING_BRIEF})

    assert any("invalide ou orpheline" in warning for warning in warnings)
    assert any("orpheline" in warning for warning in warnings)


def test_pipeline_degrades_when_retrieved_banking_evidence_is_not_cited() -> None:
    request = RfpRequest(description=BANKING_BRIEF, mode="brief")
    raw_needs = [{
        "id": "req-01",
        "text": "ignored",
        "category": "performance",
        "priority": "MUST",
        "brief_anchor": "le taux de réussite actuel est de 90 % et la latence des paiements doit rester supérieure à 800 ms",
    }]
    evidence = _evidence()
    packet = EvidencePacket(requirement_id="req-01", status="SUPPORTED", evidence=[evidence])
    sections = [
        RfpSection(key=spec["key"], title=spec["title"], body="Question de cadrage.", status="requires_clarification")
        for spec in BRIEF_SECTIONS
    ]

    with patch("app.generation.rfp_proposal._generate_call_a", return_value=({"sector": "banque", "atomic_needs": raw_needs}, 1)), \
         patch("app.generation.rfp_proposal.retrieve_for_requirements", return_value=[packet]), \
         patch("app.generation.rfp_proposal._generate_batch_async", new=AsyncMock(return_value=(sections, 1))):
        response = asyncio.run(generate_standard_rfp_async(request, _settings(), "brief"))

    assert response.status == "degraded"
    assert response.quality.passed is False
    assert response.evidence_validation_passed is False
    assert response.annexes.compliance_matrix[0].covered is False
