"""Regression coverage for sector-aware PDF evidence selection."""

from unittest.mock import patch

from app.retrieval.vector_search import retrieve_for_requirements
from app.schemas import RetrievedChunk, RetrieveResponse, RfpAtomicNeed


def _chunk(chunk_id: int, document_name: str) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_id=chunk_id,
        document_name=document_name,
        page=3,
        corpus_scope="PDF",
        content="Architecture temps réel et paiements instantanés.",
        score=0.9,
    )


def test_banking_sector_prefers_banking_document_title_over_unrelated_pdf() -> None:
    need = RfpAtomicNeed(
        id="req-01",
        text="Traiter 15 000 événements par seconde avec une latence p95 inférieure à 200 ms.",
        category="performance",
        priority="MUST",
        source_excerpt="15 000 événements par seconde",
        start_offset=0,
        end_offset=30,
    )
    response = RetrieveResponse(
        query=need.text,
        chunks=[
            _chunk(1, "04_Volteris_Energies_Socle_IoT_Telereleve_Dossier_Projet.pdf"),
            _chunk(2, "01_Credalis_Banque_NovaShield_Bilan_Projet.pdf"),
            _chunk(3, "02_Transovia_Logistique_ORION_WMS_Bilan_Projet.pdf"),
        ],
        total_found=3,
    )

    with patch("app.retrieval.vector_search.vector_search", return_value=response) as search:
        packets = retrieve_for_requirements([need], sector="banque")

    assert "banque" in search.call_args.args[0].query.lower()
    assert [e.document_name for e in packets[0].evidence] == [
        "01_Credalis_Banque_NovaShield_Bilan_Projet.pdf"
    ]
    assert packets[0].evidence[0].id == "pdf-001"
