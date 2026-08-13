from unittest.mock import MagicMock, patch

import numpy as np

from app.ingestion.document_pipeline import ingest_document
from app.ingestion.extraction import ExtractedSection


@patch("app.ingestion.document_pipeline.execute_batch")
@patch("app.ingestion.document_pipeline.get_connection")
@patch("app.ingestion.document_pipeline.encode")
@patch("app.ingestion.document_pipeline._embedding_inputs")
@patch("app.ingestion.document_pipeline.extract_document")
@patch("app.ingestion.document_pipeline.is_loaded", return_value=True)
def test_document_ingestion_replaces_chunks_with_page_metadata(
    _is_loaded,
    extract_document_mock,
    embedding_inputs_mock,
    encode_mock,
    get_connection_mock,
    execute_batch_mock,
):
    extract_document_mock.return_value = [
        ExtractedSection(content="Architecture cloud sécurisée", page=2),
        ExtractedSection(content="Plan de migration", page=3),
    ]
    embedding_inputs_mock.return_value = ["Architecture cloud sécurisée", "Plan de migration"]
    encode_mock.return_value = [np.array([0.1, 0.2]), np.array([0.3, 0.4])]
    connection = MagicMock()
    get_connection_mock.return_value.__enter__.return_value = connection

    result = ingest_document(42, "mission.pdf", b"pdf")

    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.execute.assert_called_once_with(
        "DELETE FROM doc_chunk WHERE source_document_id = %s", (42,)
    )
    params = execute_batch_mock.call_args.args[2]
    assert params == [
        (42, 2, 0, "Architecture cloud sécurisée", [0.1, 0.2]),
        (42, 3, 1, "Plan de migration", [0.3, 0.4]),
    ]
    assert result == {
        "document_id": 42,
        "page_count": 3,
        "chunks_inserted": 2,
        "characters_extracted": 45,
    }


@patch("app.ingestion.document_pipeline.execute_batch")
@patch("app.ingestion.document_pipeline.get_connection")
@patch("app.ingestion.document_pipeline.encode")
@patch("app.ingestion.document_pipeline._embedding_inputs")
@patch("app.ingestion.document_pipeline.extract_document")
@patch("app.ingestion.document_pipeline.is_loaded", return_value=True)
def test_document_ingestion_counts_non_paginated_document_as_one_page(
    _is_loaded,
    extract_document_mock,
    embedding_inputs_mock,
    encode_mock,
    get_connection_mock,
    _execute_batch_mock,
):
    extract_document_mock.return_value = [ExtractedSection(content="Texte indexable")]
    embedding_inputs_mock.return_value = ["Texte indexable"]
    encode_mock.return_value = [np.array([0.1, 0.2])]
    connection = MagicMock()
    get_connection_mock.return_value.__enter__.return_value = connection

    result = ingest_document(43, "mission.txt", b"Texte indexable")

    assert result["page_count"] == 1