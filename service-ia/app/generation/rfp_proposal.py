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
    """Analyze client brief and extract requirements with deterministic fallback."""
    stripped = description.strip()
    if not stripped or len(stripped) < 3:
        raise RfpGenerationError("Le brief fourni est vide.")

    # Greeting-only or trivial inputs must be rejected
    folded = _fold_text(stripped)
    greetings = {"bonjour", "salut", "hello", "hi", "bonsoir", "coucou", "test"}
    if folded in greetings or (len(stripped.split()) <= 2 and folded.replace("!", "").replace(".", "") in greetings):
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
                excerpt=chunk.content[:240].strip() + ("..." if len(chunk.content) > 240 else ""),
                score=chunk.score,
            )
        )
        if len(sources) >= top_k:
            break

    return citations, sources


# ============================================================================
# Step 3 & 4: Multi-Pass 19-Section Writing & Planning
# ============================================================================
def _format_sources_for_prompt(sources: list[RfpSource]) -> str:
    if not sources:
        return "Aucune source PDF interne disponible pour cette demande."
    lines = []
    for s in sources:
        lines.append(f"- [{s.id}] {s.document_name} (Page {s.page}) : « {s.excerpt} »")
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


def _generate_section_cluster(
    section_specs: list[dict[str, Any]],
    requirements: RfpRequirements,
    description: str,
    sources: list[RfpSource],
    settings: Settings,
) -> list[RfpSection]:
    """Generate a cluster of sections using LLM with deterministic fallback."""
    spec_summary = "\n".join([f"- {s['key']} ({s['title']}) : {s['description']}" for s in section_specs])
    brief_formatted = _format_brief_for_prompt(requirements, description)
    sources_formatted = _format_sources_for_prompt(sources)

    prompt = RFP_SECTION_BATCH_PROMPT.format(
        section_specs=spec_summary,
        brief=brief_formatted,
        sources=sources_formatted,
    )

    try:
        raw_output = generate_text(prompt, settings, max_tokens=1500, output_schema=RFP_SECTION_BATCH_SCHEMA)
        parsed = json.loads(raw_output)
        if isinstance(parsed, dict) and "sections" in parsed and isinstance(parsed["sections"], list):
            parsed_by_key = {s.get("key"): s for s in parsed["sections"] if isinstance(s, dict) and s.get("key")}
            generated_sections: list[RfpSection] = []
            for spec in section_specs:
                key = spec["key"]
                sec_data = parsed_by_key.get(key)
                if sec_data:
                    claims = [
                        RfpClaim(
                            id=c.get("id") or f"claim-{idx:03d}",
                            text=c.get("text", ""),
                            kind=c.get("kind", "recommendation"),
                            source_ids=c.get("source_ids", []),
                            citation_indexes=[int(sid.replace("doc-", "")) for sid in c.get("source_ids", []) if sid.startswith("doc-") and sid.replace("doc-", "").isdigit()],
                        )
                        for idx, c in enumerate(sec_data.get("claims", []), start=1)
                        if isinstance(c, dict) and c.get("text")
                    ]
                    tables = [
                        RfpTable(
                            title=t.get("title", "Tableau"),
                            columns=t.get("columns", ["Élément", "Description"]),
                            rows=t.get("rows", []),
                        )
                        for t in sec_data.get("tables", [])
                        if isinstance(t, dict) and t.get("columns") and t.get("rows")
                    ]
                    narrative = sec_data.get("narrative", [])
                    bullets = sec_data.get("bullets", [])
                    questions = sec_data.get("questions", [])

                    # Populate legacy backward-compatibility fields
                    facts_from_brief = [c.text for c in claims if c.kind == "brief_fact"]
                    verified_references = [c for c in claims if c.kind == "internal_evidence"]
                    recommendations = [c.text for c in claims if c.kind == "recommendation"] or narrative
                    assumptions_to_confirm = [c.text for c in claims if c.kind in ("assumption", "question")] or questions

                    generated_sections.append(
                        RfpSection(
                            key=key,
                            order=spec["order"],
                            title=spec["title"],
                            status=sec_data.get("status", "complete"),
                            status_reason=sec_data.get("status_reason"),
                            summary=sec_data.get("summary"),
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
                    )
                else:
                    generated_sections.append(_deterministic_section(spec, requirements, sources))
            return generated_sections
    except Exception as exc:
        logger.warning("LLM section generation failed for cluster, falling back to deterministic: %s", exc)

    return [_deterministic_section(spec, requirements, sources) for spec in section_specs]


def _deterministic_section(
    spec: dict[str, Any],
    requirements: RfpRequirements,
    sources: list[RfpSource],
) -> RfpSection:
    """Compose a specific, tailored section deterministically when LLM is unavailable."""
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
                    [need.text, "Conformité et recette validée", "100% conforme"]
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
            "Exploitation et maintien en conditions opérationnelles en dehors de la période de garantie",
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
                    ["J1 — Lancement", "T0", "Validation du plan de travail"],
                    ["J2 — Fin de cadrage", "T0 + 4 semaines", "Validation du dossier d'architecture"],
                    ["J3 — Recette", "T0 + 10 semaines", "Validation des cas de tests"],
                    ["J4 — Mise en service", "T0 + 12 semaines", "Bascule en production"],
                ],
            )
        ]
    elif key == "team_and_governance":
        narrative = ["Le dispositif s'appuie sur une équipe sénior et une gouvernance resserrée."]
        tables = [
            RfpTable(
                title="Comitologie et gouvernance",
                columns=["Instance", "Fréquence", "Participants", "Rôle"],
                rows=[
                    ["Comité de Projet (COPIL)", "Mensuel", "Directeur de mission & Sponsors", "Arbitrages et suivi stratégique"],
                    ["Comité Technique (COTEC)", "Hebdomadaire", "Chef de projet & Équipe", "Suivi opérationnel et risques"],
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
        narrative = ["Le maintien en conditions opérationnelles inclut une période de garantie post-démarrage et un support niveau 3."]
    elif key == "risks_assumptions_clarifications":
        narrative = ["Les risques identifiés et les mesures de maîtrise associées sont consignés ci-dessous :"]
        tables = [
            RfpTable(
                title="Matrice des risques et parades",
                columns=["Risque identifié", "Impact possible", "Mesure préventive", "Plan de repli"],
                rows=[
                    ["Disponibilité des référents métier", "Moyen", "Planification anticipée des ateliers", "Délégation formalisée"],
                    ["Hétérogénéité des sources de données", "Élevé", "Phase de diagnostic approfondie en phase 1", "Périmètre de données prioritaire"],
                ],
            )
        ]
        questions = requirements.ambiguities_and_questions or ["Confirmer le calendrier des instances décisionnelles client."]
    elif key == "references_differentiation_next_steps":
        narrative = ["Avaliance apporte une expertise reconnue et un engagement d'excellence opérationnelle."]
        if sources:
            for s in sources:
                claims.append(
                    RfpClaim(
                        id=f"claim-ref-{len(claims)+1}",
                        text=f"Référence interne : {s.title} — {s.excerpt}",
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
# Step 5: Quality Validation & Repair
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


def validate_and_repair_proposal(
    sections: list[RfpSection],
    requirements: RfpRequirements,
    sources: list[RfpSource],
    settings: Settings,
    description: str,
) -> tuple[list[RfpSection], RfpQualityReport, list[RfpCoverageItem]]:
    """Verify 19 sections, ordering, claim citations, coverage, and repair if needed."""
    valid_source_ids = {s.id for s in sources}
    warnings: list[str] = []

    # Map sections by key or block index
    parsed_sections: list[RfpSection] = []
    for s in sections:
        # Check for banned generic placeholder responses
        if any("une réponse générique" in r.casefold() for r in (s.recommendations + s.narrative)):
            raise RfpGenerationError("La proposition générée contient du texte générique non adapté au brief.")
        parsed_sections.append(s)

    # Ensure 19 sections are present
    existing_by_key = {s.key: s for s in parsed_sections}
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
                        warnings.append(f"Section {key}: citation inconnue {invalid_ids} assainie.")
                        claim.source_ids = [sid for sid in claim.source_ids if sid in valid_source_ids]
                        if not claim.source_ids:
                            claim.kind = "recommendation"
            ordered_sections.append(found)
        else:
            ordered_sections.append(_deterministic_section(spec, requirements, sources))

    # If the generation returned custom decision blocks (e.g. block-1, block-2),
    # incorporate their tailored content into the 19 standard sections so nothing is lost!
    custom_blocks = [s for s in parsed_sections if s.key not in {spec["key"] for spec in RFP_19_SECTIONS}]
    if custom_blocks:
        custom_recs = [r for b in custom_blocks for r in (b.recommendations or b.narrative)]
        if custom_recs and ordered_sections:
            ordered_sections[0].recommendations.extend(custom_recs)
            ordered_sections[0].narrative.extend(custom_recs)

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
    citation_integrity = 1.0 if not warnings else max(0.7, 1.0 - (len(warnings) * 0.05))
    quality_score = round(0.5 * coverage_score + 0.5 * citation_integrity, 2)

    quality = RfpQualityReport(
        passed=quality_score >= 0.7,
        score=quality_score,
        coverage_score=round(coverage_score, 2),
        citation_integrity=round(citation_integrity, 2),
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
    # 1. Brief Requirements Extraction
    requirements = extract_brief_requirements(request.description, request.sector, settings)

    # 2. PDF Evidence Retrieval (Exclusively PDF)
    citations, sources = retrieve_rfp_pdf_evidence(
        query=request.description,
        sector=request.sector or requirements.sector,
        top_k=request.top_k,
        settings=settings,
    )

    # 3. Model Proposal Generation with Quality Check & Single Retry
    brief_formatted = _format_brief_for_prompt(requirements, request.description)
    sources_formatted = _format_sources_for_prompt(sources)
    prompt = RFP_SECTION_BATCH_PROMPT.format(
        section_specs="19 sections enterprise Avaliance",
        brief=brief_formatted,
        sources=sources_formatted,
    )

    raw_sections: list[RfpSection] = []
    try:
        raw_output = generate_text(prompt, settings, max_tokens=1800, output_schema=RFP_SECTION_BATCH_SCHEMA)
        candidate_sections = _parse_model_sections_output(raw_output, requirements, sources)
        is_covered, missing_needs = _check_proposal_quality(candidate_sections, requirements)
        if not is_covered:
            # Targeted single retry with CORRECTION OBLIGATOIRE
            repair_prompt = f"{prompt}\n\nCORRECTION OBLIGATOIRE : Les exigences suivantes doivent obligatoirement être couvertes : {missing_needs}"
            retry_output = generate_text(repair_prompt, settings, max_tokens=1800, output_schema=RFP_SECTION_BATCH_SCHEMA)
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
        logger.warning("Model generation failed or returned invalid output, using tailored deterministic fallback: %s", exc)
        raw_sections = [_deterministic_section(spec, requirements, sources) for spec in RFP_19_SECTIONS]

    # 4. Quality Validation & Formatting into 19 Standard Sections
    validated_sections, quality, coverage_report = validate_and_repair_proposal(
        raw_sections, requirements, sources, settings, request.description
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
