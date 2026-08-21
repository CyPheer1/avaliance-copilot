"""Regression tests for the active canonical RFP pipeline."""

import asyncio
from unittest.mock import patch

import pytest

from app.generation.rfp_proposal import FULL_SECTIONS, RfpInputError, generate_standard_rfp_async
from app.schemas import RfpRequest
from app.settings import Settings


TOKEN = "test-internal-token-123456"


def _settings() -> Settings:
    return Settings(
        internal_token=TOKEN,
        database_url="postgresql://test:test@localhost:5432/test",
        llm_model="test-model",
    )


def test_full_contract_has_exactly_nineteen_unique_canonical_sections() -> None:
    assert len(FULL_SECTIONS) == 19
    assert len({section["key"] for section in FULL_SECTIONS}) == 19
    assert all(section["budget"] > 0 for section in FULL_SECTIONS)


def test_empty_call_a_requirements_fail_explicitly() -> None:
    request = RfpRequest(description="Bonjour !", mode="brief", request_id="quality-test")
    with patch("app.generation.rfp_proposal._generate_call_a", return_value=({"atomic_needs": []}, 1)):
        with pytest.raises(RfpInputError):
            asyncio.run(generate_standard_rfp_async(request, _settings(), "brief"))


def test_active_pipeline_does_not_depend_on_legacy_module() -> None:
    # The public generator is intentionally implemented in rfp_proposal.py;
    # legacy code can remain on disk without becoming a runtime dependency.
    import app.generation.rfp_proposal as proposal

    assert "rfp_proposal_legacy" not in proposal.__dict__
