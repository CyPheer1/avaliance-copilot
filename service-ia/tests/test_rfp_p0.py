"""Comprehensive P0 RFP unit and integration test suite asserting real orchestration."""

import json
from unittest.mock import MagicMock, patch
import pytest

from app.generation.rfp_proposal import (
    RFP_19_SECTIONS,
    RFP_WRITER_CLUSTERS,
    BriefExtractionResult,
    ClusterGenerationResult,
    PlannerResult,
    RfpGenerationError,
    RfpInfrastructureError,
    RfpInputError,
    RfpValidationError,
    _deterministic_extract_requirements,
    _deterministic_section,
    _generate_section_cluster,
    _plan_rfp_structure,
    _repair_proposal_targeted,
    _strict_parse_json,
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
        llm_model="qwen3:8b",
        min_source_similarity=0.55,
        ollama_timeout_seconds=60,
    )


# ============================================================================
# 1. Strict Raw JSON Parser Tests
# ============================================================================
def test_strict_parse_json_valid():
    """Test valid strict JSON parsing."""
    raw = '{"key": "value", "list": [1, 2, 3]}'
    parsed = _strict_parse_json(raw)
    assert parsed == {"key": "value", "list": [1, 2, 3]}


def test_strict_parse_json_rejects_think_tags():
    """Strict parser must reject <think> tags."""
    raw = '<think>I should output JSON</think>{"key": "value"}'
    with pytest.raises(ValueError, match="<think>"):
        _strict_parse_json(raw)


def test_strict_parse_json_rejects_code_fences():
    """Strict parser must reject markdown code fences."""
    raw = '```json\n{"key": "value"}\n```'
    with pytest.raises(ValueError, match="markdown code fences"):
        _strict_parse_json(raw)


def test_strict_parse_json_rejects_leading_trailing_commentary():
    """Strict parser must reject leading and trailing commentary."""
    raw = 'Here is the JSON result:\n{"key": "value"}'
    with pytest.raises(ValueError, match="leading or trailing commentary"):
        _strict_parse_json(raw)

    raw2 = '{"key": "value"}\nHope this helps!'
    with pytest.raises(ValueError, match="leading or trailing commentary"):
        _strict_parse_json(raw2)


# ============================================================================
# 2. Brief Extraction Tests & Exact Offsets
# ============================================================================
def test_extract_brief_requirements_llm_success(mock_settings):
    """Test LLM extraction with exact brief provenance and call assertion."""
    brief_text = "Groupe hospitalier : déployer un portail patient sécurisé HDS, interopérable FHIR avec le DPI."
    mock_llm_json = {
        "sector": "sante",
        "organization_type": "hopital",
        "business_problem": ["Déployer un portail patient sécurisé"],
        "project_type": ["portail web"],
        "technologies_and_constraints": ["FHIR", "HDS"],
        "security_and_compliance": ["HDS"],
        "expected_deliverables": ["Portail livré"],
        "scale": ["100k patients"],
        "timeline_and_urgency": [],
        "atomic_needs": [
            {"id": "need-01", "text": "déployer un portail patient sécurisé HDS", "category": "security", "source_excerpt": "déployer un portail patient sécurisé HDS"},
            {"id": "need-02", "text": "interopérable FHIR avec le DPI", "category": "technical", "source_excerpt": "interopérable FHIR avec le DPI"},
        ],
    }
    with patch("app.generation.rfp_proposal.generate_text", return_value=json.dumps(mock_llm_json)) as mock_gen:
        res = extract_brief_requirements(brief_text, sector=None, settings=mock_settings)
        assert mock_gen.call_count == 1
        assert res.mode == "llm"
        req = res.requirements
        assert req.sector == "sante"
        assert len(req.atomic_needs) == 2
        assert req.atomic_needs[0].id == "need-01"
        assert req.atomic_needs[0].start_offset is not None
        assert req.atomic_needs[0].end_offset is not None
        assert brief_text[req.atomic_needs[0].start_offset:req.atomic_needs[0].end_offset] == req.atomic_needs[0].source_excerpt


def test_extract_brief_requirements_llm_failure_deterministic_fallback(mock_settings):
    """Test brief extraction falls back cleanly on invalid LLM output with offsets."""
    brief_text = "Groupe hospitalier : déployer un portail patient sécurisé HDS, interopérable avec le Dossier Patient Informatisé (DPI) via des API REST et FHIR."
    with patch("app.generation.rfp_proposal.generate_text", side_effect=Exception("Ollama timeout")):
        res = extract_brief_requirements(brief_text, sector=None, settings=mock_settings)
        assert res.mode == "deterministic_fallback"
        req = res.requirements
        assert req.sector == "sante"
        assert len(req.atomic_needs) >= 2
        assert all(n.start_offset is not None and n.end_offset is not None for n in req.atomic_needs)


def test_extract_brief_empty_or_greeting_rejection(mock_settings):
    """Test that empty or greeting-only input is rejected with typed RfpInputError (HTTP 422)."""
    with pytest.raises(RfpInputError):
        extract_brief_requirements("   ", None, mock_settings)

    with pytest.raises(RfpInputError):
        extract_brief_requirements("Bonjour !", None, mock_settings)

    with pytest.raises(RfpInputError):
        extract_brief_requirements("Hello, test.", None, mock_settings)


# ============================================================================
# 3. Planner Stage Tests
# ============================================================================
def test_planner_output_structure_and_call_count(mock_settings):
    """Test planner produces 19 sections plan and asserts generate_text call count."""
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
    with patch("app.generation.rfp_proposal.generate_text", return_value=json.dumps(mock_plan)) as mock_gen:
        plan_res = _plan_rfp_structure(req, [], mock_settings, "Brief test")
        assert mock_gen.call_count == 1
        assert plan_res.mode == "llm"
        assert len(plan_res.plan) == 19
        assert "executive_summary" in plan_res.plan
        assert plan_res.plan["executive_summary"]["status"] == "complete"


# ============================================================================
# 4. Five Writer Clusters Tests
# ============================================================================
def test_five_writer_clusters_execution(mock_settings):
    """Test that the pipeline executes 5 distinct logical writer cluster calls."""
    req = RfpRequirements(
        sector="sante",
        atomic_needs=[RfpAtomicNeed(id="need-01", text="Portail HDS", category="security")],
    )
    sources = [RfpSource(id="doc-01", type="internal_pdf", title="Doc 1", excerpt="Portail patient Santélia")]

    planner_plan = {spec["key"]: {"status": "complete", "planned_topics": [spec["title"]], "allowed_source_ids": ["brief"]} for spec in RFP_19_SECTIONS}

    def fake_generate(prompt, settings, max_tokens, output_schema=None, timeout_seconds=None):
        # Return valid batch JSON for the requested sections
        keys = []
        for s in RFP_19_SECTIONS:
            if f"[{s['key']}]" in prompt:
                keys.append(s["key"])
        batch_sections = [
            {
                "key": k,
                "title": f"Title {k}",
                "status": "complete",
                "narrative": ["Prose de test."],
                "claims": [{"id": f"c-{k}", "text": "Affirmation", "kind": "recommendation", "source_ids": []}],
                "bullets": [],
                "tables": [],
                "questions": [],
            }
            for k in keys
        ]
        return json.dumps({"sections": batch_sections})

    with patch("app.generation.rfp_proposal.generate_text", side_effect=fake_generate) as mock_gen:
        results = []
        for cluster in RFP_WRITER_CLUSTERS:
            res = _generate_section_cluster(cluster, planner_plan, req, sources, mock_settings, "Brief description")
            results.append(res)

        assert mock_gen.call_count == 5
        assert all(r.mode == "llm" for r in results)
        total_sections = sum(len(r.sections) for r in results)
        assert total_sections == 19


# ============================================================================
# 5. Deterministic Validation & All-Visible-Field Checks
# ============================================================================
def test_validate_proposal_detects_unsupported_factual_commitments():
    """Test that unsupported numbers, percentages, dates, budgets, SLAs in visible prose trigger violations."""
    req = RfpRequirements(
        sector="sante",
        atomic_needs=[RfpAtomicNeed(id="need-01", text="Portail patient HDS", category="security")],
    )
    sources = []
    sections = [_deterministic_section(spec, req, sources) for spec in RFP_19_SECTIONS]

    # Inject unsupported commitments into narrative, bullets, table cells
    sections[0].narrative.append("Nous garantissons une disponibilité de 99.9% et un délai ferme de T0 + 2 semaines.")
    sections[4].bullets.append("Équipe dédiée de 4 ETP pour un budget total de 150 k€.")
    sections[13].tables = [
        RfpTable(title="Recette", columns=["Élément", "Détail"], rows=[["Garantie", "garantie de 6 mois"]])
    ]

    violations = _validate_proposal_deterministically(sections, req, sources)
    assert any("99.9%" in v for v in violations)
    assert any("T0 + 2 semaines" in v for v in violations)
    assert any("4 ETP" in v or "150 k€" in v for v in violations)
    assert any("garantie de 6 mois" in v for v in violations)


def test_validate_proposal_detects_unknown_source():
    """Test that unknown source IDs in claims trigger violations."""
    req = RfpRequirements(sector="sante", atomic_needs=[])
    sources = [RfpSource(id="doc-01", type="internal_pdf", title="Doc 1", excerpt="test")]
    sections = [_deterministic_section(spec, req, sources) for spec in RFP_19_SECTIONS]
    sections[0].claims.append(RfpClaim(id="claim-bad", text="Bad claim", kind="internal_evidence", source_ids=["doc-99"]))

    violations = _validate_proposal_deterministically(sections, req, sources)
    assert any("unknown source ID 'doc-99'" in v for v in violations)


def test_validate_proposal_detects_non_rectangular_table():
    """Test that non-rectangular tables trigger validation violations."""
    req = RfpRequirements(sector="sante", atomic_needs=[])
    sources = []
    sections = [_deterministic_section(spec, req, sources) for spec in RFP_19_SECTIONS]
    sections[0].tables = [
        RfpTable(title="Bad Table", columns=["Col 1", "Col 2"], rows=[["Val 1"], ["Val 1", "Val 2"]])
    ]

    violations = _validate_proposal_deterministically(sections, req, sources)
    assert any("length 1 != columns length 2" in v for v in violations)


# ============================================================================
# 6. Targeted Repair & Controlled Failure Tests
# ============================================================================
def test_targeted_repair_invoked_on_violations(mock_settings):
    """Test that targeted repair is invoked on violating sections and re-validated."""
    req = RfpRequirements(
        sector="sante",
        atomic_needs=[RfpAtomicNeed(id="need-01", text="Portail HDS", category="security")],
    )
    sources = [RfpSource(id="doc-01", type="internal_pdf", title="Doc 1", excerpt="Portail patient HDS")]
    sections = [_deterministic_section(spec, req, sources) for spec in RFP_19_SECTIONS]

    violations = ["Section 'executive_summary' contains unsupported factual commitment '99.9%'"]

    repaired_clean = {
        "sections": [
            {
                "key": "executive_summary",
                "title": "Synthèse exécutive",
                "status": "complete",
                "narrative": ["Accompagnement méthodologique Avaliance pour le portail patient HDS."],
                "claims": [{"id": "c-01", "text": "Portail patient HDS", "kind": "brief_fact", "source_ids": ["brief"]}],
                "bullets": [],
                "tables": [],
                "questions": [],
            }
        ]
    }

    with patch("app.generation.rfp_proposal.generate_text", return_value=json.dumps(repaired_clean)) as mock_gen:
        merged, remaining_violations = _repair_proposal_targeted(
            sections, violations, req, sources, mock_settings, "Brief test"
        )
        assert mock_gen.call_count == 1
        assert len(remaining_violations) == 0


def test_controlled_failure_after_failed_repair(mock_settings):
    """Test that remaining violations after repair raise RfpValidationError (controlled 502)."""
    req = RfpRequest(description="Groupe hospitalier : déployer un portail patient sécurisé HDS.")

    # Mock generation that returns persistent violations
    with patch("app.generation.rfp_proposal.retrieve_rfp_pdf_evidence", return_value=([], [])), \
         patch("app.generation.rfp_proposal.generate_text", side_effect=lambda *args, **kwargs: json.dumps({
        "sections": [
            {
                "key": spec["key"],
                "title": spec["title"],
                "status": "complete",
                "narrative": ["Engagement ferme de 99.9% de disponibilité sans qualification."],
                "claims": [{"id": f"c-{spec['key']}", "text": "99.9%", "kind": "recommendation", "source_ids": []}],
                "bullets": [],
                "tables": [],
                "questions": [],
            }
            for spec in RFP_19_SECTIONS
        ]
    })):
        with pytest.raises(RfpValidationError):
            generate_rfp_proposal(req, mock_settings)


# ============================================================================
# 7. Quality Ceilings & Fallback Metadata Tests
# ============================================================================
def test_no_pdf_honest_fallback_and_quality_ceiling(mock_settings):
    """Test proposal behavior and quality score ceiling when no relevant PDF exists."""
    req = RfpRequest(description="Concevoir un télescope spatial infrarouge pour l'observation des exoplanètes.", top_k=5)
    with patch("app.generation.rfp_proposal.retrieve_rfp_pdf_evidence", return_value=([], [])), \
         patch("app.generation.rfp_proposal.generate_text", side_effect=Exception("Ollama unavailable")):
        resp = generate_rfp_proposal(req, mock_settings)
        assert resp.evidence_validation_passed is False
        assert resp.diagnostic == "NO_RELEVANT_PDF_EVIDENCE"
        assert len(resp.sources) == 0
        assert len(resp.citations) == 0
        assert len(resp.similar_missions) == 0
        assert len(resp.proposal.sections) == 19
        assert resp.quality.score <= 0.70
        assert any("Aucune preuve PDF interne" in w for w in resp.quality.warnings)


def test_mixed_fallback_score_cap(mock_settings):
    """Test that mixed cluster fallback sets generation_mode='mixed_fallback' and caps score at 0.85."""
    req = RfpRequest(description="Groupe hospitalier : déployer un portail patient sécurisé HDS.")

    # Call 1 (ext): success, Call 2 (plan): success, Call 3 (clust 1): error -> fallback, rest success
    call_idx = 0
    def mixed_generate(prompt, settings, max_tokens, output_schema=None, timeout_seconds=None):
        nonlocal call_idx
        call_idx += 1
        if call_idx == 1:
            # Extraction
            return json.dumps({
                "sector": "sante",
                "atomic_needs": [{"id": "need-01", "text": "portail patient sécurisé HDS", "category": "security", "source_excerpt": "portail patient sécurisé HDS"}],
            })
        elif call_idx == 2:
            # Planner
            return json.dumps({
                "plan": [{"key": s["key"], "status": "complete", "covered_need_ids": ["need-01"], "planned_topics": [s["title"]], "allowed_source_ids": ["brief"]} for s in RFP_19_SECTIONS]
            })
        elif call_idx == 3:
            # Cluster 1 fails
            raise Exception("Cluster 1 Ollama timeout")
        else:
            # Other clusters succeed
            keys = [s["key"] for s in RFP_19_SECTIONS if f"[{s['key']}]" in prompt]
            return json.dumps({
                "sections": [{"key": k, "title": f"T {k}", "status": "complete", "narrative": ["Prose"], "claims": [], "bullets": [], "tables": [], "questions": []} for k in keys]
            })

    with patch("app.generation.rfp_proposal.retrieve_rfp_pdf_evidence", return_value=([], [])), \
         patch("app.generation.rfp_proposal.generate_text", side_effect=mixed_generate):
        resp = generate_rfp_proposal(req, mock_settings)
        assert resp.quality.generation_mode == "mixed_fallback"
        assert resp.quality.score <= 0.85
        assert len(resp.quality.failed_cluster_keys) > 0


# ============================================================================
# 8. Ollama Per-Call Timeout & Num-Predict Forwarding Tests
# ============================================================================
def test_ollama_generate_text_forwards_num_predict_and_timeout(mock_settings):
    """Test that generate_text forwards max_tokens to options.num_predict and timeout_seconds to httpx.Timeout."""
    from app.generation.ollama import generate_text

    with patch("httpx.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {"response": "Clean response"}
        mock_client.post.return_value = mock_response
        mock_client_cls.return_value.__enter__.return_value = mock_client

        generate_text(
            "Test prompt",
            mock_settings,
            max_tokens=1428,
            timeout_seconds=42.5,
        )

        # Check client timeout
        timeout_arg = mock_client_cls.call_args[1]["timeout"]
        assert timeout_arg.read == 42.5

        # Check payload num_predict
        payload = mock_client.post.call_args[1]["json"]
        assert payload["options"]["num_predict"] == 1428
