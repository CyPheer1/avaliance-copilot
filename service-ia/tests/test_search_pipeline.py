from unittest.mock import patch

from app.schemas import Citation, GenerateResponse, RetrieveRequest, RetrieveResponse, RetrievedChunk
from app.search_pipeline import run_search_pipeline
from app.settings import Settings


TOKEN = "test-internal-token-123456"


def _settings() -> Settings:
    return Settings(
        internal_token=TOKEN,
        database_url="postgresql://test:test@localhost:5432/test",
        generation_max_context_chunks=8,
        generation_cache_max_entries=0,
    )


def _chunk() -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=3597,
        mission_id=None,
        mission_title=None,
        document_id=29,
        document_name="02_Novacom_Telecom_Plateforme_Data_Retention_Bilan_Mission.pdf",
        page=13,
        sector="télécom",
        mission_type="data/BI",
        corpus_scope="PDF",
        request_id="req-1",
        content="Pauline Vasseur Ingénierie data Avaliance 100% flux temps réel",
        score=0.5,
        rrf_score=0.5,
        relevance_score=0.99,
        vector_score=0.99,
        text_score=0.88,
    )


def test_run_search_pipeline_uses_production_retrieve_chunks_for_generation():
    request = RetrieveRequest(
        query="Qui a pris en charge la partie flux temps réel dans le projet Novacom Télécom (programme HORIZON DATA) ?",
        top_k=5,
        corpus_scope="PDF",
        request_id="req-1",
    )
    retrieve_response = RetrieveResponse(query=request.query, chunks=[_chunk()], total_found=1)
    trace = {
        "query": request.query,
        "request_id": request.request_id,
        "corpus_scope": request.corpus_scope,
        "top_k": request.top_k,
        "candidate_limit": 20,
        "metadata_filters": ["dc.corpus_scope = %s", "dc.source_document_id IS NOT NULL", "sd.status = 'INDEXED'"],
        "metadata_filter_params": ["PDF"],
        "vector_elapsed_ms": 11.0,
        "text_elapsed_ms": 7.0,
        "rerank_elapsed_ms": 1.0,
        "vector_rows": [{"chunk_id": 3597}],
        "text_rows": [{"chunk_id": 3597}],
        "candidate_rows": [{"chunk_id": 3597}],
        "final_rows": [{"chunk_id": 3597}],
    }
    generate_response = GenerateResponse(
        answer="Pauline Vasseur — Ingénierie data — flux temps réel [1]",
        citations=[
            Citation(
                citation_id="req-1:3597",
                chunk_id=3597,
                document_id=29,
                document_name="02_Novacom_Telecom_Plateforme_Data_Retention_Bilan_Mission.pdf",
                page=13,
                corpus_scope="PDF",
                request_id="req-1",
                content="Pauline Vasseur Ingénierie data Avaliance 100% flux temps réel",
                score=0.5,
                rrf_score=0.5,
                relevance_score=0.99,
            )
        ],
        confidence=0.99,
    )

    with patch("app.search_pipeline.vector_search_with_trace", return_value=(retrieve_response, trace)) as retrieve_mock, patch(
        "app.search_pipeline.generate_sourced_answer", return_value=generate_response
    ) as generate_mock:
        actual_retrieve, actual_generate, pipeline_trace = run_search_pipeline(request, _settings())

    assert actual_retrieve == retrieve_response
    assert actual_generate == generate_response
    retrieve_mock.assert_called_once_with(request)
    generate_request = generate_mock.call_args.args[0]
    assert [chunk.chunk_id for chunk in generate_request.chunks] == [3597]
    assert generate_request.request_id == "req-1"
    assert pipeline_trace["selection"]["selected_chunk_ids"] == [3597]
    assert [chunk.chunk_id for chunk in generate_request.chunks] == pipeline_trace["selection"]["selected_chunk_ids"]
    assert pipeline_trace["answer"]["citation_chunk_ids"] == [3597]
    assert pipeline_trace["answer"]["validation_passed"] is False
    assert pipeline_trace["answer"]["evidence"] == []
    assert pipeline_trace["retrieval"]["final_rows"][0]["chunk_id"] == 3597
