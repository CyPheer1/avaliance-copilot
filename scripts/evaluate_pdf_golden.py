"""Evaluate the versioned real-PDF golden suite through the public API."""

from __future__ import annotations

import argparse
import json
import os
import statistics
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CANONICAL_ABSTENTION = "Information insuffisante dans le corpus pour répondre de manière fiable."


def post_json(url: str, payload: dict[str, Any], headers: dict[str, str] | None = None) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=660) as response:
        return json.loads(response.read().decode("utf-8"))


def citation_matches(citation: dict[str, Any], evidence: dict[str, Any]) -> bool:
    return (
        citation.get("documentId") == evidence["document_id"]
        and citation.get("documentName") == evidence["document_name"]
        and citation.get("chunkId") == evidence["chunk_id"]
        and citation.get("page") == evidence["page"]
        and evidence["evidence_quote"] in (citation.get("content") or "")
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", type=Path, default=Path("benchmarks/pdf-golden-v2.json"))
    parser.add_argument("--output", type=Path, default=Path("benchmarks/results/pdf-golden-v2/baseline.json"))
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default=os.getenv("ADMIN_PASSWORD"))
    args = parser.parse_args()
    if not args.password:
        raise SystemExit("Set ADMIN_PASSWORD or provide --password.")

    suite = json.loads(args.suite.read_text(encoding="utf-8"))
    login = post_json(
        f"{args.base_url.rstrip('/')}/api/auth/login",
        {"username": args.username, "password": args.password},
    )
    token = login["token"]
    results: list[dict[str, Any]] = []

    for case in suite["cases"]:
        started = time.perf_counter()
        response = post_json(
            f"{args.base_url.rstrip('/')}/api/search",
            {
                "query": case["query"],
                "topK": 5,
                "corpusScope": "PDF",
                "requestId": f"{suite['suite_id']}:{case['case_id']}",
            },
            {"Authorization": f"Bearer {token}"},
        )
        latency_ms = round((time.perf_counter() - started) * 1000, 3)
        answer = response.get("answer") or ""
        citations = response.get("citations") or []
        if case["should_abstain"]:
            answer_correct = answer == CANONICAL_ABSTENTION
            citation_correct = not citations
        else:
            folded_answer = answer.casefold()
            answer_correct = all(fragment.casefold() in folded_answer for fragment in case["required_answer_fragments"])
            answer_correct = answer_correct and not any(
                fragment.casefold() in folded_answer for fragment in case["forbidden_answer_fragments"]
            )
            citation_correct = any(
                citation_matches(citation, evidence)
                for citation in citations
                for evidence in case["expected_evidence"]
            )
        results.append({
            "case_id": case["case_id"],
            "category": case["category"],
            "should_abstain": case["should_abstain"],
            "answer": answer,
            "confidence": response.get("confidence"),
            "citations": citations,
            "latency_ms": latency_ms,
            "answer_correct": answer_correct,
            "citation_correct": citation_correct,
            "grounded_correct": answer_correct and citation_correct,
        })

    positives = [result for result in results if not result["should_abstain"]]
    abstentions = [result for result in results if result["should_abstain"]]
    report = {
        "schema_version": 2,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "suite_id": suite["suite_id"],
        "suite_path": str(args.suite),
        "execution": {"base_url": args.base_url, "corpus_scope": "PDF", "top_k": 5},
        "summary": {
            "cases": len(results),
            "answer_accuracy": round(sum(result["answer_correct"] for result in results) / len(results), 4),
            "citation_accuracy": round(sum(result["citation_correct"] for result in results) / len(results), 4),
            "grounded_accuracy": round(sum(result["grounded_correct"] for result in results) / len(results), 4),
            "positive_answer_accuracy": round(sum(result["answer_correct"] for result in positives) / len(positives), 4),
            "abstention_accuracy": round(sum(result["answer_correct"] for result in abstentions) / len(abstentions), 4),
            "median_latency_ms": round(statistics.median(result["latency_ms"] for result in results), 3),
        },
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
