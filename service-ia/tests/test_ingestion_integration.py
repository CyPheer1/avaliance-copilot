from __future__ import annotations

import os
import uuid

import numpy as np
import pytest

import app.embeddings as embeddings_module
from app.db import close_pool, execute_query, init_pool
from app.ingestion.pipeline import ingest_missions
from app.retrieval.vector_search import vector_search
from app.schemas import IngestMissionDocument, IngestMissionRequest, RetrieveRequest


DATABASE_URL = os.getenv("DATABASE_URL")
_BASE_VECTOR = np.linspace(0.0, 1.0, 1024, dtype=np.float32)


def _vector_batch(texts: list[str]) -> np.ndarray:
    return np.tile(_BASE_VECTOR, (len(texts), 1)).astype(np.float32, copy=False)


def _make_mission(title: str, marker: str) -> IngestMissionRequest:
    return IngestMissionRequest(
        id=f"mission-{uuid.uuid4().hex}",
        title=title,
        sector="banque",
        mission_type="modernisation applicative",
        technologies=["Java", "Spring", "PostgreSQL"],
        year=2024,
        referent_tag="p2-int",
        summary="Mission synthétique de validation P2 avec recherche vectorielle réelle.",
        documents=[
            IngestMissionDocument(
                chunk_index=0,
                kind="note architecture",
                content=(
                    "Modernisation applicative Java Spring avec migration PostgreSQL, "
                    "cadre idéal pour valider l ingestion et la recherche vectorielle. "
                    f"Marqueur unique {marker}."
                ),
            )
        ],
    )


@pytest.mark.integration
def test_ingest_and_retrieve_against_real_postgresql():
    if not DATABASE_URL:
        pytest.skip("DATABASE_URL is required for the live PostgreSQL integration test")

    init_pool(DATABASE_URL)

    title = f"P2 Integration Test {uuid.uuid4().hex}"
    marker = f"nebula{uuid.uuid4().hex}"
    mission = _make_mission(title, marker)
    original_model = embeddings_module._model  # type: ignore[attr-defined]

    try:
        ext_rows = execute_query("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
        assert ext_rows, "pgvector extension must be installed"

        column_rows = execute_query(
            """
            SELECT data_type, udt_name
            FROM information_schema.columns
            WHERE table_name = 'doc_chunk' AND column_name = 'embedding'
            """
        )
        assert column_rows, "doc_chunk.embedding must exist"
        assert column_rows[0]["data_type"] == "USER-DEFINED"
        assert column_rows[0]["udt_name"] == "vector"

        import app.ingestion.pipeline as pipeline_module
        import app.retrieval.vector_search as vector_search_module

        original_pipeline_encode = pipeline_module.encode
        original_search_encode = vector_search_module.encode

        try:
            embeddings_module._model = object()  # type: ignore[attr-defined]
            pipeline_module.encode = _vector_batch  # type: ignore[assignment]
            vector_search_module.encode = _vector_batch  # type: ignore[assignment]

            result = ingest_missions([mission])
            assert result == {
                "missions_inserted": 1,
                "chunks_inserted": 1,
                "chunks_with_embeddings": 1,
            }

            chunk_rows = execute_query(
                """
                SELECT vector_dims(embedding) AS dimensions, ts
                FROM doc_chunk
                WHERE mission_id = (SELECT id FROM mission WHERE title = %s)
                """,
                (title,),
            )
            assert chunk_rows, "ingested mission must create at least one chunk"
            assert chunk_rows[0]["dimensions"] == 1024
            assert chunk_rows[0]["ts"] is not None
            assert len(str(chunk_rows[0]["ts"])) > 0

            search_result = vector_search(
                RetrieveRequest(query=marker, top_k=5, corpus_scope="MISSION")
            )
            assert search_result.total_found >= 1
            assert all(chunk.corpus_scope == "MISSION" for chunk in search_result.chunks)
            assert any(chunk.mission_title == title for chunk in search_result.chunks)
        finally:
            pipeline_module.encode = original_pipeline_encode  # type: ignore[assignment]
            vector_search_module.encode = original_search_encode  # type: ignore[assignment]
            embeddings_module._model = original_model  # type: ignore[attr-defined]
    finally:
        try:
            execute_query("DELETE FROM mission WHERE title = %s", (title,))
        finally:
            close_pool()

