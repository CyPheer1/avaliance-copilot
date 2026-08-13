from unittest.mock import patch

from app.generation.ollama import OllamaUnavailableError
from app.ingestion.contextual import contextual_embedding_inputs
from app.settings import Settings


def _settings(**overrides) -> Settings:
    return Settings(
        internal_token="test-internal-token-123456",
        database_url="postgresql://test:test@localhost:5432/test",
        **overrides,
    )


def test_contextual_embeddings_keep_raw_input_when_disabled():
    chunks = ["Le projet utilise PostgreSQL."]

    assert contextual_embedding_inputs(
        document_label="architecture.pdf",
        document_context=chunks[0],
        chunks=chunks,
        settings=_settings(contextual_retrieval_enabled=False),
    ) == ["Le projet utilise PostgreSQL."]


def test_contextual_embeddings_prefix_retrieval_input_without_mutating_chunk():
    chunk = "Le projet utilise PostgreSQL."
    with patch("app.ingestion.contextual.generate_text", return_value="Cette section décrit la persistance."):
        inputs = contextual_embedding_inputs(
            document_label="architecture.pdf",
            document_context=chunk,
            chunks=[chunk],
            settings=_settings(contextual_retrieval_enabled=True),
        )

    assert inputs == [
        "Cette section décrit la persistance.\n\nLe projet utilise PostgreSQL."
    ]
    assert chunk == "Le projet utilise PostgreSQL."


def test_contextual_embeddings_fall_back_to_original_passages_when_prefix_generation_fails():
    chunks = ["Premier extrait.", "Second extrait."]
    with patch(
        "app.ingestion.contextual.generate_text",
        side_effect=OllamaUnavailableError("unavailable"),
    ):
        inputs = contextual_embedding_inputs(
            document_label="architecture.pdf",
            document_context="\n".join(chunks),
            chunks=chunks,
            settings=_settings(contextual_retrieval_enabled=True),
        )

    assert inputs == ["Premier extrait.", "Second extrait."]
