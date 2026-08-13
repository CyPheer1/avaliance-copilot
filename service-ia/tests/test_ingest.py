"""Tests for /ingest endpoint."""

from unittest.mock import MagicMock, patch

import numpy as np
from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import Settings

TOKEN = "test-internal-token-123456"

_SAMPLE_MISSION = {
    "id": "mission-001",
    "title": "Test Mission 001",
    "sector": "banque",
    "mission_type": "migration cloud",
    "technologies": ["Java", "Spring Boot"],
    "year": 2024,
    "referent_tag": "ref-01",
    "summary": "A synthetic test mission for ingestion testing.",
    "documents": [
        {
            "chunk_index": 0,
            "kind": "contexte projet",
            "content": "This is a test document content for chunk zero of the mission.",
        },
        {
            "chunk_index": 1,
            "kind": "note d'architecture",
            "content": "This is a second test document about architecture decisions.",
        },
    ],
}


def _make_client() -> TestClient:
    settings = Settings(
        internal_token=TOKEN,
        database_url="postgresql://test:test@localhost:5432/test",
    )
    app = create_app(settings)
    app.router.lifespan_context = None  # type: ignore[assignment]
    return TestClient(app, raise_server_exceptions=False)


def test_ingest_calls_pipeline():
    client = _make_client()

    mock_result = {
        "missions_inserted": 1,
        "chunks_inserted": 2,
        "chunks_with_embeddings": 2,
    }

    with patch("app.ingestion.pipeline.ingest_missions", return_value=mock_result) as mock_ingest:
        response = client.post(
            "/ingest",
            json={"missions": [_SAMPLE_MISSION]},
            headers={"X-Internal-Token": TOKEN},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["missions_inserted"] == 1
    assert data["chunks_inserted"] == 2
    assert data["chunks_with_embeddings"] == 2
    mock_ingest.assert_called_once()


def test_ingest_requires_auth():
    client = _make_client()

    response = client.post("/ingest", json={"missions": [_SAMPLE_MISSION]})

    assert response.status_code == 401


def test_ingest_rejects_empty_missions():
    client = _make_client()

    response = client.post(
        "/ingest",
        json={"missions": []},
        headers={"X-Internal-Token": TOKEN},
    )

    assert response.status_code == 422


def test_ingest_returns_503_when_model_not_loaded():
    client = _make_client()

    with patch(
        "app.ingestion.pipeline.ingest_missions",
        side_effect=RuntimeError("Embedding model not loaded. Cannot ingest without embeddings."),
    ):
        response = client.post(
            "/ingest",
            json={"missions": [_SAMPLE_MISSION]},
            headers={"X-Internal-Token": TOKEN},
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "Embedding model not loaded"
