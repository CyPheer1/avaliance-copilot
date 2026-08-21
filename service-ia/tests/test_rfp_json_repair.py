import asyncio
from unittest.mock import AsyncMock, patch

from app.generation.rfp_proposal import BRIEF_SECTIONS, _generate_batch_async
from app.schemas import RfpRequest
from app.settings import Settings


def _settings() -> Settings:
    return Settings(
        internal_token="test-internal-token-123456",
        database_url="postgresql://test:test@localhost:5432/test",
    )


def _valid_sections_json() -> str:
    sections = [
        {
            "key": spec["key"],
            "title": spec["title"],
            "status": "complete",
            "body": "Contenu valide.",
            "bullets": [],
            "assumptions": [],
            "questions": [],
        }
        for spec in BRIEF_SECTIONS
    ]
    import json
    return json.dumps({"sections": sections})


def test_batch_repairs_malformed_json_once_with_json_prompt():
    request = RfpRequest(request_id="malformed-json-request", description="Brief exploitable", mode="brief")

    with patch(
        "app.generation.rfp_proposal.generate_text_async",
        new_callable=AsyncMock,
        side_effect=['{"sections": [{"key": "executive_summary"', _valid_sections_json()],
    ) as generate:
        sections, _ = asyncio.run(
            _generate_batch_async(request, _settings(), 10_000.0, BRIEF_SECTIONS, [], [])
        )

    assert len(sections) == 4
    assert generate.await_count == 2
    assert generate.await_args_list[0].kwargs["stage"] == "call_b"
    assert generate.await_args_list[1].kwargs["stage"] == "call_b_json_repair"
    assert "SORTIE INVALIDE" in generate.await_args_list[1].kwargs["prompt"]
    assert generate.await_args_list[1].kwargs["max_tokens"] == 2400
