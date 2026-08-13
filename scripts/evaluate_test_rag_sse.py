"""Evaluate every natural TEST_RAG.md case through Spring's public POST-SSE API.

This is an external acceptance evaluator: it only logs in through Spring and calls
/api/search/stream with PDF scope.  It never accesses Postgres or service-ia.
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
MISSION_DOCUMENTS = {
    "Helvia Assurances": "01_Helvia_Assurances_Refonte_Sinistres_Bilan_Projet.pdf",
    "Novacom Télécom": "02_Novacom_Telecom_Plateforme_Data_Retention_Bilan_Mission.pdf",
    "TransAlpes Logistique": "03_TransAlpes_Logistique_Securisation_SI_NIS2_Rapport_Programme.pdf",
    "Volteris Énergies": "04_Volteris_Energies_Socle_IoT_Telereleve_Dossier_Projet.pdf",
    "Groupe Santélia": "05_Groupe_Santelia_Portail_Patient_Interoperabilite_Dossier_Projet.pdf",
}
STOP_WORDS = {
    "a", "ai", "ait", "au", "aux", "avec", "ce", "ces", "cet", "cette", "comme", "contre",
    "d", "dans", "de", "des", "du", "elle", "en", "est", "et", "il", "la", "le", "les",
    "leur", "leurs", "l", "mais", "on", "ou", "par", "pas", "plus", "pour", "qu", "que",
    "quel", "quelle", "quelles", "quels", "s", "sa", "sans", "se", "ses", "soit", "son",
    "sur", "t", "un", "une", "vers", "y",
}


def fold(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(char for char in normalized if not unicodedata.combining(char)).casefold()


def terms(value: str) -> set[str]:
    return {term for term in re.findall(r"[a-z0-9]+", fold(value)) if len(term) >= 3 and term not in STOP_WORDS}


def numeric_facts(value: str) -> set[str]:
    compact = fold(value).replace("\u00a0", " ")
    return {
        re.sub(r"\s+", "", match).replace(",", ".")
        for match in re.findall(r"\d+(?:[\s,.]\d+)*(?:\s*%|\s*(?:€|eur|h|jours?|mois|minutes?|etp|msg/s))?", compact)
    }


def parse_pages(expected: str) -> list[int]:
    match = re.search(r"(?:—|-)\s*p\.\s*([0-9 ,et]+)\s*$", expected, flags=re.IGNORECASE)
    return [int(value) for value in re.findall(r"\d+", match.group(1))] if match else []


def expected_answer(expected: str) -> str:
    return re.sub(r"\s*(?:—|-)\s*p\.\s*[0-9 ,et]+\s*$", "", expected, flags=re.IGNORECASE).strip()


def parse_cases(markdown: Path) -> list[dict[str, Any]]:
    source = markdown.read_text(encoding="utf-8")
    sections = re.split(r"^## \d+\. ", source, flags=re.MULTILINE)[1:]
    cases: list[dict[str, Any]] = []
    for section in sections:
        title, body = section.split("\n", 1)
        mission = next((name for name in MISSION_DOCUMENTS if name in title), None)
        if mission is None:
            continue
        pattern = re.compile(
            r"^\d+\. \*\*(?P<family>[^*]+)\*\*\s+—\s+(?P<query>.+?)\n\s*>\s*(?P<expected>.+?)(?=\n\d+\. \*\*|\Z)",
            re.MULTILINE | re.DOTALL,
        )
        for number, match in enumerate(pattern.finditer(body), start=1):
            raw_expected = " ".join(match.group("expected").split())
            family = match.group("family").strip()
            if family == "PIÈGE":
                raw_expected = "Information absente du corpus."
            cases.append({
                "case_id": f"{mission[:3].upper()}-{number:02d}",
                "mission": mission,
                "family": family,
                "query": " ".join(match.group("query").split()),
                "expected_answer": expected_answer(raw_expected),
                "expected_pages": parse_pages(raw_expected),
                "expected_document": MISSION_DOCUMENTS[mission],
                "type": "negatif" if family == "PIÈGE" else "factuel",
            })
    if len(cases) != 50:
        raise ValueError(f"Expected 50 TEST_RAG cases, parsed {len(cases)}")
    return cases


def post_json(url: str, payload: dict[str, Any], headers: dict[str, str] | None = None) -> dict[str, Any]:
    request = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json", **(headers or {})}, method="POST")
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode())


def stream_search(base_url: str, token: str, case: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    payload = {"query": case["query"], "topK": 15, "corpusScope": "PDF", "requestId": f"test-rag-sse:{case['case_id']}"}
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/search/stream", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Accept": "text/event-stream", "Authorization": f"Bearer {token}"}, method="POST",
    )
    answer: list[str] = []
    citation_events: list[list[dict[str, Any]]] = []
    validation: list[dict[str, Any]] = []
    events: list[str] = []
    done: dict[str, Any] | None = None
    event: str | None = None
    with urllib.request.urlopen(request, timeout=700) as response:
        for raw in response:
            line = raw.decode().rstrip("\r\n")
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:") and event:
                data = json.loads(line[5:].strip())
                events.append(event)
                if event == "delta":
                    answer.append(str(data.get("token") or ""))
                elif event in {"citation", "citations"}:
                    citation_events.append(data.get("citations") or [])
                elif event == "validation":
                    validation.append(data)
                elif event == "done":
                    done = data
                elif event == "error":
                    raise RuntimeError(data.get("error") or "SSE error")
    citations = (done or {}).get("citations") if done else None
    if not citations:
        citations = [citation for event_citations in citation_events for citation in event_citations]
    unique = {str(c.get("citationId") or f"{c.get('chunkId')}:{c.get('sourceIndex')}"): c for c in citations or []}
    # A grounded abstention deliberately has validationPassed=false; it is still
    # a well-formed terminal SSE exchange. Factual scoring separately requires
    # citations and marker/card consistency.
    protocol_ok = bool(done) and bool(validation) and bool(events) and events[-1] == "done"
    return ({"answer": "".join(answer).strip(), "citations": list(unique.values()), "done": done or {}, "validation": validation}, {"events": events, "protocol_ok": protocol_ok})


def percentile(values: list[float], value: float) -> float:
    return sorted(values)[max(0, math.ceil(value * len(values)) - 1)]


def score(case: dict[str, Any], response: dict[str, Any], protocol: dict[str, Any], latency_ms: float) -> dict[str, Any]:
    answer = response["answer"]
    citations = response["citations"]
    negative = case["type"] == "negatif"
    abstained = answer == CANONICAL_ABSTENTION
    expected_terms = terms(case["expected_answer"])
    recall = len(expected_terms & terms(answer)) / len(expected_terms) if expected_terms else 1.0
    missing_numbers = sorted(numeric_facts(case["expected_answer"]) - numeric_facts(answer))
    matching = [c for c in citations if c.get("documentName") == case["expected_document"] and (not case["expected_pages"] or c.get("page") in case["expected_pages"])]
    cited_pages = sorted({c.get("page") for c in matching if isinstance(c.get("page"), int)})
    citation_correct = not citations if negative else bool(matching) and set(case["expected_pages"]).issubset(cited_pages)
    source_indexes = [c.get("sourceIndex") for c in citations]
    markers = {int(item) for item in re.findall(r"\[(\d+)\]", answer)}
    cards_ok = bool(citations) and markers == set(source_indexes) and len(source_indexes) == len(set(source_indexes))
    style_ok = (abstained and not citations) if negative else (bool(markers) and cards_ok and "<think" not in answer.casefold() and not answer.lstrip().startswith("{"))
    answer_correct = (abstained and not citations) if negative else (not abstained and recall >= .85 and not missing_numbers)
    return {**case, "answer": answer, "citations": citations, "validation": response["validation"], "sse_events": protocol["events"], "protocol_ok": protocol["protocol_ok"], "latency_ms": round(latency_ms, 3), "term_recall": round(recall, 4), "missing_numeric_facts": missing_numbers, "answer_correct": answer_correct, "citation_correct": citation_correct, "source_cards_ok": (not citations if negative else cards_ok), "style_ok": style_ok, "complete": answer_correct and citation_correct and style_ok and protocol["protocol_ok"], "completeness": 1.0 if negative and answer_correct else round(recall if not abstained else 0.0, 4)}


def markdown_report(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = ["# TEST_RAG — évaluation SSE publique", "", f"Généré : {report['generated_at']}", "", "## Synthèse", "", f"- Cas exécutés : **{summary['cases']}**", f"- Réussite stricte complète : **{summary['strict_complete_rate']:.2%}**", f"- Exactitude factuelle : **{summary['factual_answer_accuracy']:.2%}**", f"- Complétude factuelle moyenne : **{summary['mean_completeness']:.2%}**", f"- Exactitude document/page : **{summary['factual_citation_accuracy']:.2%}**", f"- Abstention négative : **{summary['negative_abstention_accuracy']:.2%}**", f"- Protocole/style : **{summary['style_protocol_pass_rate']:.2%}**", f"- Latence ms (moyenne / médiane / P95 / max) : **{summary['latency_ms']['mean']:.0f} / {summary['latency_ms']['median']:.0f} / {summary['latency_ms']['p95']:.0f} / {summary['latency_ms']['maximum']:.0f}**", "", "## Par mission", "", "| Mission | Cas | Complets | Taux |", "|---|---:|---:|---:|"]
    for mission, value in report["mission_summary"].items():
        lines.append(f"| {mission} | {value['cases']} | {value['complete']} | {value['complete_rate']:.2%} |")
    failures = [row for row in report["results"] if not row["complete"]]
    lines += ["", "## Échecs", ""]
    if not failures:
        lines.append("Aucun échec reproductible.")
    for row in failures:
        citations = "; ".join(f"{c.get('documentName')} p.{c.get('page')} chunk {c.get('chunkId')} [#{c.get('sourceIndex')}]" for c in row["citations"]) or "aucune"
        if row.get("request_error"):
            root_cause = f"échec de requête SSE : {row['request_error']}"
        elif not row["protocol_ok"]:
            root_cause = "séquence SSE terminale incomplète"
        elif row["validation"] and row["validation"][-1].get("passed") is False:
            root_cause = f"validation de provenance rejetée : {row['validation'][-1].get('diagnostic')}"
        elif not row["citation_correct"]:
            root_cause = "preuve sur document/page attendu incomplète ou absente"
        elif not row["answer_correct"]:
            root_cause = "réponse incomplète ou attribut demandé non extrait"
        else:
            root_cause = "incohérence marqueur/source ou style"
        lines += [f"### {row['case_id']} — {row['mission']} ({row['family']})", f"- Attendu : {row['expected_answer']} (pages {row['expected_pages'] or 'non spécifiée'})", f"- Obtenu : {row['answer'] or 'réponse vide'}", f"- Citations : {citations}", f"- Cause observée : {root_cause}.", f"- Mesures : recall={row['term_recall']}, chiffres manquants={row['missing_numeric_facts']}, citation={row['citation_correct']}, cartes={row['source_cards_ok']}, protocole={row['protocol_ok']}.", ""]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark", type=Path, default=Path("TEST_RAG.md"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default=os.getenv("ADMIN_PASSWORD"))
    args = parser.parse_args()
    if not args.password:
        raise SystemExit("Set ADMIN_PASSWORD or pass --password.")
    cases = parse_cases(args.benchmark)
    token = post_json(f"{args.base_url.rstrip('/')}/api/auth/login", {"username": args.username, "password": args.password})["token"]
    rows = []
    for index, case in enumerate(cases, 1):
        print(f"[{index:02d}/{len(cases):02d}] {case['case_id']}", flush=True)
        started = time.perf_counter()
        try:
            response, protocol = stream_search(args.base_url, token, case)
            row = score(case, response, protocol, (time.perf_counter() - started) * 1000)
            row["request_error"] = None
        except Exception as error:
            row = {**case, "answer": "", "citations": [], "request_error": str(error), "latency_ms": round((time.perf_counter() - started) * 1000, 3), "answer_correct": False, "citation_correct": False, "source_cards_ok": False, "style_ok": False, "protocol_ok": False, "complete": False, "completeness": 0.0, "term_recall": 0.0, "missing_numeric_facts": [], "sse_events": []}
        rows.append(row)
    factual = [row for row in rows if row["type"] == "factuel"]
    negative = [row for row in rows if row["type"] == "negatif"]
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows: grouped[row["mission"]].append(row)
    latencies = [row["latency_ms"] for row in rows]
    summary = {"cases": len(rows), "request_errors": sum(bool(row["request_error"]) for row in rows), "strict_complete_rate": sum(row["complete"] for row in rows) / len(rows), "factual_answer_accuracy": sum(row["answer_correct"] for row in factual) / len(factual), "mean_completeness": statistics.mean(row["completeness"] for row in factual), "factual_citation_accuracy": sum(row["citation_correct"] for row in factual) / len(factual), "negative_abstention_accuracy": sum(row["answer_correct"] for row in negative) / len(negative), "style_protocol_pass_rate": sum(row["style_ok"] and row["protocol_ok"] for row in rows) / len(rows), "latency_ms": {"mean": statistics.mean(latencies), "median": statistics.median(latencies), "p95": percentile(latencies, .95), "maximum": max(latencies)}}
    report = {"schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(), "suite_source": str(args.benchmark), "execution": {"base_url": args.base_url, "endpoint": "/api/search/stream", "corpus_scope": "PDF", "top_k": 15, "browser_acceptance": "Not run by this API-only evaluator; see separately executed Playwright tests."}, "previous_baseline": {"strict_complete_rate": .1316, "source": "benchmarks/results/test-rag-20260811/live-post-coverage-20260811.json"}, "summary": summary, "mission_summary": {mission: {"cases": len(items), "complete": sum(item["complete"] for item in items), "complete_rate": sum(item["complete"] for item in items) / len(items)} for mission, items in grouped.items()}, "results": rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.output.with_suffix(".md").write_text(markdown_report(report), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"Wrote {args.output} and {args.output.with_suffix('.md')}")


if __name__ == "__main__":
    main()
