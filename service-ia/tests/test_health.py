"""Tests for /health endpoint."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import create_app
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


def test_health_accepts_valid_internal_token():
    client = _make_client()

    response = client.get("/health", headers={"X-Internal-Token": TOKEN})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "service-ia"


def test_health_rejects_missing_internal_token():
    client = _make_client()

    response = client.get("/health")

    assert response.status_code == 401


def test_health_rejects_invalid_internal_token():
    client = _make_client()

    response = client.get("/health", headers={"X-Internal-Token": "wrong-token-value"})

    assert response.status_code == 403


def test_ready_requires_database_and_embedding_model():
    client = _make_client()

    with patch("app.db.is_initialized", return_value=False), \
         patch("app.embeddings.is_loaded", return_value=True):
        response = client.get("/ready", headers={"X-Internal-Token": TOKEN})
    assert response.status_code == 503
    assert response.json()["detail"] == "Database pool not initialized"

    with patch("app.db.is_initialized", return_value=True), \
         patch("app.embeddings.is_loaded", return_value=False):
        response = client.get("/ready", headers={"X-Internal-Token": TOKEN})
    assert response.status_code == 503
    assert response.json()["detail"] == "Embedding model not loaded"


def test_ready_rejects_missing_configured_ollama_model():
    client = _make_client()

    with patch("app.db.is_initialized", return_value=True), \
         patch("app.embeddings.is_loaded", return_value=True), \
         patch("app.generation.ollama.is_configured_model_available", return_value=False):
        response = client.get("/ready", headers={"X-Internal-Token": TOKEN})

    assert response.status_code == 503
    assert response.json()["detail"] == "Configured Ollama model unavailable: qwen3:8b"


def test_ready_accepts_available_dependencies():
    client = _make_client()

    with patch("app.db.is_initialized", return_value=True), \
         patch("app.embeddings.is_loaded", return_value=True), \
         patch("app.generation.ollama.is_configured_model_available", return_value=True):
        response = client.get("/ready", headers={"X-Internal-Token": TOKEN})

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "service": "service-ia", "llm_model": "qwen3:8b"}