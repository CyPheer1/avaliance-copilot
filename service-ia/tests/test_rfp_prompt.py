"""Tests for explicit RFP evidence provenance."""

from app.generation.service import _citation_for_chunk, _proposal_sections
from app.schemas import RetrievedChunk, RfpRequirements


def test_rfp_verified_claims_reference_explicit_citation_indexes():
    citation = _citation_for_chunk(
        RetrievedChunk(
            chunk_id=7, document_id=5, document_name="reference.pdf", page=2,
            corpus_scope="PDF", content="Extrait PDF vérifié.", score=0.9,
        ),
        1,
    )
    assert citation is not None
    sections = _proposal_sections(RfpRequirements(), [citation])
    verified_claims = [claim for section in sections for claim in section.verified_references]
    assert verified_claims
    assert all(claim.citation_indexes == [1] for claim in verified_claims)
    assert all("[1]" not in claim.text for claim in verified_claims)
