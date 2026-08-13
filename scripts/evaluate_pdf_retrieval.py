"""Measure live PDF evidence recall at each production retrieval stage.

The evaluator calls the internal-only ``/retrieve/trace`` endpoint from inside
``service-ia``. It does not use benchmark data for indexing or ranking.
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_TRACE_CLIENT = r"""
import json
import os
import sys
import urllib.request
payload = json.load(sys.stdin)
request = urllib.request.Request(
    'http://127.0.0.1:8000/retrieve/trace',
    data=json.dumps(payload).encode('utf-8'),
    headers={'Content-Type': 'application/json', 'X-Internal-Token': os.environ['INTERNAL_TOKEN']},
    method='POST',
)
with urllib.request.urlopen(request, timeout=660) as response:
    print(response.read().decode('utf-8'))
"""

_STAGE_KEYS = {
    "vector": "vector_rows",
    "lexical": "text_rows",
    "fused": "candidate_rows",
    "final": "final_rows",
}


def _rank(rows: list[dict[str, Any]], evidence: dict[str, Any]) -> int | None:
    for index, row in enumerate(rows, start=1):
        if (
            row.get("chunk_id") == evidence["chunk_id"]
            and row.get("document_id") == evidence["document_id"]
            and row.get("page") == evidence["page"]
        ):
            return index
    return None


def _trace(compose: list[str], payload: dict[str, Any]) -> dict[str, Any]:
    completed = subprocess.run(
        [*compose, "exec", "-T", "service-ia", "python", "-c", _TRACE_CLIENT],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(completed.stdout)


def _stage_summary(case_rows: list[dict[str, Any]], stage: str) -> dict[str, float | int]:
    ranks = [row["ranks"][stage] for row in case_rows if row["ranks"][stage] is not None]
    total = len(case_rows)
    return {
        "recall_at_5": round(sum(rank <= 5 for rank in ranks) / total, 4),
        "recall_at_10": round(sum(rank <= 10 for rank in ranks) / total, 4),
        "mrr": round(sum(1 / rank for rank in ranks) / total, 4),
        "document_accuracy": round(sum(row["document_matches"][stage] for row in case_rows) / total, 4),
        "page_accuracy": round(sum(row["page_matches"][stage] for row in case_rows) / total, 4),
        "evidence_found": len(ranks),
        "cases": total,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", type=Path, default=Path("benchmarks/pdf-golden-v2.json"))
    parser.add_argument("--output", type=Path, default=Path("benchmarks/results/pdf-golden-v2/retrieval-trace.json"))
    parser.add_argument(
        "--candidate-pools-output",
        type=Path,
        default=None,
        help="Optional immutable export of post-RRF/pre-reranker pools for offline reranker comparison.",
    )
    parser.add_argument("--candidate-limit", type=int, default=None, help="Recorded expected live configuration; does not mutate a running service.")
    parser.add_argument("--compose-file", action="append", default=[])
    args = parser.parse_args()
    if not args.compose_file:
        args.compose_file = ["docker-compose.yml"]

    suite = json.loads(args.suite.read_text(encoding="utf-8"))
    compose = ["docker", "compose"]
    for compose_file in args.compose_file:
        compose.extend(["-f", compose_file])

    case_rows: list[dict[str, Any]] = []
    traces: list[dict[str, Any]] = []
    candidate_pools: list[dict[str, Any]] = []
    for case in suite["cases"]:
        if case["should_abstain"]:
            continue
        trace = _trace(compose, {
            "query": case["query"],
            "top_k": 5,
            "corpus_scope": "PDF",
            "request_id": f"{suite['suite_id']}:{case['case_id']}:retrieval",
        })
        traces.append(trace)
        evidence = case["expected_evidence"][0]
        candidate_pools.append(
            {
                "schema_version": 1,
                "pool_id": f"{suite['suite_id']}:{case['case_id']}",
                "query": case["query"],
                "expected_evidence": case["expected_evidence"],
                "retrieval_provenance": {
                    "source_stage": "candidate_rows",
                    "corpus_scope": "PDF",
                    "candidate_limit": trace["candidate_limit"],
                },
                "candidates": trace["candidate_rows"],
            }
        )
        ranks = {
            stage: _rank(trace[_STAGE_KEYS[stage]], evidence)
            for stage in _STAGE_KEYS
        }
        case_rows.append({
            "case_id": case["case_id"],
            "expected": {key: evidence[key] for key in ("chunk_id", "document_id", "page")},
            "ranks": ranks,
            "document_matches": {
                stage: any(row.get("document_id") == evidence["document_id"] for row in trace[_STAGE_KEYS[stage]])
                for stage in _STAGE_KEYS
            },
            "page_matches": {
                stage: any(
                    row.get("document_id") == evidence["document_id"] and row.get("page") == evidence["page"]
                    for row in trace[_STAGE_KEYS[stage]]
                )
                for stage in _STAGE_KEYS
            },
            "timing_ms": {
                key: trace[key]
                for key in ("vector_elapsed_ms", "text_elapsed_ms", "fusion_elapsed_ms", "rerank_elapsed_ms")
            },
        })

    report = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "suite_id": suite["suite_id"],
        "purpose": "Evaluation-only live retrieval trace; no benchmark case is used to tune or index the corpus.",
        "execution": {
            "compose_files": args.compose_file,
            "requested_candidate_limit": args.candidate_limit,
            "live_candidate_limits": sorted({trace["candidate_limit"] for trace in traces}),
            "positive_cases": len(case_rows),
        },
        "summary": {stage: _stage_summary(case_rows, stage) for stage in _STAGE_KEYS},
        "median_timing_ms": {
            key: round(statistics.median(row["timing_ms"][key] for row in case_rows), 3)
            for key in ("vector_elapsed_ms", "text_elapsed_ms", "fusion_elapsed_ms", "rerank_elapsed_ms")
        },
        "cases": case_rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.candidate_pools_output is not None:
        pools_report = {
            "schema_version": 1,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "suite_id": suite["suite_id"],
            "purpose": "Frozen post-RRF/pre-reranker pools. Regenerate only when the corpus, index, or retrieval configuration changes.",
            "pools": candidate_pools,
        }
        args.candidate_pools_output.parent.mkdir(parents=True, exist_ok=True)
        args.candidate_pools_output.write_text(
            json.dumps(pools_report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"Wrote {args.candidate_pools_output}")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
