"""Tests for /retrieve endpoint."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import create_app
from app.schemas import RetrievedChunk, RetrieveResponse
from app.settings import Settings

TOKEN = "test-internal-token-123456"


def _make_client() -> TestClient:
    settings = Settings(
        internal_token=TOKEN,
        database_url="postgresql://test:test@localhost:5432/test",
    )
    app = create_app(settings)
    app.router.lifespan_context = None  # type: ignore[assignment]
    return TestClient(app, raise_server_exceptions=False)


def test_retrieve_returns_chunks():
    client = _make_client()

    mock_response = RetrieveResponse(
        query="migration cloud",
        chunks=[
            RetrievedChunk(
                chunk_id=1,
                mission_id=1,
                mission_title="Test Mission",
                sector="banque",
                mission_type="migration cloud",
                corpus_scope="PDF",
                request_id="test-request",
                content="Cloud migration content",
                score=0.85,
            ),
        ],
        total_found=1,
    )

    with patch("app.retrieval.vector_search.vector_search", return_value=mock_response):
        response = client.post(
            "/retrieve",
            json={"query": "migration cloud", "top_k": 5},
            headers={"X-Internal-Token": TOKEN},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["query"] == "migration cloud"
    assert len(data["chunks"]) == 1
    assert data["chunks"][0]["score"] == 0.85
    assert data["total_found"] == 1


def test_retrieve_requires_auth():
    client = _make_client()

    response = client.post("/retrieve", json={"query": "test"})

    assert response.status_code == 401


def test_retrieve_rejects_empty_query():
    client = _make_client()

    response = client.post(
        "/retrieve",
        json={"query": ""},
        headers={"X-Internal-Token": TOKEN},
    )

    assert response.status_code == 422


def test_retrieve_validates_top_k():
    client = _make_client()

    response = client.post(
        "/retrieve",
        json={"query": "test", "top_k": 0},
        headers={"X-Internal-Token": TOKEN},
    )

    assert response.status_code == 422


def test_retrieve_returns_503_when_model_not_loaded():
    client = _make_client()

    with patch(
        "app.retrieval.vector_search.vector_search",
        side_effect=RuntimeError("Embedding model not loaded. Call load_model() first."),
    ):
        response = client.post(
            "/retrieve",
            json={"query": "test"},
            headers={"X-Internal-Token": TOKEN},
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "Embedding model not loaded"
