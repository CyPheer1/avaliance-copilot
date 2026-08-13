from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from evaluate_live_pdf_cases import (
    ROOT,
    build_settings,
    citation_correctness,
    load_cases,
    read_env_value,
)

from app import db, embeddings  # type: ignore
from app.schemas import RetrieveRequest  # type: ignore
from app.search_pipeline import run_search_pipeline  # type: ignore


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def post_json(url: str, payload: dict[str, Any], headers: dict[str, str] | None = None, timeout: float = 60.0) -> dict[str, Any]:
    request_headers = {"Content-Type": "application/json", **(headers or {})}
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=request_headers,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def login(base_url: str, username: str, password: str) -> str:
    payload = post_json(
        f"{base_url.rstrip('/')}/api/auth/login",
        {"username": username, "password": password},
        timeout=30.0,
    )
    token = payload.get("token")
    if not token:
        raise RuntimeError("Login response did not contain a token")
    return token


def api_search(base_url: str, token: str, query: str, request_id: str) -> tuple[dict[str, Any], float]:
    started = time.perf_counter()
    payload = post_json(
        f"{base_url.rstrip('/')}/api/search",
        {
            "query": query,
            "topK": 5,
            "corpusScope": "PDF",
            "requestId": request_id,
        },
        headers={"Authorization": f"Bearer {token}"},
        timeout=660.0,
    )
    return payload, round((time.perf_counter() - started) * 1000, 3)


def evaluator_run(query: str, request_id: str, settings: Any) -> tuple[dict[str, Any], float]:
    started = time.perf_counter()
    retrieve_request = RetrieveRequest(
        query=query,
        top_k=5,
        corpus_scope="PDF",
        request_id=request_id,
    )
    retrieve_response, response, trace = run_search_pipeline(retrieve_request, settings)
    latency_ms = round((time.perf_counter() - started) * 1000, 3)
    return {
        "answer": response.answer,
        "confidence": response.confidence,
        "diagnostic": response.diagnostic,
        "citations": [
            {
                "citation_id": citation.citation_id,
                "request_id": citation.request_id,
                "chunk_id": citation.chunk_id,
                "document_id": citation.document_id,
                "document_name": citation.document_name,
                "page": citation.page,
                "corpus_scope": citation.corpus_scope,
            }
            for citation in response.citations
        ],
        "selection_chunk_ids": trace["selection"]["selected_chunk_ids"],
        "retrieval_top_chunk_ids": [row["chunk_id"] for row in trace["retrieval"]["final_rows"][:5]],
        "latency_ms": latency_ms,
    }, latency_ms


def main() -> None:
    parser = argparse.ArgumentParser(description="Run live production/evaluator parity and Novacom stability checks.")
    parser.add_argument("--suite", type=Path, default=ROOT / "benchmarks" / "live-pdf-six-case-v1.json")
    parser.add_argument("--output", type=Path, default=ROOT / "benchmarks" / "results" / "live-pdf-six-case-v1" / "live-api-parity.json")
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password")
    parser.add_argument("--novacom-runs", type=int, default=10)
    args = parser.parse_args()

    password = (
        args.password
        or read_env_value(ROOT / ".env", "ADMIN_PASSWORD")
    )
    if not password:
        raise SystemExit("ADMIN_PASSWORD not found in .env and --password was not provided")

    settings = build_settings()
    cases = load_cases(args.suite)
    token = login(args.base_url, args.username, password)

    embeddings.load_model(settings.embedding_model_path)
    db.init_pool(settings.database_url, min_connections=1, max_connections=4)
    try:
        api_once_results: list[dict[str, Any]] = []
        for case in cases:
            payload, latency_ms = api_search(args.base_url, token, case.query, f"api-once-{case.case_id}")
            api_once_results.append(
                {
                    "case_id": case.case_id,
                    "query": case.query,
                    "answer": payload.get("answer"),
                    "citations": payload.get("citations") or [],
                    "confidence": payload.get("confidence"),
                    "latency_ms": latency_ms,
                }
            )

        novacom = next(case for case in cases if case.case_id == "LIVE-PDF-A")
        api_runs: list[dict[str, Any]] = []
        evaluator_runs: list[dict[str, Any]] = []
        for index in range(1, args.novacom_runs + 1):
            request_id = f"novacom-parity-{index:02d}"
            api_payload, api_latency_ms = api_search(args.base_url, token, novacom.query, request_id)
            evaluator_payload, evaluator_latency_ms = evaluator_run(novacom.query, request_id, settings)
            api_runs.append(
                {
                    "run": index,
                    "request_id": request_id,
                    "answer": api_payload.get("answer"),
                    "citations": api_payload.get("citations") or [],
                    "confidence": api_payload.get("confidence"),
                    "latency_ms": api_latency_ms,
                    "answer_ok": "Pauline Vasseur" in (api_payload.get("answer") or "") and "flux temps réel" in (api_payload.get("answer") or ""),
                    "citation_ok": any(
                        citation.get("chunkId") == 3597 and citation.get("page") == 13
                        for citation in (api_payload.get("citations") or [])
                    ),
                }
            )
            evaluator_runs.append(
                {
                    "run": index,
                    "request_id": request_id,
                    **evaluator_payload,
                    "answer_ok": "Pauline Vasseur" in evaluator_payload["answer"] and "flux temps réel" in evaluator_payload["answer"],
                    "citation_ok": any(
                        citation["chunk_id"] == 3597 and citation["page"] == 13
                        for citation in evaluator_payload["citations"]
                    ),
                }
            )
    finally:
        db.close_pool()

    report = {
        "generated_at": utc_now_iso(),
        "suite": str(args.suite),
        "api_once_results": api_once_results,
        "novacom_stability": {
            "api": {
                "runs": api_runs,
                "answer_success_rate": round(sum(run["answer_ok"] for run in api_runs) / len(api_runs), 4),
                "citation_success_rate": round(sum(run["citation_ok"] for run in api_runs) / len(api_runs), 4),
                "unique_answers": sorted({run["answer"] for run in api_runs}),
            },
            "evaluator": {
                "runs": evaluator_runs,
                "answer_success_rate": round(sum(run["answer_ok"] for run in evaluator_runs) / len(evaluator_runs), 4),
                "citation_success_rate": round(sum(run["citation_ok"] for run in evaluator_runs) / len(evaluator_runs), 4),
                "unique_answers": sorted({run["answer"] for run in evaluator_runs}),
            },
            "parity": {
                "all_answers_equal": all(api["answer"] == evaluator["answer"] for api, evaluator in zip(api_runs, evaluator_runs, strict=True)),
                "all_citations_equal": all(
                    [
                        (citation.get("chunkId"), citation.get("documentId"), citation.get("page"))
                        for citation in api["citations"]
                    ]
                    == [
                        (citation["chunk_id"], citation["document_id"], citation["page"])
                        for citation in evaluator["citations"]
                    ]
                    for api, evaluator in zip(api_runs, evaluator_runs, strict=True)
                ),
            },
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"Report written to {args.output}")


if __name__ == "__main__":
    main()
