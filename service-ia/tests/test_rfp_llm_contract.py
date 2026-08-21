import asyncio
from unittest.mock import AsyncMock, patch

from app.generation.rfp_proposal import _generate_batch_async
from app.schemas import RfpRequest
from app.settings import Settings


def _settings() -> Settings:
    return Settings(
        internal_token="test-internal-token-123456",
        database_url="postgresql://test:test@localhost:5432/test",
    )


def test_rfp_batch_passes_structured_schema_to_async_ollama_client():
    sections_spec = [{"key": "executive_summary", "title": "Synthèse", "budget": 120}]
    request = RfpRequest(description="Moderniser la plateforme", mode="brief")

    with patch(
        "app.generation.rfp_proposal.generate_text_async",
        new_callable=AsyncMock,
        return_value='{"sections": []}',
    ) as generate:
        sections, _ = asyncio.run(
            _generate_batch_async(request, _settings(), float("inf"), sections_spec, [], [])
        )

    assert sections == []
    assert generate.call_args.kwargs["output_schema"] is not None
