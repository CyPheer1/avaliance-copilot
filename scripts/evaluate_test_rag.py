"""Evaluate the complete TEST_RAG.md-derived 38-case live PDF corpus suite.

This evaluator calls the public backend API, keeps every raw answer and citation,
and applies a transparent conservative rubric:

* factual answer: every normalized numeric fact plus >= 85% significant-term
  recall, and at least one citation to the expected physical PDF page;
* negative answer: canonical abstention with no citations;
* style: non-abstained answers must carry citations and no internal JSON/think
  leakage.

It is evaluation-only and does not modify the indexed corpus.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import statistics
import time
import unicodedata
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CANONICAL_ABSTENTION = "Information insuffisante dans le corpus pour répondre de manière fiable."
STOP_WORDS = {
    "a", "ai", "ait", "au", "aux", "avec", "ce", "ces", "cet", "cette", "comme", "contre",
    "d", "dans", "de", "des", "du", "elle", "en", "est", "et", "il", "la", "le", "les",
    "leur", "leurs", "l", "mais", "on", "ou", "par", "pas", "plus", "pour", "qu", "que",
    "quel", "quelle", "quelles", "quels", "s", "sa", "sans", "se", "ses", "soit", "son",
    "sur", "t", "un", "une", "vers", "y",
}
DOCUMENTS = {
    "AVL-2025-SIN-014": "01_Helvia_Assurances_Refonte_Sinistres_Bilan_Projet.pdf",
    "AVL-2025-NVC-031": "02_Novacom_Telecom_Plateforme_Data_Retention_Bilan_Mission.pdf",
    "AVL-2025-TAL-047": "03_TransAlpes_Logistique_Securisation_SI_NIS2_Rapport_Programme.pdf",
    "AVL-2025-VLT-022": "04_Volteris_Energies_Socle_IoT_Telereleve_Dossier_Projet.pdf",
    "AVL-2026-STL-008": "05_Groupe_Santelia_Portail_Patient_Interoperabilite_Dossier_Projet.pdf",
}


def fold(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    return "".join(char for char in value if not unicodedata.combining(char)).casefold()


def terms(value: str) -> set[str]:
    return {
        term for term in re.findall(r"[a-z0-9]+", fold(value))
        if len(term) >= 3 and term not in STOP_WORDS
    }


def numeric_facts(value: str) -> set[str]:
    compact = fold(value).replace("\u00a0", " ")
    return {
        re.sub(r"\s+", "", match).replace(",", ".")
        for match in re.findall(r"\d+(?:[\s,.]\d+)*(?:\s*%|\s*(?:€|eur|h|jours?|mois|minutes?))?", compact)
    }


def percentile(values: list[float], percentile_value: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = math.ceil(percentile_value * len(ordered)) - 1
    return ordered[max(0, min(index, len(ordered) - 1))]


def post_json(url: str, payload: dict[str, Any], headers: dict[str, str] | None = None) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=700) as response:
        return json.loads(response.read().decode("utf-8"))


def score(case: dict[str, Any], response: dict[str, Any], latency_ms: float) -> dict[str, Any]:
    answer = str(response.get("answer") or "").strip()
    citations = response.get("citations") or []
    expected_document = DOCUMENTS[case["referent_tag"]]
    expected_page = case["expected_page"]
    abstained = answer == CANONICAL_ABSTENTION
    negative = case["type"] == "negatif"
    expected_terms = terms(case["expected_answer"])
    answer_terms = terms(answer)
    matched_terms = sorted(expected_terms & answer_terms)
    recall = len(matched_terms) / len(expected_terms) if expected_terms else 1.0
    expected_numbers = numeric_facts(case["expected_answer"])
    answer_numbers = numeric_facts(answer)
    missing_numbers = sorted(expected_numbers - answer_numbers)
    matching_citations = [
        citation for citation in citations
        if citation.get("documentName") == expected_document
        and citation.get("page") == expected_page
    ]
    citation_correct = not citations if negative else bool(matching_citations)
    style_ok = (
        (abstained and not citations)
        or (
            bool(citations)
            and "<think" not in answer.casefold()
            and not answer.lstrip().startswith("{")
            and len(answer) > 12
        )
    )
    if negative:
        answer_correct = abstained and not citations
        completeness = 1.0 if answer_correct else 0.0
    else:
        answer_correct = not abstained and recall >= 0.85 and not missing_numbers
        completeness = recall if not abstained else 0.0
    return {
        **case,
        "expected_document": expected_document,
        "answer": answer,
        "diagnostic": response.get("diagnostic"),
        "confidence": response.get("confidence"),
        "citations": citations,
        "latency_ms": round(latency_ms, 3),
        "abstained": abstained,
        "term_recall": round(recall, 4),
        "expected_term_count": len(expected_terms),
        "matched_terms": matched_terms,
        "missing_numeric_facts": missing_numbers,
        "answer_correct": answer_correct,
        "citation_correct": citation_correct,
        "style_ok": style_ok,
        "complete": answer_correct and citation_correct and style_ok,
        "completeness": round(completeness, 4),
    }


def rate(rows: list[dict[str, Any]], field: str) -> float | None:
    return round(sum(row[field] for row in rows) / len(rows), 4) if rows else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=Path, default=Path("benchmarks/results/test-rag-20260811/cases.json"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default=os.getenv("ADMIN_PASSWORD"))
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()
    if not args.password:
        raise SystemExit("Set ADMIN_PASSWORD or provide --password.")

    suite = json.loads(args.cases.read_text(encoding="utf-8"))
    login = post_json(
        f"{args.base_url.rstrip('/')}/api/auth/login",
        {"username": args.username, "password": args.password},
    )
    token = login["token"]
    rows: list[dict[str, Any]] = []
    for index, case in enumerate(suite["cases"], start=1):
        print(f"[{index:02d}/{len(suite['cases']):02d}] {case['case_id']}", flush=True)
        started = time.perf_counter()
        try:
            response = post_json(
                f"{args.base_url.rstrip('/')}/api/search",
                {"query": case["query"], "topK": args.top_k, "corpusScope": "PDF", "requestId": f"test-rag-live:{case['case_id']}"},
                {"Authorization": f"Bearer {token}"},
            )
            row = score(case, response, (time.perf_counter() - started) * 1000)
            row["request_error"] = None
        except Exception as error:  # Preserve all failures as benchmark data.
            row = {
                **case,
                "request_error": str(error),
                "answer": "",
                "citations": [],
                "latency_ms": round((time.perf_counter() - started) * 1000, 3),
                "answer_correct": False,
                "citation_correct": False,
                "style_ok": False,
                "complete": False,
                "completeness": 0.0,
            }
        rows.append(row)

    factual = [row for row in rows if row["type"] == "factuel"]
    negative = [row for row in rows if row["type"] == "negatif"]
    by_mission: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_mission[row["referent_tag"]].append(row)
    mission_summary = {
        tag: {
            "cases": len(items),
            "complete": sum(item["complete"] for item in items),
            "complete_rate": rate(items, "complete"),
            "mean_completeness": round(statistics.mean(item["completeness"] for item in items), 4),
            "mean_latency_ms": round(statistics.mean(item["latency_ms"] for item in items), 3),
            "expected_page_citation_rate": rate(items, "citation_correct"),
        }
        for tag, items in by_mission.items()
    }
    latencies = [row["latency_ms"] for row in rows]
    report = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "suite_source": str(args.cases),
        "execution": {"base_url": args.base_url, "corpus_scope": "PDF", "top_k": args.top_k},
        "rubric": {
            "factual": "all expected numeric facts and >=85% significant-term recall",
            "citation": "expected document and physical page cited",
            "negative": "canonical abstention with zero citations",
            "complete": "answer, citation, and style all pass",
        },
        "summary": {
            "cases": len(rows),
            "request_errors": sum(row.get("request_error") is not None for row in rows),
            "strict_complete_rate": rate(rows, "complete"),
            "factual_answer_accuracy": rate(factual, "answer_correct"),
            "factual_citation_accuracy": rate(factual, "citation_correct"),
            "negative_abstention_accuracy": rate(negative, "answer_correct"),
            "style_pass_rate": rate(rows, "style_ok"),
            "mean_completeness": round(statistics.mean(row["completeness"] for row in rows), 4),
            "latency_ms": {
                "mean": round(statistics.mean(latencies), 3),
                "median": round(statistics.median(latencies), 3),
                "p95": round(percentile(latencies, 0.95) or 0.0, 3),
                "maximum": round(max(latencies), 3),
            },
        },
        "mission_summary": mission_summary,
        "results": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
