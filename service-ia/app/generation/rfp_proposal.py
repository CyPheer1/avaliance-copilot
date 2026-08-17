"""Structured, PDF-evidence-first RFP proposal composition with 19 enterprise sections."""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from typing import Any

from ..schemas import (
    ClaimKind,
    RetrievedChunk,
    RetrieveRequest,
    RfpAtomicNeed,
    RfpCitation,
    RfpClaim,
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


class RfpGenerationError(RuntimeError):
    """Raised when an RFP cannot be generated or validated."""


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


def _fold_text(value: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", value.lower())
        if not unicodedata.combining(c)
    )


# ============================================================================
# Step 1: Brief Normalization & Structured Extraction
# ============================================================================
def _deterministic_extract_requirements(description: str, sector: str | None) -> RfpRequirements:
    """Extract atomic needs and structured fields deterministically from brief text."""
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

    # Split on sentences, commas, and 'et' conjunctions
    raw_parts = [
        s.strip()
        for s in re.split(r"(?<=[.!?;])\s+|\n+|,\s*|\s+et\s+", description.strip())
        if len(s.strip()) > 3
    ]
    if not raw_parts and description.strip():
        raw_parts = [description.strip()]

    atomic_needs: list[RfpAtomicNeed] = []
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
        atomic_needs.append(RfpAtomicNeed(id=f"need-{idx:02d}", text=clean_text, category=category, source_excerpt=part))

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


def extract_brief_requirements(description: str, sector: str | None, settings: Settings) -> RfpRequirements:
    """Analyze client brief and extract requirements via LLM with deterministic fallback."""
    stripped = description.strip()
    if not stripped or len(stripped) < 3:
        raise RfpGenerationError("Le brief fourni est vide.")

    # Greeting-only or trivial inputs must be rejected
    folded = _fold_text(stripped)
    clean_folded = re.sub(r"[!?. ]+", "", folded)
    greetings = {"bonjour", "salut", "hello", "hi", "bonsoir", "coucou", "test", "bonjourtoutlemonde"}
    if clean_folded in greetings or folded in greetings:
        raise RfpGenerationError("Le brief fourni ne contient aucun besoin exploitable pour construire une proposition.")

    return _deterministic_extract_requirements(description, sector)


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

        # Relevance threshold check: require meaningful cross-encoder signal (> 0.25), strong lexical match (>= 1.0), or solid cosine similarity (>= 0.55)
        has_reranker_signal = chunk.score is not None and chunk.score > 0.25
        v_sim = chunk.vector_score if chunk.vector_score is not None else chunk.relevance_score
        has_solid_vector_sim = v_sim is not None and v_sim >= 0.55
        has_strong_text_match = chunk.text_score is not None and chunk.text_score >= 1.0

        if not (has_reranker_signal or has_solid_vector_sim or has_strong_text_match):
            continue

        # Diversify: max 3 chunks per document
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
def _plan_rfp_structure(
    requirements: RfpRequirements,
    sources: list[RfpSource],
    settings: Settings,
    description: str,
) -> dict[str, dict[str, Any]]:
    """Establish a structured 19-section plan with deterministic completeness."""
    plan_by_key: dict[str, dict[str, Any]] = {}
    for spec in RFP_19_SECTIONS:
        key = spec["key"]
        plan_by_key[key] = {
            "key": key,
            "status": "complete",
            "status_reason": None,
            "covered_need_ids": [n.id for n in requirements.atomic_needs[:2]],
            "planned_topics": [spec["title"]],
            "allowed_source_ids": [s.id for s in sources] if key == "references_differentiation_next_steps" else ["brief"],
        }
    return plan_by_key


# ============================================================================
# Step 4: Formatting & Proposal Generation
# ============================================================================
def _format_sources_for_prompt(sources: list[RfpSource]) -> str:
    if not sources:
        return "Aucune source PDF interne disponible pour cette demande."
    lines = []
    for s in sources:
        excerpt = s.excerpt[:200].strip() + ("..." if len(s.excerpt) > 200 else "")
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
                excerpt_short = s.excerpt[:150].strip() + ("..." if len(s.excerpt) > 150 else "")
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


# ============================================================================
# Step 5: Deterministic Validator & Quality Gates
# ============================================================================
_FRENCH_STOPWORDS = {
    "les", "des", "une", "par", "sur", "pour", "avec", "dans", "sont", "cette",
    "nous", "vous", "leur", "plus", "tout", "tous", "mais", "donc", "ainsi", "bien",
}


def _check_proposal_quality(
    sections: list[RfpSection],
    requirements: RfpRequirements,
) -> tuple[bool, list[str]]:
    """Verify that all atomic needs from the brief are addressed."""
    if not requirements.atomic_needs:
        return True, []

    full_raw = " ".join([
        f"{s.title} {' '.join(s.narrative)} {' '.join(c.text for c in s.claims)} {' '.join(s.recommendations)} {' '.join(s.facts_from_brief)}"
        for s in sections
    ])
    folded_full_text = _fold_text(full_raw)

    missing_needs: list[str] = []
    for need in requirements.atomic_needs:
        folded_need = _fold_text(need.text)
        terms = [t for t in re.findall(r"[a-z0-9]{3,}", folded_need) if t not in _FRENCH_STOPWORDS]
        if terms:
            match_count = sum(1 for term in terms if term in folded_full_text)
            covered = match_count >= max(1, (len(terms) + 1) // 2)
        else:
            covered = folded_need in folded_full_text

        if not covered:
            missing_needs.append(need.id)

    return len(missing_needs) == 0, missing_needs


def _validate_proposal_deterministically(
    sections: list[RfpSection],
    requirements: RfpRequirements,
    sources: list[RfpSource],
) -> list[str]:
    """Inspect proposal against all strict P0 deterministic validation rules."""
    violations: list[str] = []
    valid_source_ids = {s.id for s in sources} | {"brief"}

    # 1. Exact 19 sections present and in canonical order
    if len(sections) != 19:
        violations.append(f"Section count mismatch: expected 19 sections, got {len(sections)}")

    expected_keys = [spec["key"] for spec in RFP_19_SECTIONS]
    actual_keys = [s.key for s in sections]
    if actual_keys != expected_keys:
        violations.append(f"Section ordering mismatch: expected {expected_keys}, got {actual_keys}")

    # 2. Check each section's status and reasons
    seen_claim_ids: set[str] = set()
    for s in sections:
        if s.status == "not_applicable" and not s.status_reason:
            violations.append(f"Section {s.key} has status 'not_applicable' but lacks a required status_reason")

        # 3. Claims validation
        for c in s.claims:
            if c.id:
                if c.id in seen_claim_ids:
                    violations.append(f"Duplicate claim ID: {c.id}")
                seen_claim_ids.add(c.id)

            for sid in c.source_ids:
                if sid not in valid_source_ids:
                    violations.append(f"Section {s.key} claim '{c.id}' has unknown source ID '{sid}'")

            if c.kind == "internal_evidence":
                if not c.source_ids or not any(sid.startswith("doc-") and sid in valid_source_ids for sid in c.source_ids):
                    violations.append(f"Section {s.key} claim '{c.id}' is marked internal_evidence but has no valid internal source ID")

        # 4. Table rectangularity check
        for t in s.tables:
            if not t.columns:
                violations.append(f"Section {s.key} has a table with no columns")
            col_count = len(t.columns)
            for r_idx, row in enumerate(t.rows):
                if len(row) != col_count:
                    violations.append(f"Section {s.key} table '{t.title}' row {r_idx} length {len(row)} != columns length {col_count}")

    return violations


def validate_and_repair_proposal(
    sections: list[RfpSection],
    requirements: RfpRequirements,
    sources: list[RfpSource],
    settings: Settings,
    description: str,
) -> tuple[list[RfpSection], RfpQualityReport, list[RfpCoverageItem]]:
    """Verify 19 sections, ordering, claim citations, coverage, and format cleanly."""
    valid_source_ids = {s.id for s in sources}
    warnings: list[str] = []

    # Check for banned generic placeholder responses
    for s in sections:
        if any("une réponse générique" in r.casefold() for r in (s.recommendations + s.narrative)):
            raise RfpGenerationError("La proposition générée contient du texte générique non adapté au brief.")

    # Map sections by key
    existing_by_key = {s.key: s for s in sections}
    ordered_sections: list[RfpSection] = []

    for spec in RFP_19_SECTIONS:
        key = spec["key"]
        found = existing_by_key.get(key)
        if found:
            found.order = spec["order"]
            found.title = spec["title"]
            for claim in found.claims:
                if claim.kind == "internal_evidence":
                    invalid_ids = [sid for sid in claim.source_ids if sid not in valid_source_ids]
                    if invalid_ids:
                        warnings.append(f"Section {key}: citation inconnue {invalid_ids} corrigée.")
                        claim.source_ids = [sid for sid in claim.source_ids if sid in valid_source_ids]
                        if not claim.source_ids:
                            claim.kind = "recommendation"
            ordered_sections.append(found)
        else:
            ordered_sections.append(_deterministic_section(spec, requirements, sources))

    # If the generation returned custom decision blocks (e.g. block-1, block-2),
    # incorporate their tailored content into the 19 standard sections!
    custom_blocks = [s for s in sections if s.key not in {spec["key"] for spec in RFP_19_SECTIONS}]
    if custom_blocks:
        custom_recs = [r for b in custom_blocks for r in (b.recommendations or b.narrative)]
        if custom_recs and ordered_sections:
            ordered_sections[0].recommendations.extend(custom_recs)
            ordered_sections[0].narrative.extend(custom_recs)

    # Ensure globally unique claim IDs across all 19 sections
    global_claim_idx = 1
    for s in ordered_sections:
        for c in s.claims:
            c.id = f"claim-{global_claim_idx:03d}"
            global_claim_idx += 1
            if c.source_ids:
                c.citation_indexes = [
                    int(sid.replace("doc-", ""))
                    for sid in c.source_ids
                    if sid.startswith("doc-") and sid.replace("doc-", "").isdigit()
                ]

    # Compute coverage report
    coverage_report: list[RfpCoverageItem] = []
    full_text = " ".join([
        f"{s.title} {' '.join(s.narrative)} {' '.join(c.text for c in s.claims)} {' '.join(s.recommendations)} {' '.join(s.facts_from_brief)}"
        for s in ordered_sections
    ]).casefold()

    covered_count = 0
    for need in requirements.atomic_needs:
        n_terms = set(re.findall(r"[a-zà-ÿ]{4,}", _fold_text(need.text)))
        covered = any(term in full_text for term in n_terms) if n_terms else (need.text.casefold() in full_text)
        matching_keys = [s.key for s in ordered_sections if any(term in " ".join(s.narrative + s.recommendations).casefold() for term in n_terms)]
        coverage_report.append(RfpCoverageItem(need_id=need.id, covered=covered, section_keys=matching_keys or ["executive_summary"]))
        if covered:
            covered_count += 1

    coverage_score = covered_count / max(1, len(requirements.atomic_needs))
    has_sources = len(sources) > 0
    if not has_sources:
        warnings.append(
            "Aucune preuve PDF interne pertinente n'a été trouvée dans le corpus documentaire pour étayer ce besoin. "
            "La proposition repose exclusivement sur les faits du brief, des recommandations méthodologiques et des questions de cadrage."
        )
        citation_integrity = None
        # Rubric scoring when no internal evidence is present:
        # - Need Coverage: 40% (max 0.40)
        # - Section Completeness & Coherence: 30% (max 0.30)
        # - Internal PDF Evidence: 0% (max 0.00 since no internal PDF exists)
        # Total global score is honestly capped at 0.70 (70/100)
        quality_score = round(0.40 * coverage_score + 0.30 * (len(ordered_sections) / 19.0), 2)
    else:
        citation_integrity = 1.0 if not warnings else max(0.5, 1.0 - (len(warnings) * 0.1))
        # Rubric scoring when internal evidence is present:
        # - Need Coverage: 40% (max 0.40)
        # - Section Completeness & Coherence: 30% (max 0.30)
        # - Internal PDF Evidence & Citation Accuracy: 30% (max 0.30)
        quality_score = round(0.40 * coverage_score + 0.30 * (len(ordered_sections) / 19.0) + 0.30 * citation_integrity, 2)

    quality = RfpQualityReport(
        passed=quality_score >= 0.6 and len(ordered_sections) == 19,
        score=quality_score,
        coverage_score=round(coverage_score, 2),
        citation_integrity=round(citation_integrity, 2) if citation_integrity is not None else None,
        section_count=len(ordered_sections),
        warnings=warnings,
    )

    return ordered_sections, quality, coverage_report


# ============================================================================
# Main RFP Generation Pipeline Entry Point
# ============================================================================
def _parse_model_sections_output(
    raw_output: str,
    requirements: RfpRequirements,
    sources: list[RfpSource],
) -> list[RfpSection]:
    parsed = json.loads(raw_output)
    if not isinstance(parsed, dict) or "sections" not in parsed or not isinstance(parsed["sections"], list):
        raise ValueError("Invalid proposal JSON structure")

    sections: list[RfpSection] = []
    for idx, s in enumerate(parsed["sections"], start=1):
        if not isinstance(s, dict):
            continue
        key = s.get("key") or f"section-{idx}"
        title = s.get("title") or f"Section {idx}"
        narrative = s.get("narrative") or s.get("content") or []
        if isinstance(narrative, str):
            narrative = [narrative]

        claims = [
            RfpClaim(
                id=c.get("id") or f"claim-{c_idx:03d}",
                text=c.get("text", ""),
                kind=c.get("kind", "recommendation"),
                source_ids=c.get("source_ids", []),
            )
            for c_idx, c in enumerate(s.get("claims", []), start=1)
            if isinstance(c, dict) and c.get("text")
        ]

        recommendations = s.get("recommendations") or narrative
        facts = s.get("facts_from_brief") or [c.text for c in claims if c.kind == "brief_fact"]
        verified_refs = s.get("verified_references") or [c for c in claims if c.kind == "internal_evidence"]
        assumptions = s.get("assumptions") or s.get("assumptions_to_confirm") or []

        tables = [
            RfpTable(
                title=t.get("title", "Tableau"),
                columns=t.get("columns", ["Élément", "Description"]),
                rows=t.get("rows", []),
            )
            for t in s.get("tables", [])
            if isinstance(t, dict) and t.get("columns") and t.get("rows")
        ]

        sections.append(
            RfpSection(
                key=key,
                order=idx,
                title=title,
                status=s.get("status", "complete"),
                status_reason=s.get("status_reason"),
                summary=s.get("summary"),
                narrative=narrative,
                claims=claims,
                bullets=s.get("bullets", []),
                tables=tables,
                questions=s.get("questions", []),
                facts_from_brief=facts,
                verified_references=verified_refs,
                recommendations=recommendations,
                assumptions_to_confirm=assumptions,
            )
        )
    return sections


def generate_rfp_proposal(request: RfpRequest, settings: Settings) -> RfpResponse:
    """Execute the full PDF-only, 19-section RFP generation pipeline."""
    import time
    t_start = time.perf_counter()
    llm_calls_count = 0
    repair_count = 0
    deterministic_fallback_used = False

    # 1. Brief Requirements Extraction
    t_ext_start = time.perf_counter()
    requirements = extract_brief_requirements(request.description, request.sector, settings)
    t_ext_ms = round((time.perf_counter() - t_ext_start) * 1000, 1)

    # 2. PDF Evidence Retrieval (Exclusively PDF)
    t_ret_start = time.perf_counter()
    citations, sources = retrieve_rfp_pdf_evidence(
        query=request.description,
        sector=request.sector or requirements.sector,
        top_k=request.top_k,
        settings=settings,
    )
    t_ret_ms = round((time.perf_counter() - t_ret_start) * 1000, 1)

    # 3. Planner Stage
    t_plan_start = time.perf_counter()
    planner_output = _plan_rfp_structure(requirements, sources, settings, request.description)
    t_plan_ms = round((time.perf_counter() - t_plan_start) * 1000, 1)

    # 4. Model Proposal Generation with Quality Check & Single Retry
    brief_formatted = _format_brief_for_prompt(requirements, request.description)
    sources_formatted = _format_sources_for_prompt(sources)
    prompt = RFP_SECTION_BATCH_PROMPT.format(
        section_specs="19 sections enterprise Avaliance",
        brief=brief_formatted,
        sources=sources_formatted,
    )

    t_gen_start = time.perf_counter()
    raw_sections: list[RfpSection] = []
    try:
        raw_output = generate_text(prompt, settings, max_tokens=1800, output_schema=RFP_SECTION_BATCH_SCHEMA)
        llm_calls_count += 1
        candidate_sections = _parse_model_sections_output(raw_output, requirements, sources)
        is_covered, missing_needs = _check_proposal_quality(candidate_sections, requirements)
        if not is_covered:
            repair_prompt = f"{prompt}\n\nCORRECTION OBLIGATOIRE : Les exigences suivantes doivent obligatoirement être couvertes : {missing_needs}"
            repair_count += 1
            retry_output = generate_text(repair_prompt, settings, max_tokens=1800, output_schema=RFP_SECTION_BATCH_SCHEMA)
            llm_calls_count += 1
            retry_sections = _parse_model_sections_output(retry_output, requirements, sources)
            retry_covered, retry_missing = _check_proposal_quality(retry_sections, requirements)
            if not retry_covered:
                raise RfpGenerationError(f"Impossible de générer une proposition conforme après une nouvelle tentative. Exigences manquantes : {retry_missing}")
            raw_sections = retry_sections
        else:
            raw_sections = candidate_sections
    except RfpGenerationError:
        raise
    except Exception as exc:
        logger.info("Model generation unavailable or returned non-JSON, using tailored deterministic composition: %s", exc)
        deterministic_fallback_used = True
        raw_sections = [_deterministic_section(spec, requirements, sources) for spec in RFP_19_SECTIONS]
    t_gen_ms = round((time.perf_counter() - t_gen_start) * 1000, 1)

    # 5. Quality Validation & Formatting into 19 Standard Sections
    t_val_start = time.perf_counter()
    validated_sections, quality, coverage_report = validate_and_repair_proposal(
        raw_sections, requirements, sources, settings, request.description
    )
    t_val_ms = round((time.perf_counter() - t_val_start) * 1000, 1)
    total_duration_ms = round((time.perf_counter() - t_start) * 1000, 1)

    has_evidence = len(sources) > 0
    diagnostic = None if has_evidence else "NO_RELEVANT_PDF_EVIDENCE"

    logger.info(
        "RFP Pipeline Execution: request_id=%s, model=%s, llm_calls=%d, repairs=%d, deterministic_fallback=%s, "
        "evidence_passed=%s, diagnostic=%s, score=%.2f, timings_ms={brief_extraction: %.1f, pdf_retrieval: %.1f, "
        "planner: %.1f, generation: %.1f, validation: %.1f, total: %.1f}",
        request.request_id,
        settings.llm_model,
        llm_calls_count,
        repair_count,
        deterministic_fallback_used,
        has_evidence,
        diagnostic,
        quality.score,
        t_ext_ms,
        t_ret_ms,
        t_plan_ms,
        t_gen_ms,
        t_val_ms,
        total_duration_ms,
    )

    has_evidence = len(sources) > 0
    diagnostic = None if has_evidence else "NO_RELEVANT_PDF_EVIDENCE"

    return RfpResponse(
        request_id=request.request_id,
        requirements=requirements,
        proposal=RfpProposal(
            title=f"Proposition de réponse — {requirements.sector or 'Conseil & Systèmes d’Information'}",
            executive_summary=validated_sections[0].narrative[0] if validated_sections and validated_sections[0].narrative else None,
            sections=validated_sections,
        ),
        sources=sources,
        citations=citations,
        coverage_report=coverage_report,
        similar_missions=[],  # Synthetic missions are completely excluded from production RFP
        evidence_validation_passed=has_evidence,
        quality=quality,
        diagnostic=diagnostic,
    )


# ============================================================================
# Backward-Compatibility Helpers for Legacy Test Signatures
# ============================================================================
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
