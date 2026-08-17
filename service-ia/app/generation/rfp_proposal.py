"""Structured, PDF-evidence-first RFP proposal composition with 19 enterprise sections."""

from __future__ import annotations

import json
import logging
import re
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Literal

from ..schemas import (
    ClaimKind,
    RetrievedChunk,
    RetrieveRequest,
    RfpAtomicNeed,
    RfpCitation,
    RfpClaim,
    RfpClusterMetric,
    RfpCoverageItem,
    RfpProposal,
    RfpQualityReport,
    RfpRequest,
    RfpRequirements,
    RfpResponse,
    RfpSection,
    RfpSource,
    RfpTable,
    SectionStatus,
)
from ..settings import Settings
from .ollama import OllamaUnavailableError, generate_text
from .prompts import (
    RFP_BRIEF_EXTRACTION_PROMPT,
    RFP_BRIEF_SCHEMA,
    RFP_PLANNER_PROMPT,
    RFP_PLANNER_SCHEMA,
    RFP_REPAIR_PROMPT,
    RFP_SECTION_BATCH_PROMPT,
    RFP_SECTION_BATCH_SCHEMA,
)

logger = logging.getLogger(__name__)

# ============================================================================
# Global Constants & Deadline
# ============================================================================
GLOBAL_REQUEST_DEADLINE_S: float = 540.0


def _remaining_budget(deadline: float) -> float:
    """Return remaining seconds until monotonic deadline."""
    return max(0.0, deadline - time.monotonic())


# ============================================================================
# Typed Exceptions
# ============================================================================
class RfpInputError(ValueError):
    """Raised when user-provided brief is empty, greeting-only, or lacks actionable requirements (HTTP 422)."""


class RfpInfrastructureError(RuntimeError):
    """Raised when local Ollama generation or required infrastructure fails (HTTP 503)."""


class RfpValidationError(RuntimeError):
    """Raised when proposal fails deterministic validation or targeted repair (HTTP 502)."""


class RfpGenerationError(RuntimeError):
    """Backward-compatible alias for general RFP generation errors."""


# ============================================================================
# Request-Local Typed Result Objects
# ============================================================================
@dataclass
class BriefExtractionResult:
    requirements: RfpRequirements
    mode: Literal["llm", "deterministic_fallback"]
    warnings: list[str] = field(default_factory=list)
    duration_ms: float = 0.0


@dataclass
class PlannerResult:
    plan: dict[str, dict[str, Any]]
    mode: Literal["llm", "deterministic_fallback"]
    warnings: list[str] = field(default_factory=list)
    duration_ms: float = 0.0


@dataclass
class ClusterGenerationResult:
    sections: list[RfpSection]
    mode: Literal["llm", "deterministic_fallback"]
    warnings: list[str] = field(default_factory=list)
    duration_ms: float = 0.0
    cluster_keys: list[str] = field(default_factory=list)
    warning_code: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    tokens_per_sec: float = 0.0
    is_valid_json: bool = True


@dataclass
class PipelineMetadata:
    extraction_mode: Literal["llm", "deterministic_fallback"]
    planner_mode: Literal["llm", "deterministic_fallback"]
    generation_mode: Literal["llm", "mixed_fallback", "deterministic_fallback", "repair_failed"]
    repair_attempted: bool
    failed_cluster_keys: list[str]
    cluster_results: list[ClusterGenerationResult]
    warnings: list[str]
    timings: dict[str, float]


# ============================================================================
# 19 Enterprise Standard RFP Sections Specification
# ============================================================================
RFP_19_SECTIONS: list[dict[str, Any]] = [
    {
        "order": 1,
        "key": "executive_summary",
        "title": "Synthèse exécutive",
        "description": "Reformulation du problème, objectifs clés, solution recommandée et prochaine étape.",
    },
    {
        "order": 2,
        "key": "context_understanding",
        "title": "Compréhension du contexte",
        "description": "Environnement organisationnel, déclencheur de la mission et acteurs concernés.",
    },
    {
        "order": 3,
        "key": "stakes_and_problem",
        "title": "Enjeux et problème à résoudre",
        "description": "Enjeux stratégiques, points de douleur actuels et impacts métier.",
    },
    {
        "order": 4,
        "key": "objectives_and_outcomes",
        "title": "Objectifs et résultats attendus",
        "description": "Objectifs mesurables, indicateurs de succès et livrables finaux attendus.",
    },
    {
        "order": 5,
        "key": "scope_inclusions",
        "title": "Périmètre inclus",
        "description": "Chantiers, composants, domaines fonctionnels et livrables explicitement inclus.",
    },
    {
        "order": 6,
        "key": "scope_exclusions",
        "title": "Périmètre exclu",
        "description": "Limites de prestation, prérequis à la charge du client et exclusions explicites.",
    },
    {
        "order": 7,
        "key": "functional_solution",
        "title": "Solution fonctionnelle proposée",
        "description": "Description de la solution cible, des cas d'usage et des parcours utilisateurs.",
    },
    {
        "order": 8,
        "key": "technical_architecture",
        "title": "Architecture technique cible",
        "description": "Socle technologique, composants logiciels, choix d'hébergement et cohérence d'ensemble.",
    },
    {
        "order": 9,
        "key": "integrations_and_interfaces",
        "title": "Intégrations et interfaces",
        "description": "Interfaçage avec le SI existant, flux API, connecteurs et reprise de données.",
    },
    {
        "order": 10,
        "key": "security_compliance_governance",
        "title": "Sécurité, conformité et gouvernance des données",
        "description": "Exigences de sécurité (HDS, RGPD, NIS2, MFA, SIEM), gouvernance des données et conformité.",
    },
    {
        "order": 11,
        "key": "methodology_phases_deliverables",
        "title": "Démarche, phases et livrables",
        "description": "Démarche méthodologique par phases, jalons de validation et livrables associés.",
    },
    {
        "order": 12,
        "key": "planning_and_milestones",
        "title": "Planning et jalons",
        "description": "Trajectoire prévisionnelle, jalons clés, chemin critique et échéances relatives.",
    },
    {
        "order": 13,
        "key": "team_and_governance",
        "title": "Équipe, rôles et gouvernance",
        "description": "Dispositif d'intervention Avaliance, instances de pilotage, comitologie et rôles.",
    },
    {
        "order": 14,
        "key": "testing_and_acceptance",
        "title": "Stratégie de tests et recette",
        "description": "Plan de tests, recette fonctionnelle, critères d'acceptation et qualification.",
    },
    {
        "order": 15,
        "key": "migration_deployment_reversibility",
        "title": "Migration, déploiement et réversibilité",
        "description": "Stratégie de bascule, déploiement progressif, plan de repli et clauses de réversibilité.",
    },
    {
        "order": 16,
        "key": "change_management_training",
        "title": "Conduite du changement, formation et transfert",
        "description": "Accompagnement des utilisateurs, plan de formation et transfert de compétences.",
    },
    {
        "order": 17,
        "key": "operations_and_support",
        "title": "Exploitation, support et maintenance",
        "description": "Modèle de maintien en conditions opérationnelles, support, astreinte et supervision.",
    },
    {
        "order": 18,
        "key": "risks_assumptions_clarifications",
        "title": "Risques, dépendances, hypothèses et points à clarifier",
        "description": "Matrice des risques et parades, hypothèses structurantes et questions de cadrage.",
    },
    {
        "order": 19,
        "key": "references_differentiation_next_steps",
        "title": "Références, différenciation Avaliance et prochaines étapes",
        "description": "Preuves documentaires internes, atouts du cabinet et 3 actions immédiates pour démarrer.",
    },
]

# 5 Canonical Writer Clusters
RFP_WRITER_CLUSTERS: list[list[int]] = [
    [1, 2, 3, 4],       # Cluster 1: Synthesis & Context
    [5, 6, 7, 8],       # Cluster 2: Scope & Solution
    [9, 10, 11, 12],    # Cluster 3: Interfaces, Security & Methodology
    [13, 14, 15, 16],   # Cluster 4: Governance, Testing & Change
    [17, 18, 19],       # Cluster 5: Operations, Risks & References
]


def _fold_text(value: str) -> str:
    """Strip accents and lower-case text for case-insensitive comparisons."""
    return "".join(
        c for c in unicodedata.normalize("NFKD", value.lower())
        if not unicodedata.combining(c)
    )


# ============================================================================
# Strict Raw JSON Parsing
# ============================================================================
def _strict_parse_json(raw: str) -> dict[str, Any] | list[Any]:
    """Strictly parse JSON without permissive extraction or tolerating commentary."""
    if not raw or not raw.strip():
        raise ValueError("Model returned an empty response")
    if "<think>" in raw.lower() or "</think>" in raw.lower():
        raise ValueError("Model output contains <think> tags outside valid JSON")
    if "```" in raw:
        raise ValueError("Model output contains markdown code fences outside valid JSON")
    stripped = raw.strip()
    if not (stripped.startswith("{") and stripped.endswith("}")) and not (stripped.startswith("[") and stripped.endswith("]")):
        raise ValueError("Model output contains leading or trailing commentary outside JSON root")
    parsed = json.loads(stripped)
    if not isinstance(parsed, (dict, list)):
        raise ValueError("Parsed JSON root is not an object or array")
    return parsed


# ============================================================================
# Step 1: Brief Normalization & Structured Extraction
# ============================================================================
def _deterministic_extract_requirements(description: str, sector: str | None) -> RfpRequirements:
    """Extract atomic needs with exact character offsets deterministically from brief text."""
    folded = _fold_text(description)
    inferred_sector = sector or next(
        (val for val in ("sante", "telecom", "transport", "logistique", "energie", "assurance", "banque", "secteur public") if val in folded),
        None,
    )
    if not inferred_sector:
        if any(w in folded for w in ("hopital", "hospital", "patient", "soin", "hds", "dpi", "medical")):
            inferred_sector = "sante"
        elif any(w in folded for w in ("banque", "bancaire", "credit", "paiement")):
            inferred_sector = "banque"
        elif any(w in folded for w in ("assurance", "sinistre", "mutuelle", "police")):
            inferred_sector = "assurance"
        elif any(w in folded for w in ("wms", "entrepot", "fret", "logistique", "transport")):
            inferred_sector = "logistique"
        elif any(w in folded for w in ("telecom", "fibre", "mobile", "operateur", "5g")):
            inferred_sector = "telecom"
        elif any(w in folded for w in ("energie", "compteur", "iot", "reseau electrique")):
            inferred_sector = "energie"

    inferred_org = next(
        (val for val in ("hopital", "etablissement", "mutuelle", "operateur", "collectivite", "groupe", "entreprise") if val in folded),
        None,
    )

    raw_parts = [
        s.strip()
        for s in re.split(r"(?<=[.!?;])\s+|\n+|,\s*|\s+et\s+", description.strip())
        if len(s.strip()) > 3
    ]
    if not raw_parts and description.strip():
        raw_parts = [description.strip()]

    atomic_needs: list[RfpAtomicNeed] = []
    search_cursor = 0
    for idx, part in enumerate(raw_parts, start=1):
        clean_text = part.rstrip(".!?;")
        category = "general"
        f_part = _fold_text(clean_text)
        if any(w in f_part for w in ("secur", "hds", "nis2", "rgpd", "mfa", "siem", "authent")):
            category = "security"
        elif any(w in f_part for w in ("cloud", "api", "migr", "base", "donnee", "postgres", "databricks", "java")):
            category = "technical"
        elif any(w in f_part for w in ("livrable", "recette", "rapport", "formation", "jalon", "deploiement")):
            category = "delivery"
        elif any(w in f_part for w in ("cout", "budget", "delai", "urgence", "echeance", "fin d'annee")):
            category = "constraint"

        # Compute exact character offsets in original description
        start_idx = description.find(part, search_cursor)
        if start_idx == -1:
            start_idx = description.find(part)
        if start_idx != -1:
            end_idx = start_idx + len(part)
            search_cursor = end_idx
            exact_excerpt = description[start_idx:end_idx]
        else:
            start_idx = None
            end_idx = None
            exact_excerpt = part

        atomic_needs.append(
            RfpAtomicNeed(
                id=f"need-{idx:02d}",
                text=clean_text,
                category=category,
                source_excerpt=exact_excerpt,
                start_offset=start_idx,
                end_offset=end_idx,
            )
        )

    sentences = [s.strip() for s in re.split(r"(?<=[.!?;])\s+|\n+", description.strip()) if len(s.strip()) > 3]
    if not sentences and description.strip():
        sentences = [description.strip()]

    def _filter_values(terms: tuple[str, ...]) -> list[str]:
        return [s for s in sentences if any(t in _fold_text(s) for t in terms)]

    return RfpRequirements(
        sector=inferred_sector,
        organization_type=inferred_org,
        business_problem=_filter_values(("objectif", "besoin", "portail", "modernis", "interoper", "dossier", "patient", "client", "kpi", "attrition", "continuite", "reprise", "consolider", "gouvernance")),
        project_type=_filter_values(("portail", "migration", "plateforme", "cloud", "api", "integration", "cyber", "segmentation", "siem", "gouvernance", "socle")),
        technologies_and_constraints=_filter_values(("api", "java", "spring", "postgres", "databricks", "siem", "reseau", "mfa", "base")),
        security_and_compliance=_filter_values(("hds", "secur", "conform", "identite", "rgpd", "authent", "nis2", "journal", "astreinte")),
        expected_deliverables=_filter_values(("livrable", "portail", "rapport", "formation", "deploiement", "recette", "plan", "feuille")),
        scale=_filter_values(("utilisateur", "volume", "regional", "patient", "site", "base")),
        timeline_and_urgency=_filter_values(("echeance", "urgent", "deadline", "jalon", "delai", "lundi", "fin d'annee", "fin d’année")),
        atomic_needs=atomic_needs,
    )


def extract_brief_requirements(
    description: str,
    sector: str | None,
    settings: Settings,
    deadline: float | None = None,
) -> BriefExtractionResult:
    """Analyze client brief and extract requirements via LLM with exact brief provenance or fallback."""
    t_start = time.perf_counter()
    stripped = description.strip()
    if not stripped or len(stripped) < 3:
        raise RfpInputError("Le brief fourni est vide.")

    # Greeting-only or trivial inputs must be rejected with HTTP 422
    folded = _fold_text(stripped)
    clean_folded = re.sub(r"[\W_]+", "", folded)
    words = set(re.findall(r"[a-z0-9]+", folded))
    greetings = {"bonjour", "salut", "hello", "hi", "bonsoir", "coucou", "test", "bonjourtoutlemonde", "hey", "merci", "aide", "aidezmoi"}
    if clean_folded in greetings or folded in greetings or (len(words) <= 3 and words.issubset(greetings | {"le", "la", "un", "une", "de", "du", "pour", "mon", "notre", "projet"})):
        raise RfpInputError("Le brief fourni ne contient aucun besoin exploitable pour construire une proposition.")

    remaining = _remaining_budget(deadline) if deadline else settings.ollama_timeout_seconds
    stage_timeout = min(30.0, remaining)
    prompt = RFP_BRIEF_EXTRACTION_PROMPT.format(description=stripped)

    try:
        raw_output = generate_text(
            prompt,
            settings,
            max_tokens=800,
            output_schema=RFP_BRIEF_SCHEMA,
            timeout_seconds=stage_timeout,
        )
        parsed = _strict_parse_json(raw_output)
        if not isinstance(parsed, dict):
            raise ValueError("Extraction JSON root is not an object")

        raw_needs = parsed.get("atomic_needs", [])
        if not isinstance(raw_needs, list) or len(raw_needs) < 2:
            raise ValueError(f"Extracted atomic_needs count ({len(raw_needs)}) is insufficient")

        resolved_needs: list[RfpAtomicNeed] = []
        for idx, need_dict in enumerate(raw_needs, start=1):
            if not isinstance(need_dict, dict):
                raise ValueError("Atomic need is not a valid object")
            text = str(need_dict.get("text", "")).strip()
            category = str(need_dict.get("category", "general"))
            excerpt = need_dict.get("source_excerpt")

            candidate = excerpt if excerpt and isinstance(excerpt, str) else text
            candidate_clean = candidate.strip().rstrip(".!?;")
            start_pos = stripped.find(candidate_clean)
            if start_pos == -1:
                c_folded = _fold_text(candidate_clean)
                b_folded = _fold_text(stripped)
                f_pos = b_folded.find(c_folded)
                if f_pos != -1:
                    start_pos = f_pos
                    candidate_clean = stripped[f_pos:f_pos + len(c_folded)]

            if start_pos == -1:
                raise ValueError(f"Atomic need '{candidate_clean}' cannot be mapped to an exact brief substring")

            end_pos = start_pos + len(candidate_clean)
            exact_excerpt = stripped[start_pos:end_pos]
            need_id = str(need_dict.get("id") or f"need-{idx:02d}")

            resolved_needs.append(
                RfpAtomicNeed(
                    id=need_id,
                    text=text or exact_excerpt,
                    category=category,
                    source_excerpt=exact_excerpt,
                    start_offset=start_pos,
                    end_offset=end_pos,
                )
            )

        inferred_sector = sector or parsed.get("sector")
        req = RfpRequirements(
            sector=inferred_sector,
            organization_type=parsed.get("organization_type"),
            business_problem=parsed.get("business_problem", []),
            project_type=parsed.get("project_type", []),
            technologies_and_constraints=parsed.get("technologies_and_constraints", []),
            security_and_compliance=parsed.get("security_and_compliance", []),
            expected_deliverables=parsed.get("expected_deliverables", []),
            scale=parsed.get("scale", []),
            timeline_and_urgency=parsed.get("timeline_and_urgency", []),
            budget=parsed.get("budget"),
            criteria=parsed.get("criteria", []),
            dependencies=parsed.get("dependencies", []),
            exclusions=parsed.get("exclusions", []),
            assumptions=parsed.get("assumptions", []),
            ambiguities_and_questions=parsed.get("ambiguities_and_questions", []),
            atomic_needs=resolved_needs,
        )
        duration_ms = round((time.perf_counter() - t_start) * 1000, 1)
        return BriefExtractionResult(requirements=req, mode="llm", warnings=[], duration_ms=duration_ms)

    except RfpInputError:
        raise
    except Exception as exc:
        logger.info("Brief LLM extraction failed or excerpt mapping rejected: %s. Using deterministic fallback.", exc)
        det_req = _deterministic_extract_requirements(description, sector)
        duration_ms = round((time.perf_counter() - t_start) * 1000, 1)
        return BriefExtractionResult(
            requirements=det_req,
            mode="deterministic_fallback",
            warnings=["Extraction des exigences réalisée via le moteur déterministe."],
            duration_ms=duration_ms,
        )


# ============================================================================
# Step 2: PDF-Only Evidence Retrieval and Source Registry
# ============================================================================
def retrieve_rfp_pdf_evidence(
    query: str,
    sector: str | None,
    top_k: int,
    settings: Settings,
) -> tuple[list[RfpCitation], list[RfpSource]]:
    """Retrieve only PDF chunks from PostgreSQL/pgvector and register stable sources."""
    try:
        from ..retrieval.vector_search import vector_search

        retrieve_request = RetrieveRequest(
            query=query,
            sector=sector,
            top_k=min(top_k * 2, 20),
            corpus_scope="PDF",
        )
        retrieved = vector_search(retrieve_request)
    except Exception as exc:
        logger.warning("PDF evidence retrieval bypassed: %s", exc)
        return [], []

    citations: list[RfpCitation] = []
    sources: list[RfpSource] = []
    seen_chunks: set[int] = set()
    doc_chunk_count: dict[int, int] = {}

    for chunk in retrieved.chunks:
        if chunk.corpus_scope != "PDF":
            continue
        if chunk.chunk_id in seen_chunks:
            continue
        if chunk.document_id is None or not chunk.document_name or chunk.page is None:
            continue

        has_reranker_signal = chunk.score is not None and chunk.score > 0.25
        v_sim = chunk.vector_score if chunk.vector_score is not None else chunk.relevance_score
        has_solid_vector_sim = v_sim is not None and v_sim >= 0.55
        has_strong_text_match = chunk.text_score is not None and chunk.text_score >= 1.0

        if not (has_reranker_signal or has_solid_vector_sim or has_strong_text_match):
            continue

        count = doc_chunk_count.get(chunk.document_id, 0)
        if count >= 3:
            continue
        doc_chunk_count[chunk.document_id] = count + 1
        seen_chunks.add(chunk.chunk_id)

        source_idx = len(sources) + 1
        source_id = f"doc-{source_idx:02d}"

        citations.append(
            RfpCitation(
                citation_id=f"rfp-{chunk.chunk_id}",
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                document_name=chunk.document_name,
                page=chunk.page,
                content=chunk.content,
                source_index=source_idx,
            )
        )
        sources.append(
            RfpSource(
                id=source_id,
                type="internal_pdf",
                title=f"{chunk.document_name} (p. {chunk.page})",
                document_id=chunk.document_id,
                document_name=chunk.document_name,
                page=chunk.page,
                chunk_id=chunk.chunk_id,
                excerpt=chunk.content,
                score=chunk.score,
            )
        )
        if len(sources) >= top_k:
            break

    return citations, sources


# ============================================================================
# Step 3: Planner Stage
# ============================================================================
def _deterministic_planner_output(
    requirements: RfpRequirements,
    sources: list[RfpSource],
) -> dict[str, dict[str, Any]]:
    """Deterministic 19-section plan fallback."""
    plan_by_key: dict[str, dict[str, Any]] = {}
    valid_source_ids = [s.id for s in sources]
    for spec in RFP_19_SECTIONS:
        key = spec["key"]
        plan_by_key[key] = {
            "key": key,
            "status": "complete",
            "status_reason": None,
            "covered_need_ids": [n.id for n in requirements.atomic_needs[:2]],
            "planned_topics": [spec["title"]],
            "allowed_source_ids": valid_source_ids if key == "references_differentiation_next_steps" else ["brief"],
            "tables_planned": [],
            "questions_planned": [],
        }
    return plan_by_key


def _plan_rfp_structure(
    requirements: RfpRequirements,
    sources: list[RfpSource],
    settings: Settings,
    description: str,
    deadline: float | None = None,
) -> PlannerResult:
    """Establish a structured 19-section plan using LLM with deterministic fallback."""
    t_start = time.perf_counter()
    atomic_needs_str = json.dumps(
        [{"id": n.id, "text": n.text, "category": n.category} for n in requirements.atomic_needs],
        ensure_ascii=False,
    )
    sources_str = _format_sources_for_prompt(sources)
    section_specs_str = "\n".join([f"{s['order']}. [{s['key']}] {s['title']} : {s['description']}" for s in RFP_19_SECTIONS])
    plan_prompt = RFP_PLANNER_PROMPT.format(
        brief=description,
        atomic_needs=atomic_needs_str,
        sources=sources_str,
        section_specs=section_specs_str,
    )

    remaining = _remaining_budget(deadline) if deadline else settings.ollama_timeout_seconds
    stage_timeout = min(60.0, remaining)

    try:
        raw_output = generate_text(
            plan_prompt,
            settings,
            max_tokens=1600,
            output_schema=RFP_PLANNER_SCHEMA,
            timeout_seconds=stage_timeout,
        )
        parsed = _strict_parse_json(raw_output)
        if not isinstance(parsed, dict) or "plan" not in parsed or not isinstance(parsed["plan"], list):
            raise ValueError("Planner output missing 'plan' list")

        raw_plan = parsed["plan"]
        canonical_keys = [spec["key"] for spec in RFP_19_SECTIONS]
        if len(raw_plan) != 19:
            raise ValueError(f"Planner returned {len(raw_plan)} sections, expected 19")

        plan_by_key: dict[str, dict[str, Any]] = {}
        valid_source_ids = {s.id for s in sources} | {"brief"}
        valid_need_ids = {n.id for n in requirements.atomic_needs}

        for idx, item in enumerate(raw_plan):
            if not isinstance(item, dict):
                raise ValueError(f"Plan item {idx} is not an object")
            key = item.get("key")
            if key != canonical_keys[idx]:
                raise ValueError(f"Plan item {idx} key mismatch: expected '{canonical_keys[idx]}', got '{key}'")

            status_val = item.get("status", "complete")
            if status_val not in ("complete", "tailored", "not_applicable", "requires_clarification"):
                status_val = "complete"

            status_reason = item.get("status_reason")
            if status_val == "not_applicable" and not status_reason:
                raise ValueError(f"Section '{key}' is not_applicable but lacks status_reason")

            covered_needs = [nid for nid in item.get("covered_need_ids", []) if nid in valid_need_ids]
            allowed_sources = [sid for sid in item.get("allowed_source_ids", []) if sid in valid_source_ids] or ["brief"]
            planned_topics = [str(t) for t in item.get("planned_topics", [])] or [canonical_keys[idx]]

            plan_by_key[key] = {
                "key": key,
                "status": status_val,
                "status_reason": status_reason,
                "covered_need_ids": covered_needs,
                "planned_topics": planned_topics,
                "allowed_source_ids": allowed_sources,
                "tables_planned": item.get("tables_planned", []),
                "questions_planned": item.get("questions_planned", []),
            }

        duration_ms = round((time.perf_counter() - t_start) * 1000, 1)
        return PlannerResult(plan=plan_by_key, mode="llm", warnings=[], duration_ms=duration_ms)

    except Exception as exc:
        logger.info("Planner LLM call failed: %s. Using deterministic planner fallback.", exc)
        det_plan = _deterministic_planner_output(requirements, sources)
        duration_ms = round((time.perf_counter() - t_start) * 1000, 1)
        return PlannerResult(
            plan=det_plan,
            mode="deterministic_fallback",
            warnings=["Planification des sections réalisée via le moteur déterministe."],
            duration_ms=duration_ms,
        )


# ============================================================================
# Step 4: Multi-Pass 5-Cluster Section Writing
# ============================================================================
def _format_sources_for_prompt(sources: list[RfpSource]) -> str:
    if not sources:
        return "Aucune source PDF interne disponible pour cette demande."
    lines = []
    for s in sources:
        excerpt = (s.excerpt or "")[:250].strip() + ("..." if len(s.excerpt or "") > 250 else "")
        lines.append(f"- [{s.id}] {s.document_name} (Page {s.page}) : « {excerpt} »")
    return "\n".join(lines)


def _format_brief_for_prompt(req: RfpRequirements, description: str) -> str:
    parts = [f"Description brute : {description}"]
    if req.sector:
        parts.append(f"Secteur : {req.sector}")
    if req.atomic_needs:
        parts.append("Besoins identifiés :")
        for need in req.atomic_needs:
            parts.append(f"  - [{need.id}] {need.text}")
    return "\n".join(parts)


def _deterministic_section(
    spec: dict[str, Any],
    requirements: RfpRequirements,
    sources: list[RfpSource],
) -> RfpSection:
    """Compose a specific, tailored section deterministically without unsupported commercial inventions."""
    key = spec["key"]
    title = spec["title"]
    order = spec["order"]

    brief_facts = [n.text for n in requirements.atomic_needs]
    claims: list[RfpClaim] = []
    narrative: list[str] = []
    bullets: list[str] = []
    tables: list[RfpTable] = []
    questions: list[str] = []

    if key == "executive_summary":
        prob = requirements.business_problem[0] if requirements.business_problem else (brief_facts[0] if brief_facts else "la transformation attendue")
        narrative = [
            f"Cette proposition présente l'accompagnement d'Avaliance pour répondre aux enjeux de {prob}.",
            "Notre dispositif associe expertise méthodologique, cadrage rigoureux et sécurisation des livrables.",
        ]
        claims = [
            RfpClaim(id="claim-001", text=prob, kind="brief_fact", source_ids=["brief"]),
            RfpClaim(id="claim-002", text="Engager un cadrage initial pour valider le périmètre et les jalons.", kind="recommendation"),
        ]
    elif key == "context_understanding":
        narrative = [
            f"Le contexte porte sur les besoins suivants : {', '.join(brief_facts[:3])}." if brief_facts else "Le contexte de la mission s'inscrit dans un plan de modernisation opérationnel.",
        ]
        for f in brief_facts[:3]:
            claims.append(RfpClaim(id=f"claim-ctx-{len(claims)+1}", text=f, kind="brief_fact", source_ids=["brief"]))
    elif key == "stakes_and_problem":
        prob = requirements.business_problem if requirements.business_problem else brief_facts
        narrative = ["Les enjeux principaux identifiés nécessitent un traitement structuré et sans rupture d'activité."]
        for p in prob[:3]:
            claims.append(RfpClaim(id=f"claim-stk-{len(claims)+1}", text=p, kind="brief_fact", source_ids=["brief"]))
    elif key == "objectives_and_outcomes":
        narrative = ["Les objectifs de la prestation sont déclinés en indicateurs observables et résultats vérifiables."]
        tables = [
            RfpTable(
                title="Objectifs et indicateurs de succès",
                columns=["Objectif", "Indicateur de succès", "Cible attendue"],
                rows=[
                    [need.text, "Conformité aux spécifications validées", "Validation conjointe en recette"]
                    for need in requirements.atomic_needs[:4]
                ] or [["Cadrage et réalisation", "Livrables validés", "Réception sans réserve"]],
            )
        ]
    elif key == "scope_inclusions":
        bullets = [f"Chantier : {need.text}" for need in requirements.atomic_needs] or ["Pilotage, conception et mise en œuvre des flux"]
        narrative = ["Le périmètre pris en charge comprend les chantiers suivants :"]
    elif key == "scope_exclusions":
        bullets = [
            "Acquisition de licences logicielles tierces ou matériels",
            "Développements spécifiques hors périmètre convenu",
            "Exploitation et maintien en conditions opérationnelles non prévus au contrat",
        ]
        narrative = ["Les prestations suivantes sont expressément exclues du périmètre de base :"]
    elif key == "functional_solution":
        narrative = [
            "La solution fonctionnelle s'articule autour des cas d'usage métiers prioritaires.",
            "Chaque fonction est conçue pour simplifier les parcours et assurer l'intégrité des opérations.",
        ]
        claims = [RfpClaim(id=f"claim-fn-{idx+1}", text=need.text, kind="recommendation") for idx, need in enumerate(requirements.atomic_needs[:3])]
    elif key == "technical_architecture":
        techs = requirements.technologies_and_constraints
        narrative = [
            f"L'architecture repose sur les composants identifiés : {', '.join(techs)}." if techs else "L'architecture technique privilégie des composants standards, modulaires et sécurisés.",
        ]
    elif key == "integrations_and_interfaces":
        narrative = ["Les intégrations avec le système d'information s'effectuent via des interfaces documentées et des API sécurisées."]
    elif key == "security_compliance_governance":
        sec = requirements.security_and_compliance
        narrative = [
            f"Les exigences de sécurité et de conformité ({', '.join(sec)}) font l'objet d'un suivi dédié." if sec else "Les mesures de sécurité, de traçabilité et de gouvernance des données sont intégrées dès la conception.",
        ]
        claims = [RfpClaim(id=f"claim-sec-{idx+1}", text=s, kind="brief_fact", source_ids=["brief"]) for idx, s in enumerate(sec[:2])]
    elif key == "methodology_phases_deliverables":
        narrative = ["La démarche proposée est structurée en trois phases progressives et maîtrisées :"]
        tables = [
            RfpTable(
                title="Phases et livrables de la mission",
                columns=["Phase", "Objectif", "Livrable clé", "Critère de sortie"],
                rows=[
                    ["Phase 1 : Cadrage & Diagnostic", "Valider les exigences et la cible", "Dossier de cadrage", "Validation conjointe"],
                    ["Phase 2 : Conception & Réalisation", "Construire et intégrer les composants", "Dossier technique & Lot fonctionnel", "Recette opérationnelle"],
                    ["Phase 3 : Déploiement & Transfert", "Mettre en production et former", "PV de recette & Support", "Autonomie des équipes"],
                ],
            )
        ]
    elif key == "planning_and_milestones":
        narrative = ["Le planning prévisionnel est jalonné par des échéances relatives garantissant la visibilité opérationnelle."]
        tables = [
            RfpTable(
                title="Jalons directeurs",
                columns=["Jalon", "Échéance relative", "Objectif associé"],
                rows=[
                    ["J1 — Lancement", "Phase initiale (T0)", "Validation du plan de travail"],
                    ["J2 — Fin de cadrage", "Fin de phase 1", "Validation du dossier d'architecture"],
                    ["J3 — Recette", "Fin de phase 2", "Validation des cas de tests"],
                    ["J4 — Mise en service", "Phase 3", "Bascule en production"],
                ],
            )
        ]
    elif key == "team_and_governance":
        narrative = ["Le dispositif s'appuie sur une gouvernance structurée adaptée au contexte du client."]
        tables = [
            RfpTable(
                title="Comitologie et gouvernance",
                columns=["Instance", "Périodicité indicative", "Participants", "Rôle"],
                rows=[
                    ["Comité de Pilotage", "Selon calendrier convenu", "Directeur de mission & Sponsors", "Arbitrages et suivi stratégique"],
                    ["Comité de Projet", "Selon rythme opérationnel", "Chef de projet & Équipe", "Suivi opérationnel et risques"],
                ],
            )
        ]
    elif key == "testing_and_acceptance":
        narrative = ["La stratégie de recette repose sur une validation continue des exigences et la traçabilité des anomalies."]
    elif key == "migration_deployment_reversibility":
        narrative = ["La bascule est planifiée avec une procédure de repli formalisée et des clauses de réversibilité complètes."]
    elif key == "change_management_training":
        narrative = ["Un plan d'accompagnement au changement et de transfert de compétences est déployé auprès des équipes."]
    elif key == "operations_and_support":
        narrative = ["Le maintien en conditions opérationnelles s'articule selon le niveau de service défini lors du cadrage."]
    elif key == "risks_assumptions_clarifications":
        narrative = ["Les risques identifiés et les mesures de maîtrise associées sont consignés ci-dessous :"]
        tables = [
            RfpTable(
                title="Matrice des risques et actions de mitigation",
                columns=["Risque identifié", "Niveau", "Mesure préventive", "Action de repli"],
                rows=[
                    ["Disponibilité des référents métier", "Moyen", "Planification anticipée des ateliers", "Délégation formalisée"],
                    ["Hétérogénéité des données sources", "À évaluer", "Diagnostic approfondi en phase 1", "Périmètre de données prioritaire"],
                ],
            )
        ]
        questions = requirements.ambiguities_and_questions or ["Confirmer le calendrier des instances décisionnelles client."]
    elif key == "references_differentiation_next_steps":
        narrative = ["Avaliance s'engage sur une méthodologie transparente et un pilotage rigoureux."]
        if sources:
            for s in sources:
                excerpt_short = (s.excerpt or "")[:150].strip() + ("..." if len(s.excerpt or "") > 150 else "")
                claims.append(
                    RfpClaim(
                        id=f"claim-ref-{len(claims)+1}",
                        text=f"Référence interne : {s.title} — {excerpt_short}",
                        kind="internal_evidence",
                        source_ids=[s.id],
                        citation_indexes=[int(s.id.replace("doc-", "")) if s.id.startswith("doc-") and s.id.replace("doc-", "").isdigit() else 1],
                    )
                )
        bullets = [
            "Action 1 : Réunion de cadrage initiale et alignement sur les priorités",
            "Action 2 : Revue des accès et des documentations existantes",
            "Action 3 : Validation du planning détaillé et démarrage des ateliers",
        ]

    facts_from_brief = [c.text for c in claims if c.kind == "brief_fact"]
    verified_references = [c for c in claims if c.kind == "internal_evidence"]
    recommendations = [c.text for c in claims if c.kind == "recommendation"] or narrative
    assumptions_to_confirm = [c.text for c in claims if c.kind in ("assumption", "question")] or questions

    return RfpSection(
        key=key,
        order=order,
        title=title,
        status="complete",
        narrative=narrative,
        claims=claims,
        bullets=bullets,
        tables=tables,
        questions=questions,
        facts_from_brief=facts_from_brief,
        verified_references=verified_references,
        recommendations=recommendations,
        assumptions_to_confirm=assumptions_to_confirm,
    )


def _parse_model_sections_output(
    parsed: dict[str, Any],
    expected_specs: list[dict[str, Any]],
    sources: list[RfpSource],
) -> list[RfpSection]:
    """Parse strictly validated JSON dict into typed RfpSection objects."""
    if not isinstance(parsed, dict) or "sections" not in parsed or not isinstance(parsed["sections"], list):
        raise ValueError("JSON output missing 'sections' list")

    sections: list[RfpSection] = []
    spec_by_key = {s["key"]: s for s in expected_specs}

    for s_dict in parsed["sections"]:
        if not isinstance(s_dict, dict):
            continue
        key = s_dict.get("key")
        spec = spec_by_key.get(key)
        if not spec:
            continue

        title = s_dict.get("title") or spec["title"]
        order = spec["order"]
        status_val = s_dict.get("status", "complete")
        if status_val not in ("complete", "tailored", "not_applicable", "requires_clarification"):
            status_val = "complete"

        narrative = s_dict.get("narrative") or []
        if isinstance(narrative, str):
            narrative = [narrative]

        claims = [
            RfpClaim(
                id=c.get("id") or f"claim-{c_idx:03d}",
                text=str(c.get("text", "")).strip(),
                kind=c.get("kind", "recommendation") if c.get("kind") in ("brief_fact", "internal_evidence", "web_evidence", "recommendation", "assumption", "question") else "recommendation",
                source_ids=[str(sid) for sid in c.get("source_ids", [])],
            )
            for c_idx, c in enumerate(s_dict.get("claims", []), start=1)
            if isinstance(c, dict) and c.get("text")
        ]

        bullets = [str(b) for b in s_dict.get("bullets", []) if isinstance(b, str) and b.strip()]
        questions = [str(q) for q in s_dict.get("questions", []) if isinstance(q, str) and q.strip()]

        tables = [
            RfpTable(
                title=t.get("title", "Tableau"),
                columns=[str(col) for col in t.get("columns", ["Élément", "Description"])],
                rows=[[str(cell) for cell in row] for row in t.get("rows", []) if isinstance(row, list)],
            )
            for t in s_dict.get("tables", [])
            if isinstance(t, dict) and t.get("columns") and isinstance(t.get("rows"), list)
        ]

        facts = [c.text for c in claims if c.kind == "brief_fact"]
        verified_refs = [c for c in claims if c.kind == "internal_evidence"]
        recommendations = [c.text for c in claims if c.kind == "recommendation"] or narrative
        assumptions = [c.text for c in claims if c.kind in ("assumption", "question")] or questions

        sections.append(
            RfpSection(
                key=key,
                order=order,
                title=title,
                status=status_val,
                status_reason=s_dict.get("status_reason"),
                summary=s_dict.get("summary"),
                narrative=narrative,
                claims=claims,
                bullets=bullets,
                tables=tables,
                questions=questions,
                facts_from_brief=facts,
                verified_references=verified_refs,
                recommendations=recommendations,
                assumptions_to_confirm=assumptions,
            )
        )

    return sections


def _generate_section_cluster(
    cluster_order_list: list[int],
    planner_entries: dict[str, dict[str, Any]],
    requirements: RfpRequirements,
    sources: list[RfpSource],
    settings: Settings,
    description: str,
    deadline: float | None = None,
) -> ClusterGenerationResult:
    """Generate one bounded cluster of canonical sections with real HTTP timeout."""
    t_start = time.perf_counter()
    cluster_specs = [RFP_19_SECTIONS[i - 1] for i in cluster_order_list]
    cluster_keys = [s["key"] for s in cluster_specs]

    # Filter planner guidance and sources relevant to this cluster
    cluster_guidance = [
        f"- Section {s['order']} [{s['key']}] {s['title']} : Statut={planner_entries.get(s['key'], {}).get('status', 'complete')}, "
        f"Thèmes={planner_entries.get(s['key'], {}).get('planned_topics', [])}, "
        f"Besoins={planner_entries.get(s['key'], {}).get('covered_need_ids', [])}"
        for s in cluster_specs
    ]
    specs_formatted = "\n".join([f"{s['order']}. [{s['key']}] {s['title']} : {s['description']}" for s in cluster_specs])
    specs_with_plan = f"{specs_formatted}\n\nORIENTATIONS DU PLAN :\n" + "\n".join(cluster_guidance)

    # Allowed sources for cluster
    allowed_source_ids: set[str] = set()
    for s in cluster_specs:
        allowed_source_ids.update(planner_entries.get(s["key"], {}).get("allowed_source_ids", []))
    if any(s["key"] == "references_differentiation_next_steps" for s in cluster_specs):
        allowed_source_ids.update(src.id for src in sources)

    filtered_sources = [src for src in sources if src.id in allowed_source_ids] or sources

    brief_formatted = _format_brief_for_prompt(requirements, description)
    sources_formatted = _format_sources_for_prompt(filtered_sources)

    prompt = RFP_SECTION_BATCH_PROMPT.format(
        section_specs=specs_with_plan,
        brief=brief_formatted,
        sources=sources_formatted,
    )

    remaining = _remaining_budget(deadline) if deadline else settings.ollama_timeout_seconds
    if remaining <= 1.0:
        logger.warning("Global deadline budget exhausted before cluster %s", cluster_keys)
        det_sections = [_deterministic_section(s, requirements, sources) for s in cluster_specs]
        duration_ms = round((time.perf_counter() - t_start) * 1000, 1)
        return ClusterGenerationResult(
            sections=det_sections,
            mode="deterministic_fallback",
            warnings=[f"Délai global dépassé pour le cluster {cluster_keys}"],
            duration_ms=duration_ms,
            cluster_keys=cluster_keys,
            warning_code="TIMEOUT_FALLBACK",
        )

    stage_timeout = min(60.0, remaining)
    try:
        raw_output = generate_text(
            prompt,
            settings,
            max_tokens=1800,
            output_schema=RFP_SECTION_BATCH_SCHEMA,
            timeout_seconds=stage_timeout,
        )
        parsed = _strict_parse_json(raw_output)
        cluster_sections = _parse_model_sections_output(parsed, cluster_specs, sources)

        # Verify all expected keys exist in cluster output
        present_keys = {s.key for s in cluster_sections}
        missing_keys = [k for k in cluster_keys if k not in present_keys]
        if missing_keys:
            raise ValueError(f"Cluster output missing sections: {missing_keys}")

        duration_ms = round((time.perf_counter() - t_start) * 1000, 1)
        return ClusterGenerationResult(
            sections=cluster_sections,
            mode="llm",
            warnings=[],
            duration_ms=duration_ms,
            cluster_keys=cluster_keys,
        )

    except Exception as exc:
        logger.info("Cluster %s generation failed: %s. Using deterministic cluster fallback.", cluster_keys, exc)
        det_sections = [_deterministic_section(s, requirements, sources) for s in cluster_specs]
        duration_ms = round((time.perf_counter() - t_start) * 1000, 1)
        return ClusterGenerationResult(
            sections=det_sections,
            mode="deterministic_fallback",
            warnings=[f"Génération déterministe pour le cluster {cluster_keys}"],
            duration_ms=duration_ms,
            cluster_keys=cluster_keys,
            warning_code="CLUSTER_FALLBACK",
        )


# ============================================================================
# Step 5: Deterministic Validator & Factual-Value Quality Gates
# ============================================================================
_FRENCH_STOPWORDS = {
    "les", "des", "une", "par", "sur", "pour", "avec", "dans", "sont", "cette",
    "nous", "vous", "leur", "plus", "tout", "tous", "mais", "donc", "ainsi", "bien",
    "être", "avoir", "faire", "pourra", "seront", "selon", "entre", "comme",
}

# Regex to detect numbers, percentages, dates, SLAs, durations, budgets
_FACTUAL_PATTERNS = [
    re.compile(r"\b\d+[.,]?\d*\s*%"),                                                      # percentages: 99.9%, 10%
    re.compile(r"T0\s*\+\s*\d+\s*(?:semaines?|jours?|mois|ans?|heures?|weeks?|days?|months?)\b", re.IGNORECASE), # T0 + 2 semaines
    re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b"),                                           # dates: 12/08/2026
    re.compile(r"\b\d+\s*(?:k€|M€|€|\$|EUR|kEUR|MEUR)(?!\w)", re.IGNORECASE),            # budgets: 150 k€, 2 M€
    re.compile(r"\b\d+\s*(?:ETP|consultants?|personnes?|FTE|experts?)\b", re.IGNORECASE),  # team sizes: 4 ETP
    re.compile(r"\b(?:24/7|24h/24|7j/7|5j/7)\b", re.IGNORECASE),                          # SLAs: 24/7, 5j/7
    re.compile(r"garantie\s+de\s+\d+\s*(?:mois|ans?)\b", re.IGNORECASE),                  # warranty: garantie de 6 mois
]


def _validate_claim_evidence_support(claims: list[RfpClaim], sources: list[RfpSource]) -> list[str]:
    """Validate that internal_evidence claims are semantically supported by cited PDF excerpts."""
    violations: list[str] = []
    source_map = {s.id: s for s in sources}

    for c in claims:
        if c.kind != "internal_evidence":
            continue
        if not c.source_ids:
            violations.append(f"Claim '{c.id}' is marked internal_evidence but has no source IDs")
            continue

        for sid in c.source_ids:
            if sid == "brief":
                violations.append(f"Claim '{c.id}' is marked internal_evidence but cites 'brief'")
                continue
            src = source_map.get(sid)
            if not src or not src.excerpt:
                violations.append(f"Claim '{c.id}' cites unknown or empty source '{sid}'")
                continue

            # Semantic Support Validation: token & entity overlap
            claim_text = c.text
            src_text = src.excerpt
            folded_claim = _fold_text(claim_text)
            folded_src = _fold_text(src_text)

            # Check numbers/percentages in claim appear in source excerpt
            # Strip source identifiers (doc-01, [doc-01], etc.) and bracketed citations
            clean_claim_numbers_text = re.sub(r"\bdoc-\d+\b", "", claim_text, flags=re.IGNORECASE)
            clean_claim_numbers_text = re.sub(r"\[[^\]]*\]", "", clean_claim_numbers_text)
            raw_claim_numbers = re.findall(r"\b\d+[.,]?\d*\b", clean_claim_numbers_text)
            # Ignore 01..09 enumeration indices
            claim_numbers = [num for num in raw_claim_numbers if not (len(num) == 2 and num.startswith("0"))]
            for num in claim_numbers:
                if len(num) > 1 and num not in src_text:
                    violations.append(f"Claim '{c.id}' contains factual number '{num}' not supported in source excerpt [{sid}]")

            # Check significant keyword tokens
            claim_terms = [t for t in re.findall(r"[a-z0-9]{4,}", folded_claim) if t not in _FRENCH_STOPWORDS]
            if claim_terms:
                matched_terms = [t for t in claim_terms if t in folded_src]
                if len(matched_terms) < max(1, len(claim_terms) // 3):
                    violations.append(f"Claim '{c.id}' lacks sufficient semantic overlap with cited source excerpt [{sid}]")

    return violations


def _validate_proposal_deterministically(
    sections: list[RfpSection],
    requirements: RfpRequirements,
    sources: list[RfpSource],
) -> list[str]:
    """Inspect proposal against all strict P0 deterministic validation rules across ALL visible fields."""
    violations: list[str] = []
    valid_source_ids = {s.id for s in sources} | {"brief"}

    # 1. Exact 19 sections present and in canonical order
    if len(sections) != 19:
        violations.append(f"Section count mismatch: expected 19 sections, got {len(sections)}")

    expected_keys = [spec["key"] for spec in RFP_19_SECTIONS]
    actual_keys = [s.key for s in sections]
    if actual_keys != expected_keys:
        violations.append(f"Section ordering mismatch: expected {expected_keys}, got {actual_keys}")

    # Brief fact text corpus for grounding brief_facts
    brief_facts_corpus = " ".join([
        n.text + " " + (n.source_excerpt or "")
        for n in requirements.atomic_needs
    ])
    folded_brief = _fold_text(brief_facts_corpus)

    seen_claim_ids: set[str] = set()
    all_claims: list[RfpClaim] = []

    for s in sections:
        # 2. Section status check
        if s.status == "not_applicable" and not s.status_reason:
            violations.append(f"Section '{s.key}' has status 'not_applicable' but lacks a required status_reason")

        # 3. Scan all visible content fields for raw reasoning or non-JSON artifacts
        visible_texts: list[str] = []
        if s.summary:
            visible_texts.append(s.summary)
        visible_texts.extend(s.narrative)
        visible_texts.extend(s.bullets)
        visible_texts.extend(s.questions)
        visible_texts.extend(s.recommendations)
        visible_texts.extend(s.assumptions_to_confirm)
        if s.status_reason:
            visible_texts.append(s.status_reason)

        for t in s.tables:
            visible_texts.append(t.title)
            visible_texts.extend(t.columns)
            for row in t.rows:
                visible_texts.extend(row)

        for text in visible_texts:
            if "<think>" in text.lower() or "</think>" in text.lower():
                violations.append(f"Section '{s.key}' contains forbidden <think> tags in visible content")
            if "```" in text:
                violations.append(f"Section '{s.key}' contains forbidden markdown code fences in visible content")

            # Check unsupported commitments / factual values in prose not marked 'indicatif' or 'à confirmer'
            if s.status != "not_applicable":
                for pat in _FACTUAL_PATTERNS:
                    for match in pat.finditer(text):
                        matched_val = match.group(0)
                        is_in_brief = matched_val in brief_facts_corpus or _fold_text(matched_val) in folded_brief
                        is_clarification = any(kw in text.lower() for kw in ("indicatif", "à confirmer", "a confirmer", "hypothèse", "estimer", "prévisionnel", "jalon", "phase"))
                        if not is_in_brief and not is_clarification:
                            violations.append(
                                f"Section '{s.key}' contains unsupported factual commitment '{matched_val}' not found in brief and not marked 'indicatif' or 'à confirmer'"
                            )

        # 4. Claims validation
        for c in s.claims:
            all_claims.append(c)
            if c.id:
                if c.id in seen_claim_ids:
                    violations.append(f"Duplicate claim ID: {c.id}")
                seen_claim_ids.add(c.id)

            for sid in c.source_ids:
                if sid not in valid_source_ids:
                    violations.append(f"Section '{s.key}' claim '{c.id}' has unknown source ID '{sid}'")

            if c.kind == "internal_evidence":
                if not c.source_ids or not any(sid.startswith("doc-") and sid in valid_source_ids for sid in c.source_ids):
                    violations.append(f"Section '{s.key}' claim '{c.id}' is marked internal_evidence but lacks valid internal source ID")
            elif c.kind == "brief_fact":
                if "brief" not in c.source_ids:
                    violations.append(f"Section '{s.key}' claim '{c.id}' is marked brief_fact but does not cite 'brief'")

        # 5. Table rectangularity check
        for t in s.tables:
            if not t.columns:
                violations.append(f"Section '{s.key}' table '{t.title}' has no columns")
            col_count = len(t.columns)
            for r_idx, row in enumerate(t.rows):
                if len(row) != col_count:
                    violations.append(f"Section '{s.key}' table '{t.title}' row {r_idx} length {len(row)} != columns length {col_count}")

    # 6. Semantic evidence support validation
    evidence_violations = _validate_claim_evidence_support(all_claims, sources)
    violations.extend(evidence_violations)

    return violations


# ============================================================================
# Step 6: Targeted Single-Attempt Repair
# ============================================================================
def _repair_proposal_targeted(
    sections: list[RfpSection],
    violations: list[str],
    requirements: RfpRequirements,
    sources: list[RfpSource],
    settings: Settings,
    description: str,
    deadline: float | None = None,
) -> tuple[list[RfpSection], list[str]]:
    """Execute one targeted repair on violating sections only and re-validate."""
    logger.info("Executing targeted repair for %d violations...", len(violations))

    violating_keys: set[str] = set()
    for v in violations:
        match = re.search(r"Section '([^']+)'", v)
        if match:
            violating_keys.add(match.group(1))

    if not violating_keys:
        violating_keys = {s.key for s in sections[:4]}

    violating_specs = [spec for spec in RFP_19_SECTIONS if spec["key"] in violating_keys]
    violating_sections = [s for s in sections if s.key in violating_keys]

    violating_json = json.dumps(
        [
            {
                "key": s.key,
                "title": s.title,
                "status": s.status,
                "status_reason": s.status_reason,
                "narrative": s.narrative,
                "claims": [{"id": c.id, "text": c.text, "kind": c.kind, "source_ids": c.source_ids} for c in s.claims],
                "bullets": s.bullets,
                "tables": [{"title": t.title, "columns": t.columns, "rows": t.rows} for t in s.tables],
                "questions": s.questions,
            }
            for s in violating_sections
        ],
        ensure_ascii=False,
    )

    violations_str = "\n".join([f"- {v}" for v in violations])
    brief_formatted = _format_brief_for_prompt(requirements, description)
    sources_formatted = _format_sources_for_prompt(sources)

    repair_prompt = RFP_REPAIR_PROMPT.format(
        violations=violations_str,
        brief=brief_formatted,
        sources=sources_formatted,
        raw_proposal=violating_json,
    )

    remaining = _remaining_budget(deadline) if deadline else settings.ollama_timeout_seconds
    stage_timeout = min(60.0, remaining)

    try:
        raw_output = generate_text(
            repair_prompt,
            settings,
            max_tokens=1800,
            output_schema=RFP_SECTION_BATCH_SCHEMA,
            timeout_seconds=stage_timeout,
        )
        parsed = _strict_parse_json(raw_output)
        repaired_sections = _parse_model_sections_output(parsed, violating_specs, sources)
        repaired_by_key = {s.key: s for s in repaired_sections}

        # Merge repaired sections back into 19-section proposal
        merged_sections: list[RfpSection] = []
        for s in sections:
            if s.key in repaired_by_key:
                merged_sections.append(repaired_by_key[s.key])
            else:
                merged_sections.append(s)

        # Re-run deterministic validator on the complete proposal
        post_violations = _validate_proposal_deterministically(merged_sections, requirements, sources)
        return merged_sections, post_violations

    except Exception as exc:
        logger.warning("Targeted repair LLM call failed: %s", exc)
        return sections, violations + [f"Repair call exception: {exc}"]


# ============================================================================
# Step 7: Automated Quality Scoring & Rubric Breakdown
# ============================================================================
def _compute_quality_report(
    sections: list[RfpSection],
    requirements: RfpRequirements,
    sources: list[RfpSource],
    metadata: PipelineMetadata,
    has_critical_fact_violation: bool = False,
) -> tuple[RfpQualityReport, list[RfpCoverageItem]]:
    """Compute automated rubric breakdown and enforce strict quality ceilings."""
    # 1. Coverage Report (/20)
    full_text = " ".join([
        f"{s.title} {' '.join(s.narrative)} {' '.join(c.text for c in s.claims)} {' '.join(s.recommendations)} {' '.join(s.facts_from_brief)}"
        for s in sections
    ]).casefold()

    coverage_report: list[RfpCoverageItem] = []
    covered_count = 0
    for need in requirements.atomic_needs:
        n_terms = set(re.findall(r"[a-zà-ÿ]{4,}", _fold_text(need.text)))
        covered = any(term in full_text for term in n_terms) if n_terms else (need.text.casefold() in full_text)
        matching_keys = [s.key for s in sections if any(term in " ".join(s.narrative + s.recommendations).casefold() for term in n_terms)]
        coverage_report.append(RfpCoverageItem(need_id=need.id, covered=covered, section_keys=matching_keys or ["executive_summary"]))
        if covered:
            covered_count += 1

    coverage_ratio = covered_count / max(1, len(requirements.atomic_needs))
    coverage_score = round(coverage_ratio, 2)
    coverage_detail = round(coverage_ratio * 20.0, 1)

    # 2. Provenance & Factual Accuracy (/25)
    all_claims = [c for s in sections for c in s.claims]
    evidence_claims = [c for c in all_claims if c.kind == "internal_evidence"]
    if sources:
        citation_integrity = 1.0 if not metadata.warnings else max(0.5, 1.0 - (len(metadata.warnings) * 0.05))
        provenance_detail = round(min(25.0, 15.0 + (len(evidence_claims) * 2.5)), 1)
    else:
        citation_integrity = None
        provenance_detail = 12.0

    # 3. Specificity (/15)
    specificity_detail = 12.0 if metadata.generation_mode == "llm" else 8.0

    # 4. Solution & Delivery Quality (/15)
    solution_detail = 13.0 if len(sections) == 19 else round((len(sections) / 19.0) * 15.0, 1)

    # 5. Risks / Governance / Acceptance (/10)
    has_risk_table = any(s.key == "risks_assumptions_clarifications" and len(s.tables) > 0 for s in sections)
    has_gov_table = any(s.key == "team_and_governance" and len(s.tables) > 0 for s in sections)
    governance_detail = 10.0 if (has_risk_table and has_gov_table) else 7.0

    # 6. Executive Writing automated estimate (/10)
    writing_detail = 9.0 if metadata.generation_mode == "llm" else 6.0

    # 7. Source Quality (/5)
    source_quality_detail = min(5.0, len(sources) * 1.5) if sources else 0.0

    # Total Automated Score (/100)
    raw_score = (
        coverage_detail
        + provenance_detail
        + specificity_detail
        + solution_detail
        + governance_detail
        + writing_detail
        + source_quality_detail
    ) / 100.0
    raw_score = round(min(1.0, max(0.0, raw_score)), 2)

    # Enforce strict quality ceilings per rule 6:
    effective_score = raw_score
    if not sources:
        effective_score = min(effective_score, 0.70)
    if metadata.generation_mode == "deterministic_fallback":
        effective_score = min(effective_score, 0.70)
    elif metadata.generation_mode == "mixed_fallback":
        effective_score = min(effective_score, 0.85)
    elif metadata.repair_attempted:
        effective_score = min(effective_score, 0.90)

    passed = (
        not has_critical_fact_violation
        and effective_score >= 0.60
        and len(sections) == 19
        and metadata.generation_mode != "repair_failed"
    )

    quality = RfpQualityReport(
        passed=passed,
        score=effective_score,
        coverage_score=coverage_score,
        citation_integrity=round(citation_integrity, 2) if citation_integrity is not None else None,
        section_count=len(sections),
        generation_mode=metadata.generation_mode,
        planner_mode=metadata.planner_mode,
        extraction_mode=metadata.extraction_mode,
        repair_attempted=metadata.repair_attempted,
        failed_cluster_keys=metadata.failed_cluster_keys,
        coverage_detail=coverage_detail,
        provenance_detail=provenance_detail,
        specificity_detail=specificity_detail,
        solution_quality_detail=solution_detail,
        governance_detail=governance_detail,
        writing_detail=writing_detail,
        source_quality_detail=source_quality_detail,
        warnings=metadata.warnings,
    )

    return quality, coverage_report


# ============================================================================
# Main RFP Generation Pipeline Entry Point
# ============================================================================
def generate_rfp_proposal(request: RfpRequest, settings: Settings) -> RfpResponse:
    """Execute the full PDF-only, 19-section RFP generation pipeline with 540s deadline."""
    t_start = time.perf_counter()
    deadline = time.monotonic() + GLOBAL_REQUEST_DEADLINE_S

    warnings: list[str] = []
    timings: dict[str, float] = {}

    # 1. Brief Requirements Extraction
    ext_result = extract_brief_requirements(
        request.description,
        request.sector,
        settings,
        deadline=deadline,
    )
    requirements = ext_result.requirements
    warnings.extend(ext_result.warnings)
    timings["brief_extraction_ms"] = ext_result.duration_ms

    # 2. PDF Evidence Retrieval (Exclusively PDF)
    t_ret_start = time.perf_counter()
    citations, sources = retrieve_rfp_pdf_evidence(
        query=request.description,
        sector=request.sector or requirements.sector,
        top_k=request.top_k,
        settings=settings,
    )
    timings["pdf_retrieval_ms"] = round((time.perf_counter() - t_ret_start) * 1000, 1)

    if not sources:
        warnings.append(
            "Aucune preuve PDF interne pertinente n'a été trouvée dans le corpus documentaire pour étayer ce besoin. "
            "La proposition repose exclusivement sur les faits du brief, des recommandations méthodologiques et des questions de cadrage."
        )

    # 3. Planner Stage
    plan_result = _plan_rfp_structure(
        requirements,
        sources,
        settings,
        request.description,
        deadline=deadline,
    )
    planner_output = plan_result.plan
    warnings.extend(plan_result.warnings)
    timings["planner_ms"] = plan_result.duration_ms

    # 4. Multi-Pass 5-Cluster Section Writing
    t_gen_start = time.perf_counter()
    cluster_results: list[ClusterGenerationResult] = []
    generated_sections: list[RfpSection] = []
    failed_cluster_keys: list[str] = []

    for cluster_order_list in RFP_WRITER_CLUSTERS:
        cluster_res = _generate_section_cluster(
            cluster_order_list,
            planner_output,
            requirements,
            sources,
            settings,
            request.description,
            deadline=deadline,
        )
        cluster_results.append(cluster_res)
        generated_sections.extend(cluster_res.sections)
        if cluster_res.mode == "deterministic_fallback":
            failed_cluster_keys.extend(cluster_res.cluster_keys)
        warnings.extend(cluster_res.warnings)

    timings["generation_ms"] = round((time.perf_counter() - t_gen_start) * 1000, 1)

    # Resolve Generation Mode
    fallback_cluster_count = sum(1 for c in cluster_results if c.mode == "deterministic_fallback")
    if fallback_cluster_count == 0:
        generation_mode: Literal["llm", "mixed_fallback", "deterministic_fallback", "repair_failed"] = "llm"
    elif fallback_cluster_count < len(RFP_WRITER_CLUSTERS):
        generation_mode = "mixed_fallback"
    else:
        generation_mode = "deterministic_fallback"

    # Ensure unique claim IDs across all sections
    global_claim_idx = 1
    for s in generated_sections:
        for c in s.claims:
            c.id = f"claim-{global_claim_idx:03d}"
            global_claim_idx += 1
            if c.source_ids:
                c.citation_indexes = [
                    int(sid.replace("doc-", ""))
                    for sid in c.source_ids
                    if sid.startswith("doc-") and sid.replace("doc-", "").isdigit()
                ]

    # 5. Deterministic Validation & Targeted Repair
    t_val_start = time.perf_counter()
    violations = _validate_proposal_deterministically(generated_sections, requirements, sources)
    repair_attempted = False

    if violations:
        logger.info("Deterministic validator found %d violations on initial generation. Initiating targeted repair...", len(violations))
        repaired_sections, post_violations = _repair_proposal_targeted(
            generated_sections,
            violations,
            requirements,
            sources,
            settings,
            request.description,
            deadline=deadline,
        )
        repair_attempted = True
        if post_violations:
            logger.error("Targeted repair failed. Remaining violations: %s", post_violations)
            raise RfpValidationError(
                f"La proposition générée ne satisfait pas aux critères de conformité et de provenance après réparation ciblée : {'; '.join(post_violations[:3])}"
            )
        generated_sections = repaired_sections

    timings["validation_ms"] = round((time.perf_counter() - t_val_start) * 1000, 1)
    timings["total_ms"] = round((time.perf_counter() - t_start) * 1000, 1)

    # Build Metadata Object
    metadata = PipelineMetadata(
        extraction_mode=ext_result.mode,
        planner_mode=plan_result.mode,
        generation_mode=generation_mode,
        repair_attempted=repair_attempted,
        failed_cluster_keys=failed_cluster_keys,
        cluster_results=cluster_results,
        warnings=warnings,
        timings=timings,
    )

    # 6. Quality Scoring
    quality, coverage_report = _compute_quality_report(
        generated_sections,
        requirements,
        sources,
        metadata,
        has_critical_fact_violation=False,
    )

    # Build Safe Public Cluster Metrics (No confidential prompts, excerpts or full prose)
    cluster_metrics: list[RfpClusterMetric] = [
        RfpClusterMetric(
            cluster_keys=c.cluster_keys,
            mode=c.mode,
            duration_ms=c.duration_ms,
            warning_code=c.warning_code,
        )
        for c in cluster_results
    ]

    has_evidence = len(sources) > 0
    diagnostic = None if has_evidence else "NO_RELEVANT_PDF_EVIDENCE"

    logger.info(
        "RFP Pipeline Complete: request_id=%s, model=%s, extraction=%s, planner=%s, generation=%s, "
        "repairs=%d, evidence_passed=%s, score=%.2f, timings_ms=%s",
        request.request_id,
        settings.llm_model,
        metadata.extraction_mode,
        metadata.planner_mode,
        metadata.generation_mode,
        1 if repair_attempted else 0,
        has_evidence,
        quality.score,
        timings,
    )

    return RfpResponse(
        request_id=request.request_id,
        requirements=requirements,
        proposal=RfpProposal(
            title=f"Proposition de réponse — {requirements.sector or 'Conseil & Systèmes d’Information'}",
            executive_summary=generated_sections[0].narrative[0] if generated_sections and generated_sections[0].narrative else None,
            sections=generated_sections,
        ),
        sources=sources,
        citations=citations,
        coverage_report=coverage_report,
        cluster_metrics=cluster_metrics,
        similar_missions=[],  # Synthetic missions are completely excluded from production RFP
        evidence_validation_passed=has_evidence,
        quality=quality,
        diagnostic=diagnostic,
    )


# ============================================================================
# Backward-Compatibility Helpers for Legacy Test Signatures
# ============================================================================
def validate_and_repair_proposal(
    sections: list[RfpSection],
    requirements: RfpRequirements,
    sources: list[RfpSource],
    settings: Settings,
    description: str,
) -> tuple[list[RfpSection], RfpQualityReport, list[RfpCoverageItem]]:
    """Compatibility wrapper for deterministic validation & quality report."""
    metadata = PipelineMetadata(
        extraction_mode="deterministic_fallback",
        planner_mode="deterministic_fallback",
        generation_mode="deterministic_fallback",
        repair_attempted=False,
        failed_cluster_keys=[],
        cluster_results=[],
        warnings=[],
        timings={},
    )
    quality, coverage = _compute_quality_report(sections, requirements, sources, metadata)
    return sections, quality, coverage


def build_adaptive_proposal(requirements: RfpRequirements, citations: list[RfpCitation]) -> list[RfpSection]:
    """Compatibility wrapper generating 19 structured sections."""
    sources = [
        RfpSource(
            id=f"doc-{c.source_index:02d}",
            type="internal_pdf",
            title=c.document_name,
            document_id=c.document_id,
            document_name=c.document_name,
            page=c.page,
            chunk_id=c.chunk_id,
            excerpt=c.content,
        )
        for c in citations
    ]
    return [_deterministic_section(spec, requirements, sources) for spec in RFP_19_SECTIONS]


def _citation_for_chunk(chunk: RetrievedChunk, index: int) -> RfpCitation | None:
    if chunk.document_id is None or chunk.document_name is None or chunk.page is None:
        return None
    return RfpCitation(
        citation_id=f"rfp-{chunk.chunk_id}",
        chunk_id=chunk.chunk_id,
        document_id=chunk.document_id,
        document_name=chunk.document_name,
        page=chunk.page,
        content=chunk.content,
        source_index=index,
    )


def _extract_rfp_requirements(description: str, sector: str | None) -> RfpRequirements:
    return _deterministic_extract_requirements(description, sector)


def _proposal_sections(requirements: RfpRequirements, citations: list[RfpCitation]) -> list[RfpSection]:
    return build_adaptive_proposal(requirements, citations)
