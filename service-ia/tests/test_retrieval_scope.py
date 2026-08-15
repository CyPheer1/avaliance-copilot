"""Verification of strict PDF-only evidence isolation for the RFP engine."""

from unittest.mock import MagicMock, patch

from app.generation.service import generate_rfp_structure
from app.schemas import RetrievedChunk, RetrieveResponse, RfpRequest
from app.settings import Settings


def _settings() -> Settings:
    return Settings(
        internal_token="test-internal-token-123456",
        database_url="postgresql://test:test@localhost:5432/test",
    )


def test_rfp_never_queries_synthetic_missions_and_returns_19_sections():
    """Verify RFP pipeline never calls find_similar_missions or returns MISSION chunks."""
    request = RfpRequest(
        request_id="rfp-pdf-test",
        description="Groupe hospitalier : déployer un portail patient interopérable et sécurisé HDS avec API FHIR.",
        sector="sante",
        top_k=5,
    )

    fake_pdf_chunks = [
        RetrievedChunk(
            chunk_id=101,
            document_id=1,
            document_name="architecture_hds.pdf",
            page=4,
            corpus_scope="PDF",
            content="Les flux du portail patient sont chiffrés et conformes au référentiel HDS.",
            score=0.92,
        ),
        RetrievedChunk(
            chunk_id=102,
            document_id=1,
            document_name="architecture_hds.pdf",
            page=7,
            corpus_scope="PDF",
            content="Les interfaces API REST et FHIR permettent l'interopérabilité avec le DPI existant.",
            score=0.88,
        ),
    ]

    mock_retrieve = RetrieveResponse(
        query=request.description,
        chunks=fake_pdf_chunks,
        total_found=2,
    )

    with patch("app.retrieval.vector_search.vector_search", return_value=mock_retrieve) as mock_vector_search, \
         patch("app.similar_missions.search.find_similar_missions") as mock_find_similar:

        response = generate_rfp_structure(request, _settings())

        # 1. find_similar_missions must NEVER be called
        mock_find_similar.assert_not_called()

        # 2. vector_search was called with corpus_scope='PDF'
        assert mock_vector_search.call_count >= 1
        call_args = mock_vector_search.call_args[0][0]
        assert call_args.corpus_scope == "PDF"

        # 3. Output validation
        assert response.request_id == "rfp-pdf-test"
        assert response.evidence_validation_passed is True
        assert response.diagnostic is None
        assert response.similar_missions == []  # Completely empty, no synthetic mission leak

        # 4. 19 standard sections in exact order
        assert len(response.proposal.sections) == 19
        section_keys = [s.key for s in response.proposal.sections]
        assert section_keys[0] == "executive_summary"
        assert section_keys[1] == "context_understanding"
        assert section_keys[2] == "stakes_and_problem"
        assert section_keys[3] == "objectives_and_outcomes"
        assert section_keys[4] == "scope_inclusions"
        assert section_keys[5] == "scope_exclusions"
        assert section_keys[6] == "functional_solution"
        assert section_keys[7] == "technical_architecture"
        assert section_keys[8] == "integrations_and_interfaces"
        assert section_keys[9] == "security_compliance_governance"
        assert section_keys[10] == "methodology_phases_deliverables"
        assert section_keys[11] == "planning_and_milestones"
        assert section_keys[12] == "team_and_governance"
        assert section_keys[13] == "testing_and_acceptance"
        assert section_keys[14] == "migration_deployment_reversibility"
        assert section_keys[15] == "change_management_training"
        assert section_keys[16] == "operations_and_support"
        assert section_keys[17] == "risks_assumptions_clarifications"
        assert section_keys[18] == "references_differentiation_next_steps"

        # 5. Citations strictly point to PDF sources
        assert len(response.sources) == 2
        assert all(s.type == "internal_pdf" for s in response.sources)
        assert all(s.document_name == "architecture_hds.pdf" for s in response.sources)
        assert len(response.citations) == 2

        # 6. Quality report
        assert response.quality is not None
        assert response.quality.passed is True
        assert response.quality.section_count == 19
