"""Tests for the isolated, PDF-evidence-first RFP workflow."""

from unittest.mock import patch

from app.generation.service import _citation_for_chunk, _extract_rfp_requirements, _proposal_sections, generate_rfp_structure
from app.schemas import RetrievedChunk, RetrieveResponse, RfpCitation, RfpRequest
from app.settings import Settings

TOKEN = "test-internal-token-123456"


def _settings() -> Settings:
    return Settings(
        internal_token=TOKEN,
        database_url="postgresql://test:test@localhost:5432/test",
    )


def test_rfp_builds_adaptive_sections_and_structured_tables():
    requirements = _extract_rfp_requirements("Groupe de transport soumis à NIS2 : segmenter le réseau, déployer un SIEM et éprouver le plan de reprise avant fin d’année.", "transport")
    sections = _proposal_sections(requirements, [
        RfpCitation(
            citation_id="rfp-42", chunk_id=42, document_id=8,
            document_name="reference.pdf", page=3, content="Extrait vérifié", source_index=1,
        ),
    ])

    assert 1 <= len(sections) < 19
    assert {section.key for section in sections} >= {"executive_summary", "delivery_approach", "clarifications"}
    assert any(section.key == "security_and_resilience" for section in sections)
    assert all(reference.citation_indexes for section in sections for reference in section.verified_references)
    assert any(section.tables for section in sections)
    assert all(any(cell.strip() for row in table.rows for cell in row) for section in sections for table in section.tables)


def test_rfp_returns_safe_diagnostic_without_pdf_evidence():
    request = RfpRequest(description="Besoin inconnu hors corpus.")
    retrieval = RetrieveResponse(query=request.description, chunks=[], total_found=0)
    with patch("app.retrieval.vector_search.vector_search", return_value=retrieval):
        response = generate_rfp_structure(request, _settings())

    assert response.evidence_validation_passed is False
    assert response.diagnostic == "NO_RELEVANT_PDF_EVIDENCE"
    assert response.citations == []
    assert response.similar_missions == []