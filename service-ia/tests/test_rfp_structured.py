"""Focused tests for the isolated structured RFP helpers."""

from app.generation.service import _citation_for_chunk, _extract_rfp_requirements, _proposal_sections
from app.schemas import RetrievedChunk, RfpCitation


def _pdf_chunk() -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=42, document_id=8, document_name="reference-sante.pdf", page=3,
        corpus_scope="PDF", content="Le portail patient doit respecter les contraintes HDS et les interfaces API.", score=0.9,
    )


def test_requirement_extraction_identifies_healthcare_constraints():
    requirements = _extract_rfp_requirements(
        "Un établissement de santé souhaite un portail patient HDS avec API et une échéance de financement.", None,
    )
    assert requirements.sector == "sante"
    assert requirements.security_and_compliance
    assert requirements.technologies_and_constraints
    assert requirements.timeline_and_urgency


def test_citation_requires_complete_pdf_provenance():
    assert _citation_for_chunk(_pdf_chunk(), 1) is not None
    assert _citation_for_chunk(_pdf_chunk().model_copy(update={"page": None}), 1) is None


def test_proposal_has_adaptive_sections_and_structured_tables():
    requirements = _extract_rfp_requirements("Portail patient HDS avec API.", "santé")
    sections = _proposal_sections(requirements, [
        RfpCitation(citation_id="rfp-42", chunk_id=42, document_id=8, document_name="reference.pdf", page=3, content="Extrait vérifié", source_index=1),
    ])
    assert len(sections) == 19
    assert {section.key for section in sections} >= {"executive_summary", "methodology_phases_deliverables", "risks_assumptions_clarifications"}
    assert any(reference.citation_indexes for section in sections for reference in section.verified_references)
    assert any(section.tables for section in sections)
    assert all(table.columns for section in sections for table in section.tables)
