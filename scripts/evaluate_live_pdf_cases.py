"""Evaluate live PDF-only treatment versus eval-only mixed-scope control.

This script does not modify production behavior or runtime data. It connects directly to
PostgreSQL, reuses the service-ia retrieval SQL and generation policy in-process, and writes
comparison artifacts for a versioned live-PDF case suite.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import sys
import tempfile
import time
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
SERVICE_IA_ROOT = ROOT / "service-ia"
if not SERVICE_IA_ROOT.exists() and (ROOT / "app").exists():
    SERVICE_IA_ROOT = ROOT
if str(SERVICE_IA_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_IA_ROOT))

from app import db, embeddings  # type: ignore  # noqa: E402
from app.generation.prompts import INSUFFICIENT_INFORMATION  # type: ignore  # noqa: E402
from app.generation.service import generate_sourced_answer  # type: ignore  # noqa: E402
from app.project_query import project_reference_from_query, project_title_from_query  # type: ignore  # noqa: E402
from app.retrieval.vector_search import (  # type: ignore  # noqa: E402
    _CONTENT_SELECT,
    _MIN_CANDIDATES,
    _MAX_CANDIDATES,
    _CANDIDATE_MULTIPLIER,
    _RRF_WEIGHTS,
    _metadata_filters,
    _query_embedding,
    _rerank_named_project_evidence,
    reciprocal_rank_fusion,
)
from app.schemas import GenerateRequest, RetrieveRequest, RetrievedChunk  # type: ignore  # noqa: E402
from app.search_pipeline import run_search_pipeline  # type: ignore  # noqa: E402
from app.settings import Settings  # type: ignore  # noqa: E402


@dataclass(frozen=True)
class EvalCase:
    case_id: str
    category: str
    query: str
    should_abstain: bool
    accepted_answer_fragments: list[str]
    forbidden_answer_fragments: list[str]
    expected_evidence: list[dict[str, Any]]


@dataclass(frozen=True)
class EvalMode:
    name: str
    corpus_scope: str
    include_mission: bool


PDF_ONLY = EvalMode(name="pdf_only", corpus_scope="PDF", include_mission=False)
MIXED_SCOPE = EvalMode(
    name="mixed_pdf_mission_eval_only",
    corpus_scope="PDF",
    include_mission=True,
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=path.parent) as handle:
        handle.write(content)
        temp_name = handle.name
    Path(temp_name).replace(path)


def median_metric(values: list[float]) -> float | None:
    return round(statistics.median(values), 3) if values else None


def redact_preview(content: str, *, limit: int = 140) -> str:
    compact = " ".join(content.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1] + "…"


def load_cases(path: Path) -> list[EvalCase]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [EvalCase(**item) for item in payload["cases"]]


def read_env_value(path: Path, key: str) -> str | None:
    if not path.exists():
        return None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        candidate, value = line.split("=", 1)
        if candidate.strip() == key:
            return value.strip().strip('"\'') or None
    return None


def _normalize_database_url(database_url: str, *, username: str | None = None, password: str | None = None) -> str:
    if database_url.startswith("jdbc:"):
        database_url = database_url.removeprefix("jdbc:")
    parsed = urlsplit(database_url)
    host = parsed.hostname or ""
    netloc = parsed.netloc
    if username and parsed.username is None:
        credential_prefix = username
        if password is not None:
            credential_prefix += f":{password}"
        if "@" in netloc:
            _, _, host_port = netloc.rpartition("@")
        else:
            host_port = netloc
        netloc = f"{credential_prefix}@{host_port}"
        parsed = parsed._replace(netloc=netloc)
    if host != "postgres":
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, parsed.fragment))
    netloc = parsed.netloc
    if "@" in netloc:
        credentials, _, host_port = netloc.rpartition("@")
        _, _, port = host_port.partition(":")
        replacement = f"{credentials}@localhost{':' + port if port else ''}"
    else:
        _, _, port = netloc.partition(":")
        replacement = f"localhost{':' + port if port else ''}"
    return urlunsplit((parsed.scheme, replacement, parsed.path, parsed.query, parsed.fragment))


def _normalize_service_url(url: str, service_host: str) -> str:
    parsed = urlsplit(url)
    if parsed.hostname != service_host:
        return url
    netloc = parsed.netloc.replace(service_host, "localhost", 1)
    return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))


def build_settings() -> Settings:
    service_env = SERVICE_IA_ROOT / ".env"
    root_env = ROOT / ".env"
    db_username = (
        os.getenv("DB_USERNAME")
        or os.getenv("POSTGRES_USER")
        or read_env_value(service_env, "DB_USERNAME")
        or read_env_value(service_env, "POSTGRES_USER")
        or read_env_value(root_env, "DB_USERNAME")
        or read_env_value(root_env, "POSTGRES_USER")
        or "copilot"
    )
    db_password = (
        os.getenv("DB_PASSWORD")
        or os.getenv("POSTGRES_PASSWORD")
        or read_env_value(service_env, "DB_PASSWORD")
        or read_env_value(service_env, "POSTGRES_PASSWORD")
        or read_env_value(root_env, "DB_PASSWORD")
        or read_env_value(root_env, "POSTGRES_PASSWORD")
        or "change_me_db_password"
    )
    database_url = _normalize_database_url(
        os.getenv("DATABASE_URL")
        or read_env_value(service_env, "DATABASE_URL")
        or read_env_value(root_env, "DATABASE_URL")
        or "postgresql://copilot:change_me_db_password@localhost:5432/avaliance",
        username=db_username,
        password=db_password,
    )
    embedding_model_path = (
        os.getenv("EMBEDDING_MODEL_PATH")
        or read_env_value(service_env, "EMBEDDING_MODEL_PATH")
        or read_env_value(root_env, "EMBEDDING_MODEL_PATH")
        or "BAAI/bge-m3"
    )
    ollama_url = _normalize_service_url(
        os.getenv("OLLAMA_URL")
        or read_env_value(service_env, "OLLAMA_URL")
        or read_env_value(root_env, "OLLAMA_URL")
        or "http://localhost:11434",
        "ollama",
    )
    return Settings(
        internal_token=os.getenv("INTERNAL_TOKEN", "change_me_internal_service_secret"),
        database_url=database_url,
        embedding_model_path=embedding_model_path,
        ollama_url=ollama_url,
        llm_model=(
            os.getenv("LLM_MODEL")
            or read_env_value(service_env, "LLM_MODEL")
            or read_env_value(root_env, "LLM_MODEL")
            or (_ for _ in ()).throw(RuntimeError("LLM_MODEL must be configured"))
        ),
        generation_cache_max_entries=0,
        min_source_similarity=float(os.getenv("MIN_SOURCE_SIMILARITY", "0.55")),
    )


def _named_project_filter(query: str) -> tuple[list[str], list[object]]:
    project_reference = project_reference_from_query(query)
    if project_reference is not None:
        return ["sd.original_filename ILIKE %s"], [f"%{project_reference}%"]

    project_title = project_title_from_query(query)
    if project_title is None:
        return [], []

    return [
        """
        dc.source_document_id = (
            SELECT candidate.source_document_id
            FROM doc_chunk candidate
            WHERE candidate.source_document_id IS NOT NULL
              AND candidate.ts @@ plainto_tsquery('french', %s)
            GROUP BY candidate.source_document_id
            ORDER BY max(
                ts_rank_cd(candidate.ts, plainto_tsquery('french', %s))
            ) DESC, candidate.source_document_id
            LIMIT 1
        )
        """
    ], [project_title, project_title]


def _mixed_scope_filters(request: RetrieveRequest) -> tuple[list[str], list[object]]:
    conditions, params = _metadata_filters(request)
    filtered_conditions: list[str] = []
    for condition in conditions:
        if condition == "dc.corpus_scope = %s":
            continue
        if condition == "dc.source_document_id IS NOT NULL":
            continue
        if condition == "sd.status = 'INDEXED'":
            continue
        filtered_conditions.append(condition)
    filtered_params = [param for param in params if param != "PDF"]
    mixed_condition = "(dc.corpus_scope = 'MISSION' OR (dc.corpus_scope = 'PDF' AND dc.source_document_id IS NOT NULL AND sd.status = 'INDEXED'))"
    return [mixed_condition, *filtered_conditions], filtered_params


def retrieve_chunks(request: RetrieveRequest, mode: EvalMode) -> tuple[list[RetrievedChunk], dict[str, float]]:
    query_vector = list(_query_embedding(request.query))
    vector_literal = str(query_vector)
    if mode.include_mission:
        conditions, filter_params = _mixed_scope_filters(request)
    else:
        conditions, filter_params = _metadata_filters(request)
    project_conditions, project_params = _named_project_filter(request.query)
    conditions.extend(project_conditions)
    filter_params.extend(project_params)
    candidate_limit = min(
        max(request.top_k * _CANDIDATE_MULTIPLIER, _MIN_CANDIDATES),
        _MAX_CANDIDATES,
    )

    vector_conditions = ["dc.embedding IS NOT NULL", *conditions]
    vector_where = " AND ".join(vector_conditions)
    vector_query = f"""
        SELECT
            dc.id AS chunk_id,
            dc.mission_id,
            m.title AS mission_title,
            dc.source_document_id AS document_id,
            sd.original_filename AS document_name,
            dc.source_page AS page,
            dc.sector,
            dc.mission_type,
            dc.corpus_scope,
            {_CONTENT_SELECT}
            1 - (dc.embedding <=> %s::vector) AS ranking_score
        FROM doc_chunk dc
        LEFT JOIN mission m ON m.id = dc.mission_id
        LEFT JOIN source_document sd ON sd.id = dc.source_document_id
        WHERE {vector_where}
        ORDER BY dc.embedding <=> %s::vector
        LIMIT %s
    """
    vector_params = (vector_literal, *filter_params, vector_literal, candidate_limit)

    text_conditions = [*conditions, "dc.ts @@ lexical_query.value"]
    text_where = " AND ".join(text_conditions)
    text_query = f"""
        SELECT
            dc.id AS chunk_id,
            dc.mission_id,
            m.title AS mission_title,
            dc.source_document_id AS document_id,
            sd.original_filename AS document_name,
            dc.source_page AS page,
            dc.sector,
            dc.mission_type,
            dc.corpus_scope,
            {_CONTENT_SELECT}
            ts_rank_cd(dc.ts, lexical_query.value) AS ranking_score
        FROM doc_chunk dc
        LEFT JOIN mission m ON m.id = dc.mission_id
        LEFT JOIN source_document sd ON sd.id = dc.source_document_id
        CROSS JOIN LATERAL (
            SELECT to_tsquery(
                'french',
                array_to_string(
                    tsvector_to_array(to_tsvector('french', %s)),
                    ' | '
                )
            ) AS value
        ) lexical_query
        WHERE {text_where}
        ORDER BY ranking_score DESC, dc.id
        LIMIT %s
    """
    text_params = (request.query, *filter_params, candidate_limit)

    started = time.perf_counter()
    vector_rows = db.execute_query(vector_query, vector_params)
    vector_elapsed_ms = (time.perf_counter() - started) * 1000

    started = time.perf_counter()
    text_rows = db.execute_query(text_query, text_params)
    text_elapsed_ms = (time.perf_counter() - started) * 1000

    started = time.perf_counter()
    candidate_rows = reciprocal_rank_fusion(
        [vector_rows, text_rows],
        top_k=candidate_limit,
        weights=_RRF_WEIGHTS,
    )
    reranked_rows = _rerank_named_project_evidence(request.query, candidate_rows, top_k=request.top_k)
    rerank_elapsed_ms = (time.perf_counter() - started) * 1000

    chunks = [
        RetrievedChunk(
            chunk_id=row["chunk_id"],
            mission_id=row["mission_id"],
            mission_title=row["mission_title"],
            document_id=row.get("document_id"),
            document_name=row.get("document_name"),
            page=row.get("page"),
            sector=row.get("sector"),
            mission_type=row.get("mission_type"),
            corpus_scope=row["corpus_scope"],
            request_id=request.request_id,
            content=row["content"],
            score=float(row["score"]),
            rrf_score=float(row["rrf_score"]),
            relevance_score=float(row["relevance_score"]),
            vector_score=float(row["vector_score"]) if row.get("vector_score") is not None else None,
            text_score=float(row["text_score"]) if row.get("text_score") is not None else None,
        )
        for row in reranked_rows
    ]
    return chunks, {
        "vector_query_ms": round(vector_elapsed_ms, 3),
        "text_query_ms": round(text_elapsed_ms, 3),
        "rerank_ms": round(rerank_elapsed_ms, 3),
        "retrieval_total_ms": round(vector_elapsed_ms + text_elapsed_ms + rerank_elapsed_ms, 3),
    }


def first_supporting_rank(chunks: list[RetrievedChunk], expected_evidence: list[dict[str, Any]]) -> int | None:
    expected_pairs = {
        (item.get("document_id"), item.get("chunk_id"), item.get("page"))
        for item in expected_evidence
    }
    for index, chunk in enumerate(chunks, start=1):
        if (chunk.document_id, chunk.chunk_id, chunk.page) in expected_pairs:
            return index
    return None


def recall_at(chunks: list[RetrievedChunk], expected_evidence: list[dict[str, Any]], limit: int) -> float | None:
    if not expected_evidence:
        return None
    expected_pairs = {
        (item.get("document_id"), item.get("chunk_id"), item.get("page"))
        for item in expected_evidence
    }
    found = {
        (chunk.document_id, chunk.chunk_id, chunk.page)
        for chunk in chunks[:limit]
        if (chunk.document_id, chunk.chunk_id, chunk.page) in expected_pairs
    }
    return round(len(found) / len(expected_pairs), 4)


def answer_contains_all(answer: str, fragments: list[str]) -> bool:
    folded_answer = answer.casefold()
    return all(fragment.casefold() in folded_answer for fragment in fragments)


def answer_contains_any(answer: str, fragments: list[str]) -> bool:
    folded_answer = answer.casefold()
    return any(fragment.casefold() in folded_answer for fragment in fragments)


def citation_correctness(citations: list[Any], expected_evidence: list[dict[str, Any]], should_abstain: bool) -> bool:
    if should_abstain:
        return not citations
    if not citations:
        return False
    expected = {
        (item.get("document_id"), item.get("document_name"), item.get("page"), item.get("chunk_id"))
        for item in expected_evidence
    }
    actual = {
        (citation.document_id, citation.document_name, citation.page, citation.chunk_id)
        for citation in citations
    }
    return bool(actual & expected)


def groundedness(answer: str, citations: list[Any], should_abstain: bool) -> bool:
    if should_abstain:
        return answer == INSUFFICIENT_INFORMATION and not citations
    return answer != INSUFFICIENT_INFORMATION and bool(citations)


def evaluate_case(case: EvalCase, mode: EvalMode, settings: Settings) -> dict[str, Any]:
    request_id = f"{case.case_id}:{mode.name}"
    started_at = utc_now_iso()
    retrieve_request = RetrieveRequest(
        query=case.query,
        top_k=5 if not mode.include_mission else 20,
        corpus_scope=mode.corpus_scope,
        request_id=request_id,
    )

    if mode.include_mission:
        retrieval_started = time.perf_counter()
        chunks, retrieval_metrics = retrieve_chunks(retrieve_request, mode)
        retrieval_latency_ms = (time.perf_counter() - retrieval_started) * 1000
        generation_started = time.perf_counter()
        response = generate_sourced_answer(
            GenerateRequest(query=case.query, request_id=request_id, chunks=chunks),
            settings,
        )
        generation_latency_ms = (time.perf_counter() - generation_started) * 1000
        pipeline_trace = {
            "orchestration": "legacy_eval_mixed_scope_pipeline",
            "request": {
                "query": retrieve_request.query,
                "request_id": retrieve_request.request_id,
                "corpus_scope": retrieve_request.corpus_scope,
                "top_k": retrieve_request.top_k,
            },
            "timing_ms": {
                "retrieval_total_ms": round(retrieval_latency_ms, 3),
                "generation_ms": round(generation_latency_ms, 3),
                "total_ms": round(retrieval_latency_ms + generation_latency_ms, 3),
            },
        }
    else:
        retrieve_response, response, pipeline_trace = run_search_pipeline(retrieve_request, settings)
        chunks = retrieve_response.chunks
        pipeline_trace = {
            "orchestration": "shared_production_pipeline",
            **pipeline_trace,
        }

    first_rank = first_supporting_rank(chunks, case.expected_evidence)
    answer = response.answer
    abstained = answer == INSUFFICIENT_INFORMATION
    correctness = abstained if case.should_abstain else answer_contains_all(answer, case.accepted_answer_fragments)
    irrelevant_content = answer_contains_any(answer, case.forbidden_answer_fragments)

    retrieval_trace = [
        {
            "rank": index,
            "chunk_id": chunk.chunk_id,
            "document_id": chunk.document_id,
            "document_name": chunk.document_name,
            "page": chunk.page,
            "corpus_scope": chunk.corpus_scope,
            "rrf_score": chunk.rrf_score,
            "relevance_score": chunk.relevance_score,
            "vector_score": chunk.vector_score,
            "text_score": chunk.text_score,
            "content_preview": redact_preview(chunk.content),
        }
        for index, chunk in enumerate(chunks[:20], start=1)
    ]

    return {
        "case_id": case.case_id,
        "category": case.category,
        "mode": mode.name,
        "query": case.query,
        "started_at": started_at,
        "finished_at": utc_now_iso(),
        "status": "ok",
        "should_abstain": case.should_abstain,
        "abstained": abstained,
        "correctness": correctness,
        "groundedness": groundedness(answer, response.citations, case.should_abstain),
        "citation_correct": citation_correctness(response.citations, case.expected_evidence, case.should_abstain),
        "irrelevant_content": irrelevant_content,
        "abstention_correct": abstained if case.should_abstain else None,
        "answer_length_chars": len(answer),
        "confidence": response.confidence,
        "diagnostic": response.diagnostic,
        "answer": answer,
        "expected_evidence": case.expected_evidence,
        "citations": [
            {
                "citation_id": citation.citation_id,
                "request_id": citation.request_id,
                "chunk_id": citation.chunk_id,
                "mission_id": citation.mission_id,
                "mission_title": citation.mission_title,
                "document_id": citation.document_id,
                "document_name": citation.document_name,
                "page": citation.page,
                "corpus_scope": citation.corpus_scope,
                "score": citation.score,
                "rrf_score": citation.rrf_score,
                "relevance_score": citation.relevance_score,
                "content_preview": redact_preview(citation.content),
            }
            for citation in response.citations
        ],
        "retrieval_trace": retrieval_trace,
        "pipeline_trace": pipeline_trace,
        "recall_at_5": recall_at(chunks, case.expected_evidence, 5),
        "recall_at_10": recall_at(chunks, case.expected_evidence, 10),
        "recall_at_20": recall_at(chunks, case.expected_evidence, 20),
        "first_supporting_rank": first_rank,
        "mrr_like": round(1 / first_rank, 4) if first_rank else 0.0,
        "timing_ms": {
            "vector_query_ms": pipeline_trace.get("retrieval", {}).get("vector_elapsed_ms"),
            "text_query_ms": pipeline_trace.get("retrieval", {}).get("text_elapsed_ms"),
            "rerank_ms": pipeline_trace.get("retrieval", {}).get("rerank_elapsed_ms"),
            **pipeline_trace["timing_ms"],
            "ttft_before_fetch_ms": None,
        },
    }


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    def selected(mode: str) -> list[dict[str, Any]]:
        return [result for result in results if result["mode"] == mode and result.get("status") == "ok"]

    def rate(field: str, *, mode: str) -> dict[str, Any]:
        rows = [result for result in selected(mode) if result[field] is not None]
        passed = sum(bool(result[field]) for result in rows)
        return {
            "passed": passed,
            "total": len(rows),
            "rate": round(passed / len(rows), 4) if rows else None,
        }

    def mean(field: str, *, mode: str) -> float | None:
        values = [result["timing_ms"][field] for result in selected(mode)]
        return round(sum(values) / len(values), 3) if values else None

    def median(field: str, *, mode: str) -> float | None:
        values = [result["timing_ms"][field] for result in selected(mode)]
        return median_metric(values)

    def errors(mode: str) -> int:
        return sum(result.get("status") == "error" for result in results if result["mode"] == mode)

    return {
        mode.name: {
            "correctness": rate("correctness", mode=mode.name),
            "groundedness": rate("groundedness", mode=mode.name),
            "citation_correct": rate("citation_correct", mode=mode.name),
            "abstention_correct": rate("abstention_correct", mode=mode.name),
            "mean_retrieval_ms": mean("retrieval_total_ms", mode=mode.name),
            "median_retrieval_ms": median("retrieval_total_ms", mode=mode.name),
            "mean_generation_ms": mean("generation_ms", mode=mode.name),
            "median_generation_ms": median("generation_ms", mode=mode.name),
            "mean_total_ms": mean("total_ms", mode=mode.name),
            "median_total_ms": median("total_ms", mode=mode.name),
            "errors": errors(mode.name),
        }
        for mode in (PDF_ONLY, MIXED_SCOPE)
    }


def _write_csv_summary(path: Path, results: list[dict[str, Any]]) -> None:
    rows: list[dict[str, Any]] = []
    for result in results:
        rows.append(
            {
                "case_id": result["case_id"],
                "mode": result["mode"],
                "status": result.get("status"),
                "correctness": result.get("correctness"),
                "groundedness": result.get("groundedness"),
                "citation_correct": result.get("citation_correct"),
                "irrelevant_content": result.get("irrelevant_content"),
                "abstention_correct": result.get("abstention_correct"),
                "first_supporting_rank": result.get("first_supporting_rank"),
                "retrieval_total_ms": result.get("timing_ms", {}).get("retrieval_total_ms"),
                "generation_ms": result.get("timing_ms", {}).get("generation_ms"),
                "total_ms": result.get("timing_ms", {}).get("total_ms"),
                "diagnostic": result.get("diagnostic"),
                "error": result.get("error", ""),
            }
        )
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()) if rows else ["case_id"])
        writer.writeheader()
        writer.writerows(rows)


def _write_markdown_summary(path: Path, results: list[dict[str, Any]]) -> None:
    by_case: dict[str, dict[str, dict[str, Any]]] = {}
    for result in results:
        by_case.setdefault(result["case_id"], {})[result["mode"]] = result

    lines = [
        "# Live PDF Comparison Summary",
        "",
        "| Case | Type | Expected evidence | Mixed result | PDF-only result | Evidence rank | Citation correct | Irrelevant content | TTFT | Total |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for case_id, modes in sorted(by_case.items()):
        mixed = modes.get(MIXED_SCOPE.name, {})
        pdf_only = modes.get(PDF_ONLY.name, {})
        expected = pdf_only.get("expected_evidence") or mixed.get("expected_evidence") or []
        expected_label = ", ".join(
            f"{item.get('document_name')} p.{item.get('page')} #{item.get('chunk_id')}"
            for item in expected
        ) or "abstention-only"
        rank_value = pdf_only.get("first_supporting_rank")
        citation_ok = pdf_only.get("citation_correct")
        irrelevant = pdf_only.get("irrelevant_content")
        ttft = pdf_only.get("timing_ms", {}).get("ttft_before_fetch_ms")
        total = pdf_only.get("timing_ms", {}).get("total_ms")
        lines.append(
            "| {case} | {category} | {expected} | {mixed_status} | {pdf_status} | {rank} | {citation} | {irrelevant} | {ttft} | {total} |".format(
                case=case_id,
                category=(pdf_only.get("category") or mixed.get("category") or "n/a"),
                expected=expected_label,
                mixed_status=mixed.get("status", "n/a"),
                pdf_status=pdf_only.get("status", "n/a"),
                rank=rank_value if rank_value is not None else "-",
                citation=citation_ok if citation_ok is not None else "-",
                irrelevant=irrelevant if irrelevant is not None else "-",
                ttft=ttft if ttft is not None else "n/a",
                total=total if total is not None else "n/a",
            )
        )
    atomic_write_text(path, "\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--suite",
        type=Path,
        default=ROOT / "benchmarks" / "live-pdf-six-case-v1.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "benchmarks" / "live-pdf-six-case-results.json",
    )
    parser.add_argument(
        "--mode",
        choices=["pdf_only", "mixed_pdf_mission_eval_only", "both"],
        default="both",
    )
    parser.add_argument(
        "--continue-on-case-error",
        action="store_true",
        default=True,
    )
    args = parser.parse_args()

    settings = build_settings()
    cases = load_cases(args.suite)
    modes = [PDF_ONLY, MIXED_SCOPE] if args.mode == "both" else [PDF_ONLY if args.mode == PDF_ONLY.name else MIXED_SCOPE]
    results: list[dict[str, Any]] = []
    exit_code = 0

    embeddings.load_model(settings.embedding_model_path)
    db.init_pool(settings.database_url, min_connections=1, max_connections=4)
    try:
        for case in cases:
            for mode in modes:
                print(f"[eval] case={case.case_id} mode={mode.name} started_at={utc_now_iso()}", flush=True)
                try:
                    results.append(evaluate_case(case, mode, settings))
                except Exception as error:  # noqa: BLE001
                    exit_code = 2
                    failure = {
                        "case_id": case.case_id,
                        "category": case.category,
                        "mode": mode.name,
                        "query": case.query,
                        "started_at": utc_now_iso(),
                        "finished_at": utc_now_iso(),
                        "status": "error",
                        "should_abstain": case.should_abstain,
                        "expected_evidence": case.expected_evidence,
                        "error": str(error),
                        "traceback": traceback.format_exc(),
                    }
                    results.append(failure)
                    print(f"[eval] case={case.case_id} mode={mode.name} failed error={error}", flush=True)
                    if not args.continue_on_case_error:
                        raise
    finally:
        db.close_pool()

    report = {
        "schema_version": 1,
        "generated_at": utc_now_iso(),
        "suite": str(args.suite),
        "modes": [mode.name for mode in modes],
        "metadata": {
            "database_url_redacted": settings.database_url.rsplit("@", 1)[-1],
            "ollama_url": settings.ollama_url,
            "llm_model": settings.llm_model,
            "min_source_similarity": settings.min_source_similarity,
            "continue_on_case_error": args.continue_on_case_error,
        },
        "summary": summarize(results),
        "results": results,
    }
    atomic_write_text(args.output, json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    _write_markdown_summary(args.output.with_suffix(".md"), results)
    _write_csv_summary(args.output.with_suffix(".csv"), results)
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2), flush=True)
    print(f"Report written to {args.output}", flush=True)
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
