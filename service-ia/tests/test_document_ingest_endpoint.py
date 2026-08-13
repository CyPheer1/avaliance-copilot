"""Regression tests for uploaded-document stream handling and error logging."""

from unittest.mock import patch

from fastapi.testclient import TestClient

from app.ingestion.extraction import DocumentExtractionError
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


def _upload(filename: str = "mission.pdf") -> dict[str, tuple[str, bytes, str]]:
    return {"file": (filename, b"%PDF-valid", "application/pdf")}


def test_document_ingest_resets_stream_before_reading():
    client = _make_client()

    with patch("app.ingestion.document_pipeline.ingest_document", return_value={"document_id": 7}) as ingest_mock:
        response = client.post(
            "/documents/ingest",
            data={"document_id": "7"},
            files=_upload(),
            headers={"X-Internal-Token": TOKEN},
        )

    assert response.status_code == 200
    assert ingest_mock.call_args.args == (7, "mission.pdf", b"%PDF-valid")


def test_document_ingest_logs_actual_extraction_exception(caplog):
    client = _make_client()

    with patch(
        "app.ingestion.document_pipeline.ingest_document",
        side_effect=DocumentExtractionError(
            "Le PDF ne peut pas être extrait. Consultez les journaux du service IA."
        ),
    ):
        response = client.post(
            "/documents/ingest",
            data={"document_id": "8"},
            files=_upload("valid.pdf"),
            headers={"X-Internal-Token": TOKEN},
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "Le PDF ne peut pas être extrait. Consultez les journaux du service IA."
    assert "Document extraction failed document_id=8 filename='valid.pdf' bytes=10" in caplog.text
