"""Comprehensive P0 RFP unit and integration test suite asserting real orchestration."""

import json
from unittest.mock import MagicMock, patch
import pytest

from app.generation.rfp_proposal import (
    generate_standard_rfp_async,
    _generate_call_a,
    _generate_batch_async,
    _repair_batch_async,
    STANDARD_SECTIONS_B,
    STANDARD_SECTIONS_C,
    BRIEF_SECTIONS,
    FULL_SECTIONS
)
from app.generation.rfp_quality import truncate_to_budget, validate_section
from app.schemas import (
    RfpRequest,
    RfpRequirements,
    RfpAtomicNeed,
    RfpSection,
    RfpBullet,
    RfpBulletAnchor
)
from app.settings import Settings
import asyncio
import time

@pytest.fixture
def mock_settings():
    return Settings(
        database_url="postgresql://copilot:test@localhost:5432/test",
        internal_token="test-token-1234567890",
        llm_model="qwen3:8b",
        min_source_similarity=0.55,
        ollama_timeout_seconds=60,
    )

def test_truncate_to_budget():
    """Test deterministic truncation."""
    section = RfpSection(
        key="executive_summary",
        title="Summary",
        body="Il est crucial de comprendre ce contexte. " + " ".join(["mot"] * 150),
        bullets=[]
    )
    # Budget for executive_summary is 120
    modified = truncate_to_budget(section, 120)
    assert modified
    assert len(section.body.split()) <= 120
    assert "crucial" not in section.body  # boilerplate removed


def test_call_a_uses_configured_sync_budget_not_legacy_twenty_seconds(mock_settings):
    request = RfpRequest(description="Test brief", mode="brief")
    mock_settings.ollama_timeout_seconds = 600
    mock_settings.rfp_sync_timeout_seconds = 180

    with patch("app.generation.rfp_proposal.generate_text", return_value='{"atomic_needs": []}') as generate:
        _generate_call_a(request, mock_settings, deadline=time.monotonic() + 185.0)

    assert generate.call_args.kwargs["timeout_seconds"] == pytest.approx(180, abs=0.01)

def test_generate_brief_mode(mock_settings):
    """Brief mode should generate exactly 4 sections."""
    req = RfpRequest(description="Test brief", mode="brief")

    with patch("app.generation.rfp_proposal._generate_call_a") as mock_call_a, \
         patch("app.generation.rfp_proposal.retrieve_for_requirements") as mock_retrieval, \
         patch("app.generation.rfp_proposal._generate_batch_async") as mock_batch, \
         patch("app.generation.rfp_proposal.validate_section") as mock_validate:

         mock_call_a.return_value = ({"sector": "IT", "atomic_needs": [{"id": "need-1", "text": "test", "category": "tech", "brief_anchor": "Test brief"}]}, 100)
         mock_retrieval.return_value = []
         mock_validate.return_value = []

         mock_batch.return_value = (
             [RfpSection(key=s["key"], title=s["title"], body="Test content", status="complete") for s in BRIEF_SECTIONS],
             200
         )

         resp = asyncio.run(generate_standard_rfp_async(req, mock_settings, "brief"))

         assert len(resp.proposal.sections) == 4
         assert mock_batch.call_count == 1
         assert resp.status == "completed"

def test_generate_standard_mode(mock_settings):
    """Standard mode should generate exactly 6 sections using 1 batch."""
    req = RfpRequest(description="Test standard", mode="standard")

    with patch("app.generation.rfp_proposal._generate_call_a") as mock_call_a, \
         patch("app.generation.rfp_proposal.retrieve_for_requirements") as mock_retrieval, \
         patch("app.generation.rfp_proposal._generate_batch_async") as mock_batch, \
         patch("app.generation.rfp_proposal.validate_section") as mock_validate:

         mock_call_a.return_value = ({"sector": "IT", "atomic_needs": [{"id": "need-1", "text": "test", "category": "tech", "brief_anchor": "Test standard"}]}, 100)
         mock_retrieval.return_value = []
         mock_validate.return_value = []

         # Mock batch returns different sections depending on the call
         async def fake_batch(*args, **kwargs):
             specs = kwargs.get("sections_spec", args[3] if len(args) > 3 else [])
             return [RfpSection(key=s["key"], title=s["title"], body="Test content", status="complete") for s in specs], 200

         mock_batch.side_effect = fake_batch

         resp = asyncio.run(generate_standard_rfp_async(req, mock_settings, "standard"))

         assert len(resp.proposal.sections) == 6
         assert mock_batch.call_count == 1
         assert resp.status == "completed"
         assert resp.metrics.section_count == 6

def test_generate_full_mode_uses_canonical_19_sections(mock_settings):
    req = RfpRequest(description="Test full", mode="full")
    with patch("app.generation.rfp_proposal._generate_call_a") as mock_call_a, \
         patch("app.generation.rfp_proposal.retrieve_for_requirements") as mock_retrieval, \
         patch("app.generation.rfp_proposal._generate_batch_async") as mock_batch, \
         patch("app.generation.rfp_proposal.validate_section", return_value=[]):
        mock_call_a.return_value = ({"sector": "IT", "atomic_needs": [{"id": "need-1", "text": "test", "category": "tech", "brief_anchor": "Test full"}]}, 100)
        mock_retrieval.return_value = []
        async def fake_batch(*args, **kwargs):
            specs = kwargs.get("sections_spec", args[3])
            return [RfpSection(key=s["key"], title=s["title"], body="Contenu de test") for s in specs], 50
        mock_batch.side_effect = fake_batch
        response = asyncio.run(generate_standard_rfp_async(req, mock_settings, "full"))
    assert len(response.proposal.sections) == 19
    assert [section.key for section in response.proposal.sections] == [spec["key"] for spec in FULL_SECTIONS]
    assert mock_batch.call_count == 7


def test_repair_logic(mock_settings):
    """Test that repair is called exactly once if violations exist and budget allows."""
    req = RfpRequest(description="Test repair", mode="brief")

    with patch("app.generation.rfp_proposal._generate_call_a") as mock_call_a, \
         patch("app.generation.rfp_proposal.retrieve_for_requirements") as mock_retrieval, \
         patch("app.generation.rfp_proposal._generate_batch_async") as mock_batch, \
         patch("app.generation.rfp_proposal._repair_batch_async") as mock_repair, \
         patch("app.generation.rfp_proposal.validate_section") as mock_validate:

         mock_call_a.return_value = ({"sector": "IT", "atomic_needs": [{"id": "need-1", "text": "test", "category": "tech", "brief_anchor": "Test repair"}]}, 100)
         mock_retrieval.return_value = []

         sections = [RfpSection(key=s["key"], title=s["title"], body="Test content", status="complete") for s in BRIEF_SECTIONS]
         mock_batch.return_value = (sections, 200)

         # Force validation to fail for the first section
         def fake_validate(s, evidence_ids):
             if s.key == "executive_summary":
                 return ["Citation canonique invalide"]
             return []
         mock_validate.side_effect = fake_validate

         mock_repair.return_value = ([RfpSection(key="executive_summary", title="Repaired", body="Repaired Content")], 100)

         resp = asyncio.run(generate_standard_rfp_async(req, mock_settings, "brief"))

         assert mock_repair.call_count == 1
         assert resp.quality.repair_attempted is True
         # If repair is successful but fake_validate still fails it, it should be degraded.
         # But mock_validate gets called on repaired section too.
         # The side effect will fail it again since key is executive_summary.
         assert resp.status == "degraded"
         assert resp.quality.passed is False
