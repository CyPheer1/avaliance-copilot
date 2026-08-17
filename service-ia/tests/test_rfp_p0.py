"""Comprehensive P0 RFP unit and integration test suite."""

import json
from unittest.mock import MagicMock, patch
import pytest

from app.generation.rfp_proposal import (
    RFP_19_SECTIONS,
    RfpGenerationError,
    _deterministic_extract_requirements,
    _deterministic_section,
    _plan_rfp_structure,
    _validate_proposal_deterministically,
    extract_brief_requirements,
    generate_rfp_proposal,
    retrieve_rfp_pdf_evidence,
    validate_and_repair_proposal,
)
from app.schemas import (
    RetrievedChunk,
    RetrieveRequest,
    RetrieveResponse,
    RfpAtomicNeed,
    RfpClaim,
    RfpRequest,
    RfpRequirements,
    RfpSection,
    RfpSource,
    RfpTable,
)
from app.settings import Settings


@pytest.fixture
def mock_settings():
    return Settings(
        database_url="postgresql://copilot:test@localhost:5432/test",
        internal_token="test-token-1234567890",
        llm_model="mistral-nemo:12b-instruct-2407-q8_0",
        min_source_similarity=0.55,
    )


# ============================================================================
# 1. Brief Extraction Tests
# ============================================================================
def test_extract_brief_requirements_llm_success(mock_settings):
    """Test LLM extraction when model returns structured requirements."""
    mock_llm_json = {
        "sector": "sante",
        "organization_type": "hopital",
        "business_problem": ["Déployer un portail patient sécurisé"],
        "project_type": ["portail web"],
        "technologies_and_constraints": ["FHIR", "HDS"],
        "security_and_compliance": ["HDS", "ProSanté Connect"],
        "expected_deliverables": ["Portail livré"],
        "scale": ["100k patients"],
        "timeline_and_urgency": [],
        "atomic_needs": [
            {"id": "need-01", "text": "Déployer un portail patient sécurisé HDS", "category": "security", "source_excerpt": "portail patient HDS"},
            {"id": "need-02", "text": "Interopérabilité FHIR avec le DPI", "category": "technical", "source_excerpt": "interopérable FHIR"},
        ],
    }
    with patch("app.generation.rfp_proposal.generate_text", return_value=json.dumps(mock_llm_json)):
        req = extract_brief_requirements(
            "Groupe hospitalier : déployer un portail patient sécurisé HDS, interopérable FHIR avec le DPI.",
            sector=None,
            settings=mock_settings,
        )
        assert req.sector == "sante"
        assert len(req.atomic_needs) == 2
        assert req.atomic_needs[0].id == "need-01"


def test_extract_brief_requirements_llm_failure_deterministic_fallback(mock_settings):
    """Test that brief extraction falls back cleanly to deterministic extraction on invalid LLM output."""
    with patch("app.generation.rfp_proposal.generate_text", side_effect=Exception("Ollama timeout")):
        req = extract_brief_requirements(
            "Groupe hospitalier : déployer un portail patient sécurisé HDS, interopérable avec le Dossier Patient Informatisé (DPI) via des API REST et FHIR.",
            sector=None,
            settings=mock_settings,
        )
        assert req.sector == "sante"
        assert len(req.atomic_needs) >= 2
        assert any("hds" in n.text.lower() or "portail" in n.text.lower() for n in req.atomic_needs)


def test_extract_brief_empty_or_greeting_rejection(mock_settings):
    """Test that empty or greeting-only input is rejected."""
    with pytest.raises(RfpGenerationError):
        extract_brief_requirements("   ", None, mock_settings)

    with pytest.raises(RfpGenerationError):
        extract_brief_requirements("Bonjour !", None, mock_settings)


# ============================================================================
# 2. Planner Stage Tests
# ============================================================================
def test_planner_output_structure(mock_settings):
    """Test planner produces the 19 section plans with statuses and allowed source IDs."""
    mock_plan = {
        "plan": [
            {
                "key": spec["key"],
                "status": "complete",
                "status_reason": None,
                "covered_need_ids": ["need-01"],
                "planned_topics": ["Sujet principal"],
                "allowed_source_ids": ["brief"],
            }
            for spec in RFP_19_SECTIONS
        ]
    }
    req = RfpRequirements(
        sector="sante",
        atomic_needs=[RfpAtomicNeed(id="need-01", text="Portail HDS", category="security")],
    )
    with patch("app.generation.rfp_proposal.generate_text", return_value=json.dumps(mock_plan)):
        plan = _plan_rfp_structure(req, [], mock_settings, "Brief test")
        assert len(plan) == 19
        assert "executive_summary" in plan
        assert plan["executive_summary"]["status"] == "complete"


# ============================================================================
# 3. Deterministic Validation & Rules Tests
# ============================================================================
def test_validate_proposal_detects_unknown_source():
    """Test that unknown source IDs are detected as violations."""
    req = RfpRequirements(sector="sante", atomic_needs=[])
    sources = [RfpSource(id="doc-01", type="internal_pdf", title="Doc 1", excerpt="test")]
    sections = [_deterministic_section(spec, req, sources) for spec in RFP_19_SECTIONS]
    # Inject unknown source in section 1
    sections[0].claims.append(RfpClaim(id="claim-bad", text="Bad claim", kind="internal_evidence", source_ids=["doc-99"]))

    violations = _validate_proposal_deterministically(sections, req, sources)
    assert any("unknown source ID 'doc-99'" in v for v in violations)


def test_validate_proposal_detects_non_rectangular_table():
    """Test that non-rectangular tables trigger validation violations."""
    req = RfpRequirements(sector="sante", atomic_needs=[])
    sources = []
    sections = [_deterministic_section(spec, req, sources) for spec in RFP_19_SECTIONS]
    # Inject non-rectangular table
    sections[0].tables = [
        RfpTable(title="Bad Table", columns=["Col 1", "Col 2"], rows=[["Val 1"], ["Val 1", "Val 2"]])
    ]

    violations = _validate_proposal_deterministically(sections, req, sources)
    assert any("length 1 != columns length 2" in v for v in violations)


def test_validate_proposal_detects_missing_not_applicable_reason():
    """Test that not_applicable without status_reason is flagged."""
    req = RfpRequirements(sector="sante", atomic_needs=[])
    sources = []
    sections = [_deterministic_section(spec, req, sources) for spec in RFP_19_SECTIONS]
    sections[14].status = "not_applicable"
    sections[14].status_reason = None

    violations = _validate_proposal_deterministically(sections, req, sources)
    assert any("lacks a required status_reason" in v for v in violations)


def test_unique_claim_ids_across_all_sections(mock_settings):
    """Test that all claims have unique IDs across all 19 sections."""
    req = RfpRequirements(
        sector="sante",
        atomic_needs=[RfpAtomicNeed(id="need-01", text="Portail HDS", category="security")],
    )
    sources = [RfpSource(id="doc-01", type="internal_pdf", title="Doc 1", excerpt="test")]
    raw_sections = [_deterministic_section(spec, req, sources) for spec in RFP_19_SECTIONS]

    ordered, quality, coverage = validate_and_repair_proposal(
        raw_sections, req, sources, mock_settings, "Brief test"
    )

    all_ids = []
    for s in ordered:
        for c in s.claims:
            if c.id:
                all_ids.append(c.id)

    assert len(all_ids) == len(set(all_ids)), "Claim IDs must be globally unique"


# ============================================================================
# 4. Evidence Retrieval & Isolation Tests
# ============================================================================
def test_retrieve_rfp_pdf_evidence_filters_unrelated(mock_settings):
    """Test that chunks below relevance threshold are rejected."""
    mock_chunks = [
        # High relevance chunk (cosine 0.82)
        RetrievedChunk(
            chunk_id=101,
            document_id=1,
            document_name="05_Groupe_Santelia.pdf",
            page=1,
            sector="sante",
            mission_type="portail",
            corpus_scope="PDF",
            content="Portail patient Santélia...",
            score=0.015,
            rrf_score=0.015,
            relevance_score=0.82,
            vector_score=0.82,
            text_score=2.5,
        ),
        # Low relevance chunk (cosine 0.42, low text score 0.2)
        RetrievedChunk(
            chunk_id=202,
            document_id=2,
            document_name="02_Logistique.pdf",
            page=4,
            sector="logistique",
            mission_type="wms",
            corpus_scope="PDF",
            content="Gestion des stocks en entrepôt...",
            score=0.005,
            rrf_score=0.005,
            relevance_score=0.42,
            vector_score=0.42,
            text_score=0.2,
        ),
    ]
    mock_resp = RetrieveResponse(query="Portail patient HDS", chunks=mock_chunks, total_found=2)
    with patch("app.retrieval.vector_search.vector_search", return_value=mock_resp):
        citations, sources = retrieve_rfp_pdf_evidence("Portail patient HDS", "sante", 5, mock_settings)
        assert len(sources) == 1
        assert sources[0].chunk_id == 101
        assert sources[0].document_name == "05_Groupe_Santelia.pdf"


def test_production_rfp_never_queries_synthetic_missions(mock_settings):
    """Verify that retrieve_rfp_pdf_evidence passes corpus_scope='PDF' only."""
    with patch("app.retrieval.vector_search.vector_search") as mock_search:
        mock_search.return_value = RetrieveResponse(query="Question test", chunks=[], total_found=0)
        retrieve_rfp_pdf_evidence("Question test", "banque", 5, mock_settings)
        assert mock_search.called
        call_req: RetrieveRequest = mock_search.call_args[0][0]
        assert call_req.corpus_scope == "PDF"


def test_no_pdf_honest_fallback_and_quality(mock_settings):
    """Test proposal behavior when no relevant PDF exists."""
    req = RfpRequest(description="Concevoir un télescope spatial infrarouge pour l'observation des exoplanètes.", top_k=5)
    with patch("app.generation.rfp_proposal.retrieve_rfp_pdf_evidence", return_value=([], [])):
        resp = generate_rfp_proposal(req, mock_settings)
        assert resp.evidence_validation_passed is False
        assert resp.diagnostic == "NO_RELEVANT_PDF_EVIDENCE"
        assert len(resp.sources) == 0
        assert len(resp.citations) == 0
        assert len(resp.similar_missions) == 0
        assert len(resp.proposal.sections) == 19
        assert resp.quality.citation_integrity is None or resp.quality.citation_integrity == 0.0
        assert resp.quality.score == 0.7
        assert len(resp.quality.warnings) >= 1
        assert "Aucune preuve PDF interne" in resp.quality.warnings[0]
