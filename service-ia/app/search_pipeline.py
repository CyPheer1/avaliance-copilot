"""Shared retrieval + generation orchestration for parity between live API and evaluators."""

from __future__ import annotations

import time
from typing import Any

from .generation.service import _select_relevant_chunks, generate_sourced_answer
from .schemas import GenerateRequest, GenerateResponse, RetrieveRequest, RetrieveResponse
from .settings import Settings
from .retrieval.vector_search import vector_search_with_trace


def run_search_pipeline(
    retrieve_request: RetrieveRequest,
    settings: Settings,
) -> tuple[RetrieveResponse, GenerateResponse, dict[str, Any]]:
    """Execute the production retrieval and generation pipeline with trace data."""
    retrieval_started = time.perf_counter()
    retrieve_response, retrieval_trace = vector_search_with_trace(retrieve_request)
    retrieval_latency_ms = (time.perf_counter() - retrieval_started) * 1000

    selected_chunks = _select_relevant_chunks(
        retrieve_request.query,
        retrieve_response.chunks,
        limit=settings.generation_max_context_chunks,
    )
    generate_request = GenerateRequest(
        query=retrieve_request.query,
        request_id=retrieve_request.request_id,
        chunks=selected_chunks,
    )

    generation_started = time.perf_counter()
    generate_response = generate_sourced_answer(generate_request, settings)
    generation_latency_ms = (time.perf_counter() - generation_started) * 1000

    trace: dict[str, Any] = {
        "request": {
            "query": retrieve_request.query,
            "request_id": retrieve_request.request_id,
            "corpus_scope": retrieve_request.corpus_scope,
            "top_k": retrieve_request.top_k,
            "sector": retrieve_request.sector,
            "mission_type": retrieve_request.mission_type,
            "year": retrieve_request.year,
        },
        "retrieval": retrieval_trace,
        "selection": {
            "selected_chunk_ids": [chunk.chunk_id for chunk in selected_chunks],
            "selected_chunks": [
                {
                    "chunk_id": chunk.chunk_id,
                    "document_id": chunk.document_id,
                    "document_name": chunk.document_name,
                    "page": chunk.page,
                    "corpus_scope": chunk.corpus_scope,
                    "rrf_score": chunk.rrf_score,
                    "relevance_score": chunk.relevance_score,
                    "vector_score": chunk.vector_score,
                    "text_score": chunk.text_score,
                }
                for chunk in selected_chunks
            ],
        },
        "answer": {
            "text": generate_response.answer,
            "confidence": generate_response.confidence,
            "diagnostic": generate_response.diagnostic,
            "validation_passed": generate_response.validation_passed,
            "citation_chunk_ids": [citation.chunk_id for citation in generate_response.citations],
            "evidence": [item.model_dump(mode="json") for item in generate_response.evidence],
            "evidence_spans": [item.model_dump(mode="json") for item in generate_response.evidence_spans],
            "citations": [
                {
                    "citation_id": citation.citation_id,
                    "request_id": citation.request_id,
                    "chunk_id": citation.chunk_id,
                    "document_id": citation.document_id,
                    "document_name": citation.document_name,
                    "page": citation.page,
                    "corpus_scope": citation.corpus_scope,
                    "score": citation.score,
                    "rrf_score": citation.rrf_score,
                    "relevance_score": citation.relevance_score,
                }
                for citation in generate_response.citations
            ],
        },
        "timing_ms": {
            "retrieval_total_ms": round(retrieval_latency_ms, 3),
            "generation_ms": round(generation_latency_ms, 3),
            "total_ms": round(retrieval_latency_ms + generation_latency_ms, 3),
        },
    }
    return retrieve_response, generate_response, trace
