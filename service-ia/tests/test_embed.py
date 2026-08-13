"""Tests for /embed endpoint."""

from unittest.mock import patch

import numpy as np
from fastapi.testclient import TestClient

import app.embeddings as embeddings_module
from app.main import create_app
from app.settings import Settings

TOKEN = "test-internal-token-123456"


def _make_client() -> TestClient:
    settings = Settings(
        internal_token=TOKEN,
        database_url="postgresql://test:test@localhost:5432/test",
    )
    # Disable lifespan to avoid loading real model/DB in tests
    app = create_app(settings)
    app.router.lifespan_context = None  # type: ignore[assignment]
    return TestClient(app, raise_server_exceptions=False)


def test_embed_returns_vectors():
    client = _make_client()

    fake_vectors = np.array([[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]], dtype=np.float32)

    with patch("app.embeddings.is_loaded", return_value=True), \
         patch("app.embeddings.encode", return_value=fake_vectors), \
         patch("app.embeddings.get_dimension", return_value=3):
        response = client.post(
            "/embed",
            json={"texts": ["hello", "world"]},
            headers={"X-Internal-Token": TOKEN},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 2
    assert data["dimension"] == 3
    assert len(data["embeddings"]) == 2
    assert len(data["embeddings"][0]) == 3


def test_embed_rejects_empty_texts():
    client = _make_client()

    response = client.post(
        "/embed",
        json={"texts": []},
        headers={"X-Internal-Token": TOKEN},
    )

    assert response.status_code == 422


def test_embed_requires_auth():
    client = _make_client()

    response = client.post("/embed", json={"texts": ["hello"]})

    assert response.status_code == 401


def test_embed_returns_503_when_model_not_loaded():
    client = _make_client()

    with patch("app.embeddings.is_loaded", return_value=False):
        response = client.post(
            "/embed",
            json={"texts": ["hello"]},
            headers={"X-Internal-Token": TOKEN},
        )

    assert response.status_code == 503


def test_load_model_uses_cuda_when_available():
    try:
        embeddings_module._model = None  # type: ignore[attr-defined]
        embeddings_module._model_name = None  # type: ignore[attr-defined]

        with patch("app.embeddings.SentenceTransformer") as mock_constructor, patch(
            "app.embeddings.torch.cuda.is_available", return_value=True
        ):
            mock_model = mock_constructor.return_value
            mock_model.get_sentence_embedding_dimension.return_value = 1024
            mock_model.max_seq_length = 8192

            embeddings_module.load_model("BAAI/bge-m3")

        mock_constructor.assert_called_once_with(
            "BAAI/bge-m3",
            device="cuda",
            model_kwargs={"torch_dtype": embeddings_module.torch.float16},
        )
        assert embeddings_module.is_loaded() is True
    finally:
        embeddings_module._model = None  # type: ignore[attr-defined]
        embeddings_module._model_name = None  # type: ignore[attr-defined]


def test_load_model_requires_cuda():
    try:
        embeddings_module._model = None  # type: ignore[attr-defined]
        embeddings_module._model_name = None  # type: ignore[attr-defined]

        with patch("app.embeddings.SentenceTransformer") as mock_constructor, patch(
            "app.embeddings.torch.cuda.is_available", return_value=False
        ):
            try:
                embeddings_module.load_model("BAAI/bge-m3")
            except RuntimeError as error:
                assert "CUDA is required" in str(error)
            else:
                raise AssertionError("Embedding startup must reject a CPU-only runtime")

        mock_constructor.assert_not_called()
    finally:
        embeddings_module._model = None  # type: ignore[attr-defined]
        embeddings_module._model_name = None  # type: ignore[attr-defined]
