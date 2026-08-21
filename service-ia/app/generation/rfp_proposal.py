"""Structured RFP proposal composition handling standard, brief and full modes."""

from __future__ import annotations

import json
import logging
import time
import asyncio
from typing import Any, AsyncGenerator

from ..retrieval.vector_search import retrieve_for_requirements
from ..schemas import (
    RfpRequest,
    RfpResponse,
    RfpMetrics,
    RfpRequirements,
    RfpAtomicNeed,
    RfpSection,
    RfpProposal,
    RfpAnnexes,
    ComplianceMatrixRow,
    SourceRegisterEntry,
    EvidencePacket,
    RfpQualityReport,
    RfpSource,
    RfpCoverageItem,
)
from ..settings import Settings
from .ollama import OllamaStructuredOutputError, generate_text, generate_text_async
from .prompts import (
    RFP_CALL_A_PROMPT,
    RFP_CALL_A_SCHEMA,
    RFP_JSON_REPAIR_PROMPT,
    RFP_STANDARD_BATCH_PROMPT,
    RFP_STANDARD_SECTION_BATCH_SCHEMA,
    RFP_REPAIR_PROMPT,
)
from .rfp_quality import (
    validate_section,
    truncate_to_budget,
    _CITATION_PATTERN,
    _significant_terms,
    _SENTENCE_SPLIT_PATTERN,
)

logger = logging.getLogger(__name__)

class RfpInputError(ValueError):
    """The brief cannot be converted to actionable requirements."""


class RfpInfrastructureError(RuntimeError):
    """A required generation dependency is unavailable."""


class RfpValidationError(RuntimeError):
    """The generated proposal did not pass deterministic validation."""


class RfpGenerationError(RuntimeError):
    """The RFP generation budget was exhausted."""


STANDARD_SECTIONS_B = [
    {"key": "executive_summary", "title": "Synthèse Exécutive", "budget": 120},
    {"key": "client_needs_and_objectives", "title": "Compréhension du Besoin", "budget": 130},
    {"key": "proposed_solution", "title": "Solution Proposée", "budget": 160},
]
STANDARD_SECTIONS_C = [
    {"key": "delivery_and_milestones", "title": "Dispositif et Planning", "budget": 120},
    {"key": "security_risks_and_assumptions", "title": "Sécurité, Risques et Hypothèses", "budget": 100},
    {"key": "avaliance_fit_and_next_steps", "title": "Pourquoi Avaliance et Prochaines Étapes", "budget": 120},
]
BRIEF_SECTIONS = STANDARD_SECTIONS_B + [STANDARD_SECTIONS_C[0]]
FULL_SECTIONS = [
    {"key": key, "title": title, "budget": 110}
    for key, title in [
        ("executive_summary", "Synthèse exécutive"),
        ("context_understanding", "Compréhension du contexte"),
        ("stakes_and_problem", "Enjeux et problème à résoudre"),
        ("objectives_and_outcomes", "Objectifs et résultats attendus"),
        ("scope_inclusions", "Périmètre inclus"),
        ("scope_exclusions", "Périmètre exclu"),
        ("delivery_approach", "Approche de réalisation"),
        ("governance", "Gouvernance"),
        ("planning", "Planning et jalons"),
        ("team", "Équipe et responsabilités"),
        ("quality_assurance", "Assurance qualité"),
        ("security", "Sécurité et conformité"),
        ("data_management", "Gestion des données"),
        ("integration", "Intégration et architecture"),
        ("change_management", "Conduite du changement"),
        ("risks", "Risques et hypothèses"),
        ("deliverables", "Livrables"),
        ("commercial_terms", "Conditions de collaboration"),
        ("next_steps", "Prochaines étapes"),
    ]
]

def _safe_excerpt(response: str, limit: int = 240) -> str:
    return " ".join(response.split())[:limit]


def _parse_llm_json(response: str, *, request_id: str, stage: str) -> dict[str, Any]:
    try:
        parsed = json.loads(response)
    except json.JSONDecodeError as exc:
        logger.warning(
            "Invalid structured LLM JSON requestId=%s stage=%s length=%s excerpt=%r error=%s",
            request_id, stage, len(response), _safe_excerpt(response), exc.msg,
        )
        raise RfpInfrastructureError(f"Invalid JSON from LLM at {stage}") from exc
    if not isinstance(parsed, dict):
        raise RfpInfrastructureError(f"Structured LLM response must be an object at {stage}")
    return parsed


def _parse_sections(response: str, *, request_id: str, stage: str) -> list[RfpSection]:
    data = _parse_llm_json(response, request_id=request_id, stage=stage)
    try:
        return [RfpSection.model_validate(section) for section in data["sections"]]
    except (KeyError, TypeError, ValueError) as exc:
        logger.warning(
            "Invalid structured section payload requestId=%s stage=%s length=%s excerpt=%r error=%s",
            request_id, stage, len(response), _safe_excerpt(response), exc,
        )
        raise RfpInfrastructureError(f"Invalid section JSON from LLM at {stage}") from exc


def _normalize_atomic_needs(raw_needs: list[dict[str, Any]], brief: str) -> list[RfpAtomicNeed]:
    """Canonicalize requirements to exact excerpts from the authoritative brief."""
    needs: list[RfpAtomicNeed] = []
    seen_spans: set[tuple[int, int]] = set()
    cursor = 0
    for raw in raw_needs:
        anchor = str(raw.get("brief_anchor") or "").strip()
        if not anchor:
            continue
        start = brief.find(anchor, cursor)
        if start < 0:
            start = brief.find(anchor)
        if start < 0:
            continue
        end = start + len(anchor)
        cursor = end
        span = (start, end)
        # Call A can restate the same requirement under multiple labels. A single
        # immutable brief span must result in one coverage obligation, otherwise
        # duplicated rows create artificial evidence and citation failures.
        if span in seen_spans:
            continue
        seen_spans.add(span)
        needs.append(RfpAtomicNeed(
            id=str(raw["id"]),
            text=brief[start:end],
            category=str(raw.get("category") or "general"),
            priority=raw.get("priority", "SHOULD"),
            source_excerpt=brief[start:end],
            start_offset=start,
            end_offset=end,
        ))
    return needs


def _canonical_evidence(packets: list[EvidencePacket]) -> dict[str, Any]:
    return {evidence.id: evidence for packet in packets for evidence in packet.evidence}


def _hydrate_section_evidence(sections: list[RfpSection], packets: list[EvidencePacket]) -> list[str]:
    """Replace LLM-selected IDs by immutable evidence entries from this request, aligning text citations."""
    canonical = _canonical_evidence(packets)
    violations: list[str] = []
    for section in sections:
        candidate_ids: list[str] = []
        for evidence in section.evidence:
            canon_match = next((k for k in canonical if k.lower() == evidence.id.lower()), None)
            if not canon_match:
                violations.append(f"Section {section.key}: preuve inconnue ou non autorisée: {evidence.id}")
                continue
            if canon_match not in candidate_ids:
                candidate_ids.append(canon_match)

        visible_text = " ".join([section.body or "", *(b.text for b in section.bullets), *section.assumptions, *section.questions])
        for marker in _CITATION_PATTERN.findall(visible_text):
            canon_match = next((k for k in canonical if k.lower() == marker.lower()), None)
            if canon_match and canon_match not in candidate_ids:
                candidate_ids.append(canon_match)

        if not section.body:
            section.evidence = [canonical[cid].model_copy(deep=True) for cid in candidate_ids if cid in canonical]
            continue

        sentences = _SENTENCE_SPLIT_PATTERN.split(section.body)
        new_sentences: list[str] = []
        placed_ids: set[str] = set()
        selected_evidence: list[Any] = []

        for s in sentences:
            s_clean = s.strip()
            if not s_clean:
                continue
            existing = _CITATION_PATTERN.findall(s_clean)
            for em in existing:
                canon_match = next((k for k in canonical if k.lower() == em.lower()), None)
                if canon_match and canon_match not in placed_ids:
                    placed_ids.add(canon_match)
                    selected_evidence.append(canonical[canon_match].model_copy(deep=True))

            s_terms = _significant_terms(s_clean)
            for cid in candidate_ids:
                if cid in placed_ids:
                    continue
                quote = getattr(canonical[cid], "quote", "") or ""
                q_terms = _significant_terms(quote)
                if len(s_terms & q_terms) >= max(1, min(2, len(s_terms) // 3)):
                    s_clean = f"{s_clean.rstrip('. ')} [{cid}]."
                    placed_ids.add(cid)
                    selected_evidence.append(canonical[cid].model_copy(deep=True))
                    break

            new_sentences.append(s_clean)

        section.body = " ".join(new_sentences)
        visible_text = " ".join([section.body or "", *(b.text for b in section.bullets), *section.assumptions, *section.questions])
        final_markers = {m.lower() for m in _CITATION_PATTERN.findall(visible_text)}
        section.evidence = [
            ev for ev in selected_evidence
            if ev.id.lower() in final_markers
        ]
    return violations


def _generate_call_a(request: RfpRequest, settings: Settings, deadline: float) -> tuple[dict[str, Any], float]:
    start = time.monotonic()
    remaining = deadline - start
    # Call A may have to load the model after a cold start. Its budget is aligned
    # with the configured synchronous RFP and Ollama budgets, not a fixed cap.
    timeout = min(settings.ollama_timeout_seconds, settings.rfp_sync_timeout_seconds, max(0.0, remaining - 5.0))
    if timeout <= 0:
        raise RfpGenerationError("Insufficient budget for CALL A")

    response = ""
    try:
        response = generate_text(
            prompt=RFP_CALL_A_PROMPT.format(description=request.description),
            max_tokens=1200,
            output_schema=RFP_CALL_A_SCHEMA,
            settings=settings,
            timeout_seconds=timeout,
            request_id=request.request_id,
            stage="call_a",
        )
        payload = _parse_llm_json(response, request_id=request.request_id, stage="call_a")
        [RfpAtomicNeed.model_validate(need) for need in payload.get("atomic_needs", [])]
    except (OllamaStructuredOutputError, RfpInfrastructureError, ValueError) as exc:
        invalid_response = exc.response if isinstance(exc, OllamaStructuredOutputError) else response
        response = generate_text(
            prompt=RFP_JSON_REPAIR_PROMPT.format(invalid_response=_safe_excerpt(invalid_response, limit=4000)),
            max_tokens=1200,
            output_schema=RFP_CALL_A_SCHEMA,
            settings=settings,
            timeout_seconds=min(timeout, max(0.0, deadline - time.monotonic() - 5.0)),
            request_id=request.request_id,
            stage="call_a_json_repair",
        )
        payload = _parse_llm_json(response, request_id=request.request_id, stage="call_a_json_repair")
    duration_ms = int((time.monotonic() - start) * 1000)
    return payload, duration_ms

async def _generate_batch_async(
    request: RfpRequest,
    settings: Settings,
    deadline: float,
    sections_spec: list[dict],
    needs: list[RfpAtomicNeed],
    packets: list[EvidencePacket],
    stage_cap: float = 75.0
) -> tuple[list[RfpSection], float]:
    start = time.monotonic()
    remaining = deadline - start
    # Standard mode has two sequential batches in the 180 s synchronous budget.
    # Allocate up to 75 s to each and retain 5 s for validation/serialization.
    timeout = min(settings.ollama_timeout_seconds, stage_cap, max(0.0, remaining - 5.0))
    if timeout <= 0:
        raise RfpGenerationError("Insufficient budget for CALL B/C")

    spec_str = json.dumps(sections_spec, ensure_ascii=False, indent=2)
    brief_str = json.dumps([n.model_dump() for n in needs], ensure_ascii=False, indent=2)
    evidence_str = json.dumps([p.model_dump() for p in packets], ensure_ascii=False, indent=2)

    expected_keys = [spec["key"] for spec in sections_spec]
    prompt = RFP_STANDARD_BATCH_PROMPT.format(
        section_specs=spec_str,
        original_brief=request.description,
        brief=brief_str,
        evidence=evidence_str,
    ) + (
        "\nCONTRAT DE CLÉS IMPÉRATIF : retourne exactement une section pour chacune "
        f"des clés suivantes, sans numéro ordinal ni autre clé : {json.dumps(expected_keys)}."
    )
    # Constrain the structured decoder as well as the prompt.  Without this,
    # some local models substituted positional strings ("1", "2", …) for
    # canonical section keys, causing every generated section to be discarded.
    batch_schema = json.loads(json.dumps(RFP_STANDARD_SECTION_BATCH_SCHEMA))
    batch_schema["properties"]["sections"]["items"]["properties"]["key"] = {
        "type": "string", "enum": expected_keys
    }
    batch_schema["properties"]["sections"]["minItems"] = len(expected_keys)
    batch_schema["properties"]["sections"]["maxItems"] = len(expected_keys)

    stage = "call_b" if sections_spec[0]["key"] == STANDARD_SECTIONS_B[0]["key"] else "call_c"
    response = ""
    try:
        response = await generate_text_async(
            prompt=prompt,
            max_tokens=2400,
            output_schema=batch_schema,
            settings=settings,
            timeout_seconds=timeout,
            request_id=request.request_id,
            stage=stage,
        )
        sections = _parse_sections(response, request_id=request.request_id, stage=stage)
    except (OllamaStructuredOutputError, RfpInfrastructureError) as exc:
        # One targeted retry only: preserve the original output and ask for JSON repair.
        invalid_response = exc.response if isinstance(exc, OllamaStructuredOutputError) else response
        response = await generate_text_async(
            prompt=RFP_JSON_REPAIR_PROMPT.format(invalid_response=_safe_excerpt(invalid_response, limit=4000)),
            max_tokens=2400,
            output_schema=RFP_STANDARD_SECTION_BATCH_SCHEMA,
            settings=settings,
            timeout_seconds=min(timeout, max(0.0, deadline - time.monotonic() - 5.0)),
            request_id=request.request_id,
            stage=f"{stage}_json_repair",
        )
        sections = _parse_sections(response, request_id=request.request_id, stage=f"{stage}_json_repair")

    duration_ms = int((time.monotonic() - start) * 1000)
    return sections, duration_ms

async def _repair_batch_async(
    violating_sections: list[RfpSection],
    violations_text: str,
    needs: list[RfpAtomicNeed],
    packets: list[EvidencePacket],
    settings: Settings,
    deadline: float,
    request_id: str | None = None,
) -> tuple[list[RfpSection], float]:
    start = time.monotonic()
    remaining = deadline - start
    timeout = min(settings.ollama_timeout_seconds, max(0.0, remaining - 5.0))
    if timeout < 10.0:
        logger.warning(
            "Skipping repair stage due to low remaining budget requestId=%s remaining=%.2f",
            request_id, remaining,
        )
        return violating_sections, 0.0

    raw_proposal = json.dumps([s.model_dump() for s in violating_sections], ensure_ascii=False, indent=2)
    brief_str = json.dumps([n.model_dump() for n in needs], ensure_ascii=False, indent=2)
    evidence_str = json.dumps([p.model_dump() for p in packets], ensure_ascii=False, indent=2)

    prompt = RFP_REPAIR_PROMPT.format(
        violations=violations_text,
        brief=brief_str,
        sources=evidence_str,
        raw_proposal=raw_proposal
    )

    try:
        logger.info(
            "Starting RFP repair stage requestId=%s timeout=%.2f violating_sections=%d",
            request_id, timeout, len(violating_sections),
        )
        response = await generate_text_async(
            prompt=prompt,
            max_tokens=2400,
            output_schema=RFP_STANDARD_SECTION_BATCH_SCHEMA,
            settings=settings,
            timeout_seconds=timeout,
            request_id=request_id,
            stage="repair",
        )
        duration_ms = int((time.monotonic() - start) * 1000)
        return _parse_sections(response, request_id=request_id or "unknown", stage="repair"), duration_ms
    except Exception as exc:
        logger.warning("Repair call failed requestId=%s: %s", request_id, exc)
        return violating_sections, (time.monotonic() - start) * 1000

async def generate_standard_rfp_async(request: RfpRequest, settings: Settings, mode: str) -> RfpResponse:
    global_start = time.monotonic()
    deadline = global_start + (540.0 if mode == "full" else settings.rfp_sync_timeout_seconds)
    metrics = RfpMetrics()
    quality = RfpQualityReport()

    # CALL A
    call_a_data, metrics.call_a_ms = _generate_call_a(request, settings, deadline)
    needs_data = call_a_data.get("atomic_needs", [])
    if not needs_data:
        raise RfpInputError("Le brief ne contient aucun besoin exploitable.")

    needs = _normalize_atomic_needs(needs_data, request.description)
    if not needs:
        raise RfpInputError("Les besoins extraits ne sont pas ancrés textuellement dans le brief.")
    requirements = RfpRequirements(
        sector=call_a_data.get("sector"),
        atomic_needs=needs,
    )

    # RETRIEVAL: each requirement retains up to three PDF-only chunks.
    ret_start = time.monotonic()
    packets = retrieve_for_requirements(needs, sector=request.sector or call_a_data.get("sector"))
    metrics.retrieval_ms = int((time.monotonic() - ret_start) * 1000)

    canonical_evidence = _canonical_evidence(packets)
    allowed_evidence_ids = set(canonical_evidence)
    validation_context: dict[str, Any] = {**canonical_evidence, "__brief__": request.description}
    register = []
    for ev in canonical_evidence.values():
        if not any(entry.source_id == ev.id for entry in register):
            register.append(
                SourceRegisterEntry(
                    source_id=ev.id,
                    source_document_id=ev.source_document_id,
                    document_name=ev.document_name or f"Source {ev.source_document_id}",
                    page=ev.page,
                    chunk_id=ev.chunk_id,
                    quote=ev.quote or "",
                )
            )

    # Generation is sequential. Standard retains its fixed B then C contract;
    # Full uses the same generator in small canonical batches for its 19 sections.
    sections_spec_b = STANDARD_SECTIONS_B if mode == "standard" else (BRIEF_SECTIONS if mode == "brief" else FULL_SECTIONS)
    all_specs = sections_spec_b + (STANDARD_SECTIONS_C if mode == "standard" else [])
    if mode == "standard":
        sections_b, metrics.call_b_ms = await _generate_batch_async(request, settings, deadline, sections_spec_b, needs, packets)
        sections_c, metrics.call_c_ms = await _generate_batch_async(request, settings, deadline, STANDARD_SECTIONS_C, needs, packets)
        sections = sections_b + sections_c
    elif mode == "full":
        sections = []
        batch_ms = []
        for start in range(0, len(FULL_SECTIONS), 3):
            batch, elapsed = await _generate_batch_async(request, settings, deadline, FULL_SECTIONS[start:start + 3], needs, packets, stage_cap=75.0)
            sections.extend(batch)
            batch_ms.append(elapsed)
        metrics.call_b_ms = int(sum(batch_ms))
        metrics.call_c_ms = 0
    else:
        sections, metrics.call_b_ms = await _generate_batch_async(request, settings, deadline, sections_spec_b, needs, packets)
        metrics.call_c_ms = 0

    # VALIDATION & TRUNCATION
    val_start = time.monotonic()
    critical_violations = _hydrate_section_evidence(sections, packets)
    all_sections_by_key = {s.key: s for s in sections}

    # Enforce budgets and get warnings
    violating_keys = []

    for s_spec in all_specs:
        key = s_spec["key"]
        budget = s_spec["budget"]
        s = all_sections_by_key.get(key)
        if not s:
            critical_violations.append(f"Section manquante: {key}")
            violating_keys.append(key)
            # Create a placeholder to repair
            s = RfpSection(key=key, title=s_spec["title"], body="Section manquante.")
            all_sections_by_key[key] = s
            continue

        truncate_to_budget(s, budget)
        warnings = validate_section(s, validation_context)
        if warnings:
            critical_violations.append(f"Section {key} invalide: {', '.join(warnings)}")
            violating_keys.append(key)

    # REPAIR
    if critical_violations and (deadline - time.monotonic()) >= 25.0:
        quality.repair_attempted = True
        repair_sections = [all_sections_by_key[k] for k in violating_keys]
        repaired, repair_ms = await _repair_batch_async(
            repair_sections,
            "\n".join(critical_violations),
            needs, packets, settings, deadline,
            request_id=request.request_id,
        )
        metrics.repair_ms = int(repair_ms)
        critical_violations.extend(_hydrate_section_evidence(repaired, packets))

        for rep_s in repaired:
            if rep_s.key not in {spec["key"] for spec in all_specs}:
                quality.passed = False
                quality.warnings.append(f"Section réparée inattendue: {rep_s.key}")
                continue
            truncate_to_budget(rep_s, next(spec["budget"] for spec in all_specs if spec["key"] == rep_s.key))
            warnings = validate_section(rep_s, validation_context)
            if not warnings:
                all_sections_by_key[rep_s.key] = rep_s
                rep_s.status = "complete"
            else:
                rep_s.status = "requires_clarification"
                all_sections_by_key[rep_s.key] = rep_s
                quality.passed = False
                quality.warnings.extend(warnings)

    elif critical_violations:
        quality.passed = False
        quality.warnings.extend(critical_violations)
        for k in violating_keys:
            if k in all_sections_by_key:
                all_sections_by_key[k].status = "requires_clarification"

    # FINAL ASSEMBLY
    final_sections = [all_sections_by_key[k] for k in [s["key"] for s in all_specs] if k in all_sections_by_key]
    for order, section in enumerate(final_sections, start=1):
        section.order = order

    status = "completed" if quality.passed else "degraded"
    metrics.validation_ms = int((time.monotonic() - val_start) * 1000)

    total_words = 0
    for s in final_sections:
        if s.body:
            total_words += len(s.body.split())
        for b in s.bullets:
            total_words += len(b.text.split())

    metrics.section_count = len(final_sections)
    metrics.word_count = total_words
    metrics.total_ms = int((time.monotonic() - global_start) * 1000)

    # A completed response must meet its mode's exact structural contract.
    expected_section_count = {"brief": 4, "standard": 6, "full": 19}[mode]
    if len(final_sections) != expected_section_count:
        quality.passed = False
        quality.warnings.append(
            f"Nombre de sections invalide: {len(final_sections)} au lieu de {expected_section_count}."
        )
        status = "degraded"

    # ANNEXES
    compliance = []
    cited_evidence_ids = {
        evidence.id for section in final_sections for evidence in section.evidence
        if evidence.id in allowed_evidence_ids
    }
    for need in needs:
        section_keys = [
            section.key for section in final_sections
            if any(bullet.anchor and bullet.anchor.id == need.id for bullet in section.bullets)
        ]
        evidence_ids = [evidence.id for packet in packets if packet.requirement_id == need.id for evidence in packet.evidence]
        supporting = [evidence_id for evidence_id in evidence_ids if evidence_id in cited_evidence_ids]
        covered = bool(section_keys) and bool(supporting)
        compliance.append(ComplianceMatrixRow(
            requirement_id=need.id,
            requirement=need.text,
            covered=covered,
            section_keys=section_keys,
            supporting_evidence_ids=supporting,
            coverage_reason="Réponse ancrée dans une section et preuve PDF citée." if covered else "Aucune réponse ancrée avec preuve PDF citée.",
        ))
    # The register contains only sources actually cited by the final proposal.
    register = [entry for entry in register if entry.source_id in cited_evidence_ids]
    uncovered = [
        row for row in compliance
        if not row.covered and any(packet.evidence for packet in packets if packet.requirement_id == row.requirement_id)
    ]
    if uncovered:
        quality.passed = False
        quality.warnings.extend(
            f"Exigence sans preuve PDF citée: {row.requirement_id}" for row in uncovered
        )
        status = "degraded"
    annexes = RfpAnnexes(compliance_matrix=compliance, source_register=register)

    sources = [
        RfpSource(
            id=entry.source_id,
            type="internal_pdf",
            title=entry.document_name,
            document_id=entry.source_document_id,
            document_name=entry.document_name,
            page=entry.page,
            chunk_id=entry.chunk_id,
            excerpt=entry.quote,
        )
        for entry in register
    ]
    coverage_report = [
        RfpCoverageItem(need_id=row.requirement_id, covered=row.covered, section_keys=row.section_keys)
        for row in compliance
    ]

    proposal = RfpProposal(
        title="Proposition de Réponse",
        sections=final_sections
    )

    return RfpResponse(
        request_id=request.request_id,
        mode=mode,
        status=status,
        requirements=requirements,
        proposal=proposal,
        annexes=annexes,
        metrics=metrics,
        sources=sources,
        coverage_report=coverage_report,
        evidence_validation_passed=quality.passed and all(
            row.covered or not any(packet.evidence for packet in packets if packet.requirement_id == row.requirement_id)
            for row in compliance
        ),
        citations=[],
        quality=quality
    )

def generate_rfp_proposal(request: RfpRequest, settings: Settings) -> RfpResponse:
    """Entry point for RFP generation. Runs async internally."""
    mode = getattr(request, "mode", "standard")

    return asyncio.run(generate_standard_rfp_async(request, settings, mode))
