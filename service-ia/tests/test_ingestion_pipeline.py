"""Unit tests for the ingestion transaction and embedding contract."""

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import numpy as np

from app.ingestion.pipeline import ingest_missions
from app.schemas import IngestMissionDocument, IngestMissionRequest


def _mission() -> IngestMissionRequest:
    return IngestMissionRequest(
        id="mission-pipeline-test",
        title="Pipeline transaction test",
        sector="banque",
        mission_type="modernisation applicative",
        technologies=["Java", "PostgreSQL"],
        year=2024,
        referent_tag="p2-test",
        summary="Mission synthétique pour tester le pipeline P2.",
        documents=[
            IngestMissionDocument(
                chunk_index=0,
                kind="note architecture",
                content="Modernisation Java avec stockage PostgreSQL.",
            )
        ],
    )


def test_ingestion_uses_raw_bge_inputs_and_one_connection():
    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.fetchone.side_effect = [None, (42,)]

    @contextmanager
    def connection_context():
        yield connection

    vectors = np.ones((1, 1024), dtype=np.float32)
    with patch("app.ingestion.pipeline.is_loaded", return_value=True), \
         patch("app.ingestion.pipeline.get_connection", return_value=connection_context()), \
         patch("app.ingestion.pipeline.contextual_embedding_inputs", return_value=[
             "Modernisation Java avec stockage PostgreSQL."
         ]), \
         patch("app.ingestion.pipeline.encode", return_value=vectors) as mock_encode, \
         patch("app.ingestion.pipeline.execute_batch") as mock_execute_batch:
        result = ingest_missions([_mission()])

    encoded_texts = mock_encode.call_args.args[0]
    assert encoded_texts == ["Modernisation Java avec stockage PostgreSQL."]
    assert connection.cursor.call_count == 2
    assert mock_execute_batch.call_args.args[0] is cursor
    assert result == {
        "missions_inserted": 1,
        "chunks_inserted": 1,
        "chunks_with_embeddings": 1,
    }
