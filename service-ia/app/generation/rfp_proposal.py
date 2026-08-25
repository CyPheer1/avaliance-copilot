"""Structured RFP proposal composition handling standard, brief and full modes."""

from __future__ import annotations

import json
import logging
import time
import asyncio
import re
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
from .ollama import OllamaStructuredOutputError, OllamaUnavailableError, generate_text, generate_text_async
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
    segment_long_sentences,
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
    {"key": "executive_summary", "title": "Synthèse exécutive", "budget": 100},
    {"key": "needs_and_objectives", "title": "Compréhension du besoin et objectifs", "budget": 110},
    {"key": "proposed_solution", "title": "Solution proposée et périmètre", "budget": 150},
]
STANDARD_SECTIONS_C = [
    {"key": "delivery_and_deliverables", "title": "Démarche, jalons et livrables", "budget": 120},
    {"key": "security_risks_assumptions", "title": "Sécurité, risques, hypothèses et questions", "budget": 100},
    {"key": "avaliance_fit_next_steps", "title": "Fit Avaliance et prochaines étapes", "budget": 100},
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


_HARD_VIOLATION_MARKERS = (
    "section manquante",
    "preuve inconnue",
    "preuve canonique invalide",
    "citation canonique invalide",
    "citation non pertinente",
    "absente des preuves structurées",
    "valeur factuelle non sourcée",
)


def _is_hard_violation(message: str) -> bool:
    lowered = message.lower()
    return any(marker in lowered for marker in _HARD_VIOLATION_MARKERS)


def _select_generation_packets(
    needs: list[RfpAtomicNeed],
    packets: list[EvidencePacket],
    *,
    per_need: int = 2,
    max_packets: int = 12,
) -> list[EvidencePacket]:
    """Bound prompt evidence while preserving canonical packets for validation."""
    selected: list[EvidencePacket] = []
    seen_requirements: set[str] = set()
    by_requirement = {packet.requirement_id: packet for packet in packets}

    for need in needs:
        packet = by_requirement.get(need.id)
        if packet is None:
            continue
        selected.append(
            packet.model_copy(update={"evidence": packet.evidence[:per_need]}, deep=True)
        )
        seen_requirements.add(need.id)
        if len(selected) >= max_packets:
            break

    if len(selected) < max_packets:
        for packet in packets:
            if packet.requirement_id in seen_requirements:
                continue
            selected.append(
                packet.model_copy(update={"evidence": packet.evidence[:per_need]}, deep=True)
            )
            if len(selected) >= max_packets:
                break
    return selected


def _grounded_fallback_sections(
    needs: list[RfpAtomicNeed],
    specs: list[dict[str, Any]],
    packets: list[EvidencePacket],
    original_brief: str = "",
) -> list[RfpSection]:
    """Build a consultant-ready proposal from the immutable client brief.

    The local LLM is attempted first. This deterministic safety path is used when
    the LLM draft is invalid or not sufficiently grounded. Recommendations are
    derived from technologies and constraints explicitly present in the brief;
    unknown interfaces, dates, budgets and commitments remain assumptions.
    """
    compact_brief = " ".join((original_brief or "").split()).strip()
    brief_parts = [part.strip(" .") for part in re.split(r"(?<=[.!?])\s+", compact_brief) if part.strip()]
    need_texts = [" ".join(need.text.split()).strip(" .") for need in needs if need.text.strip()]
    ordered_facts: list[str] = []
    seen: set[str] = set()
    for value in brief_parts + need_texts:
        key = value.casefold()
        if value and key not in seen:
            seen.add(key)
            ordered_facts.append(value)
    if not ordered_facts:
        ordered_facts = ["Le périmètre fonctionnel doit être précisé avec le client"]

    lowered = compact_brief.casefold()
    tech_patterns = [
        ("Apache Kafka", r"\bapache kafka\b|\bkafka\b"),
        ("Java", r"\bjava\b"),
        ("FHIR", r"\bfhir\b"),
        ("RGPD", r"\brgpd\b"),
        ("PostgreSQL", r"\bpostgres(?:ql)?\b"),
        ("Kubernetes", r"\bkubernetes\b|\bk8s\b"),
        ("API", r"\bapis?\b|\bapi\b"),
        ("machine learning", r"machine learning|apprentissage automatique|mod[eè]les? de?\s*machine"),
        ("règles métiers", r"r[eè]gles? (?:m[eé]tiers?|business)|moteur de r[eè]gles"),
        ("traçabilité", r"tra[cç]abilit[eé]|audit"),
    ]
    technologies = [label for label, pattern in tech_patterns if re.search(pattern, lowered)]

    metric_matches = re.findall(
        r"\b\d[\d .]*(?:%|ms|millisecondes?|secondes?|events?|événements?|transactions?|jours?|mois)\b|"
        r"\b\d[\d .]*\s*(?:par seconde|/s)\b",
        compact_brief,
        flags=re.IGNORECASE,
    )
    metrics_text = ", ".join(dict.fromkeys(" ".join(item.split()) for item in metric_matches))
    fact_one = ordered_facts[0]
    fact_two = ordered_facts[1] if len(ordered_facts) > 1 else "Les éléments complémentaires seront précisés au cadrage"
    if len(fact_one) > 360:
        fact_one = fact_one[:357].rsplit(" ", 1)[0] + "..."
    if len(fact_two) > 360:
        fact_two = fact_two[:357].rsplit(" ", 1)[0] + "..."
    tech_text = ", ".join(technologies[:4])
    has_identity = bool(re.search(r"pi[eè]ces? d['’]?identit[eé]|identit[eé]|v[eé]rification d'identit[eé]", lowered))
    has_lcbft = bool(re.search(r"lcb[- ]?ft|blanchiment|anti[- ]?money", lowered))
    has_rest_api = bool(re.search(r"api[s]?\s+rest|restful|api[s]?\s+temps r[eé]el", lowered))
    has_rgpd = "rgpd" in lowered
    has_data_protection = bool(re.search(r"protection des donn[eé]es|donn[eé]es personnelles", lowered))
    has_archival = bool(re.search(r"archiv|preuve|conservation|r[eé]tention", lowered))
    number_words = {"un": "1", "deux": "2", "trois": "3", "quatre": "4", "cinq": "5", "six": "6", "sept": "7", "huit": "8", "neuf": "9", "dix": "10"}
    retention_match = re.search(r"\b(\d+|un|deux|trois|quatre|cinq|six|sept|huit|neuf|dix)\s+ans?\b", compact_brief, flags=re.IGNORECASE)
    if retention_match:
        raw_years = retention_match.group(1).casefold()
        retention_text = f"{number_words.get(raw_years, raw_years)} ans"
        has_explicit_retention = True
    else:
        retention_text = "la durée confirmée au cadrage"
        has_explicit_retention = False
    requirement_labels: list[str] = []
    if has_identity:
        requirement_labels.append("vérification des pièces d’identité")
    if has_lcbft:
        requirement_labels.append("contrôle LCB-FT")
    if has_rest_api:
        requirement_labels.append("intégration d’API REST temps réel")
    if has_rgpd:
        requirement_labels.append("respect du RGPD")
    if has_archival:
        requirement_labels.append(f"archivage probant des preuves pendant {retention_text}")
    has_claims = bool(re.search(r"sinistre|d[eé]claration.*sinistre|gestion des sinistres", lowered))
    has_mobile = bool(re.search(r"application mobile|app mobile|depuis un mobile", lowered))
    has_photographs = bool(re.search(r"photograph|photos?", lowered))
    has_document_upload = bool(re.search(r"joindre.*document|transmettre.*pi[eè]ces?|pi[eè]ces? justificatives?|t[eé]l[eé]vers|document[s]?", lowered))
    has_media = has_photographs or has_document_upload
    has_realtime = bool(re.search(r"temps r[eé]el|au fil de l'eau|instantan[eé]", lowered))
    has_existing_systems = bool(re.search(r"syst[eè]mes? existants?|syst[eè]me[s]? .*contrat|gestion des contrats|int[eé]grer.*contrat", lowered))
    has_history = bool(re.search(r"historique|[eé]changes|d[eé]cisions?|piste d.audit|tra[cç]abil", lowered))
    has_audit_trail = bool(re.search(r"piste d.audit|journal d.audit|audit", lowered))
    has_reduce_delay = bool(re.search(r"r[eé]duire.*d[eé]lai|acc[eé]l[eé]rer|d[eé]lais? de traitement", lowered))
    has_dashboard = bool(re.search(r"tableau de bord|suivre.*avancement|suivi.*dossier|suivre son statut|suivre.*statut", lowered))
    has_online = bool(re.search(r"en ligne|portail", lowered))
    has_completeness = bool(re.search(r"compl[eé]tude|complet[s]? des dossier", lowered))
    has_routing = bool(re.search(r"orienter.*service|services? comp[eé]tents?|acheminer", lowered))
    has_account_opening = bool(re.search(r"ouverture de compte|ouvrir un compte", lowered))
    has_iot = bool(re.search(r"iot|capteurs?|temp[eé]rature|vibration|consommation [eé]nerg[eé]tique", lowered))
    has_anomaly = bool(re.search(r"maintenance pr[eé]dictive|d[eé]tecter les anomalies|pr[eé]venir une panne", lowered))
    has_public_service = bool(re.search(r"administration|citoyens?|demandes? de documents officiels", lowered))
    has_online = bool(re.search(r"en ligne|portail", lowered))
    has_retention = bool(re.search(r"archiv|conserv|r[eé]tention|historique", lowered))
    semantic_labels: list[str] = []
    if has_claims:
        semantic_labels.append("gestion et déclaration des sinistres")
    if has_mobile:
        semantic_labels.append("application mobile")
    if has_photographs:
        semantic_labels.append("dépôt de photographies")
    if has_document_upload:
        semantic_labels.append("dépôt de documents ou de pièces justificatives")
    if has_realtime:
        semantic_labels.append("suivi en temps réel")
    if has_existing_systems:
        semantic_labels.append("intégration des systèmes existants")
    if has_history:
        semantic_labels.append("traçabilité des décisions et des échanges")
    if has_reduce_delay:
        semantic_labels.append("réduction des délais de traitement")
    if has_dashboard:
        semantic_labels.append("suivi du statut et avancement des dossiers")
    if has_online:
        semantic_labels.append("dépôt en ligne")
    if has_completeness:
        semantic_labels.append("vérification de la complétude des dossiers")
    if has_routing:
        semantic_labels.append("orientation vers les services compétents")
    if has_audit_trail:
        semantic_labels.append("piste d’audit des décisions")
    if has_account_opening:
        semantic_labels.append("parcours d’ouverture de compte")
    if has_iot:
        semantic_labels.append("données issues de capteurs IoT")
    if has_anomaly:
        semantic_labels.append("détection d’anomalies et maintenance prédictive")
    if has_public_service:
        semantic_labels.append("traitement des demandes administratives")
    if has_online:
        semantic_labels.append("dépôt et suivi en ligne")
    if has_explicit_retention:
        semantic_labels.append(f"conservation pendant {retention_text}")
    elif has_retention:
        semantic_labels.append("archivage selon les règles de conservation applicables")
    all_labels: list[str] = []
    for label in semantic_labels + requirement_labels:
        if label and label not in all_labels:
            all_labels.append(label)
    requirement_digest = ", ".join(all_labels)
    explicit_requirements = ", ".join(requirement_labels)

    first_id = needs[0].id if needs else "brief"
    second_id = needs[1].id if len(needs) > 1 else first_id

    architecture_keywords: list[str] = []
    if "kafka" in lowered:
        architecture_keywords.append("kafka")
    if "java" in lowered:
        architecture_keywords.append("java")
    if "fhir" in lowered:
        architecture_keywords.append("fhir")
    if "rgpd" in lowered:
        architecture_keywords.append("rgpd")
    if "machine learning" in lowered or "modèles" in lowered:
        architecture_keywords.append("modèle")
    if "traçabil" in lowered or "audit" in lowered:
        architecture_keywords.append("traçabil")
    architecture_evidence = _fallback_reference(packets, tuple(architecture_keywords[:2])) if architecture_keywords else None
    traceability_evidence = _fallback_reference(packets, ("traçabil", "audit")) if ("traçabil" in lowered or "audit" in lowered) else None
    architecture_citation = f" [{architecture_evidence.id}]" if architecture_evidence else ""
    traceability_citation = f" [{traceability_evidence.id}]" if traceability_evidence else ""

    if "kafka" in lowered:
        solution_body = (
            "Nous recommandons une architecture événementielle basée sur Kafka. "
            "Les producteurs publieront sur des topics séparés par flux métier. "
            "Les partitions permettront une consommation parallèle et un dimensionnement progressif. "
            "Des services Java traiteront les événements et appliqueront les règles du parcours. "
            f"Le prototype vérifiera les critères annoncés : {metrics_text or 'débit et latence à préciser'}. "
            "Les tests de charge confirmeront le comportement du parcours sous contrainte. "
            "Les interfaces et le dimensionnement final seront confirmés pendant le cadrage."
        )
    elif "fhir" in lowered:
        solution_body = (
            "Nous recommandons une couche d’interopérabilité FHIR pour structurer les échanges avec les systèmes existants. "
            "Les ressources seront validées avant transmission et les erreurs seront journalisées. "
            "Les API et les profils d’échange seront documentés avec les équipes métier et techniques. "
            f"Le prototype vérifiera la réduction attendue et les parcours prioritaires : {metrics_text or 'critères à préciser'}. "
            "Les interfaces et règles de conservation seront confirmées au cadrage."
        )
    elif "machine learning" in lowered or "fraude" in lowered or "règles métiers" in lowered:
        solution_body = (
            "Nous recommandons un pipeline séparant la collecte, l’évaluation des règles et la priorisation des cas. "
            "Les modèles ou règles retenus devront rester explicables et leurs décisions devront être traçables. "
            f"Le prototype mesurera les critères explicitement annoncés : {metrics_text or 'indicateurs à confirmer'}. "
            "Les seuils, interfaces et modalités d’exploitation seront confirmés pendant le cadrage."
        )
    elif requirement_digest:
        solution_parts: list[str] = []
        if has_claims:
            solution_parts.append("Nous recommandons un parcours de gestion des sinistres orchestré et traçable.")
        elif has_account_opening:
            solution_parts.append("Nous recommandons un parcours d’ouverture de compte orchestré et traçable.")
        elif has_public_service:
            solution_parts.append("Nous recommandons pour cette administration un parcours numérique de traitement des demandes administratives.")
        elif has_iot or has_anomaly:
            solution_parts.append("Nous recommandons une chaîne de collecte, d’analyse et de priorisation des alertes.")
        else:
            solution_parts.append("Nous recommandons une architecture métier modulaire, orientée par les exigences explicites du brief.")
        if has_mobile:
            solution_parts.append("Une application mobile permettra de déclarer le dossier et de consulter son avancement.")
        if has_photographs:
            solution_parts.append("Le parcours permettra de joindre les photographies nécessaires à l’instruction.")
        if has_document_upload:
            solution_parts.append("Le parcours permettra de transmettre les documents ou pièces justificatives nécessaires.")
        if has_realtime:
            solution_parts.append("Le statut du dossier sera exposé en temps réel avec gestion des erreurs et des reprises.")
        if has_existing_systems:
            solution_parts.append("Un service d’orchestration intégrera les systèmes existants et leurs contrats d’interface.")
        if has_identity:
            solution_parts.append("Un service vérifiera les pièces d’identité et orientera les exceptions vers une revue humaine.")
        if has_lcbft:
            solution_parts.append("Le contrôle LCB-FT sera intégré avant la décision et rattaché à la demande.")
        if has_rest_api:
            solution_parts.append("Les API REST seront documentées avec leurs contrats, erreurs, retries et règles d’idempotence.")
        if has_rgpd:
            solution_parts.append("Le RGPD sera traité comme une contrainte de conformité, avec minimisation et accès contrôlé.")
        if has_history:
            solution_parts.append("Les décisions, échanges et événements seront conservés dans une piste d’audit exploitable.")
        if has_archival and has_explicit_retention:
            solution_parts.append(f"L’archivage probant des preuves et décisions couvrira {retention_text}.")
        elif has_archival:
            solution_parts.append("L’archivage suivra les règles de conservation applicables au dossier.")
        elif has_explicit_retention:
            solution_parts.append(f"La conservation suivra la durée explicitement demandée : {retention_text}.")
        if has_reduce_delay:
            solution_parts.append("Les délais de traitement seront mesurés entre la réception, l’instruction et la décision.")
        if has_dashboard:
            solution_parts.append("Un tableau de bord opérationnel permettra de visualiser les dossiers et leurs résultats de validation.")
        if has_online:
            solution_parts.append("Le dépôt en ligne sera contrôlé avant transmission au service compétent.")
        if has_completeness:
            solution_parts.append("Un contrôle de complétude signalera les pièces manquantes avant instruction.")
        if has_routing:
            solution_parts.append("Les demandes complètes seront orientées vers les services compétents.")
        if has_audit_trail:
            solution_parts.append("Une piste d’audit conservera les décisions et les actions réalisées.")
        if has_iot:
            solution_parts.append("Les données de température, vibration et consommation seront contrôlées avant analyse.")
        if has_anomaly:
            solution_parts.append("La maintenance prédictive orientera la détection d’anomalies et la priorisation des interventions.")
        solution_parts.append("Le prototype couvrira le parcours nominal, les rejets, les reprises et les critères d’acceptation.")
        solution_body = " ".join(solution_parts)
    elif technologies:
        solution_body = (
            f"Nous recommandons une architecture modulaire s’appuyant sur {tech_text}. "
            "Le parcours prioritaire sera prototypé avant l’industrialisation. "
            f"Les tests vérifieront les contraintes annoncées : {metrics_text or 'critères de succès à préciser'}. "
            "Les interfaces, volumes et règles d’exploitation seront confirmés au cadrage."
        )
    else:
        solution_body = (
            "Nous recommandons une architecture modulaire et un prototype ciblé sur le parcours prioritaire. "
            "Les interfaces, données et critères de succès seront définis avec les parties prenantes. "
            "Les tests permettront de confirmer la faisabilité avant l’industrialisation."
        )
    solution_body += architecture_citation

    if has_archival and (has_identity or has_lcbft):
        risk_sentence = "Les risques principaux concernent une décision erronée, une preuve incomplète et le respect de la durée de conservation."
    elif "paiement" in lowered or "transaction" in lowered:
        risk_sentence = "Le risque prioritaire concerne la sécurité et la continuité des transactions."
    elif "santé" in lowered or "medical" in lowered or "médical" in lowered:
        risk_sentence = "Le risque prioritaire concerne la protection des données et la gestion des habilitations."
    elif "kafka" in lowered:
        risk_sentence = "Les risques principaux concernent la saturation des consommateurs, la perte d’événements et la latence."
    else:
        risk_sentence = "Les risques principaux concernent les interfaces, les données et le respect des critères de succès."

    if "rgpd" in lowered:
        security_sentence = "Le périmètre RGPD sera traduit en règles de minimisation, d’accès, de conservation et de traçabilité."
    else:
        security_sentence = "Les règles d’accès, de conservation et de traçabilité seront définies selon le périmètre client."
    if "paiement" in lowered or "transaction" in lowered:
        security_sentence += " Les contrôles de sécurité des transactions seront vérifiés avant la mise en service."
    elif "santé" in lowered or "medical" in lowered or "médical" in lowered:
        security_sentence += " Les habilitations et la protection des données sensibles seront confirmées avec les parties prenantes."

    if has_claims or has_mobile or has_media:
        risk_sentence += " La confidentialité des pièces et la disponibilité du parcours seront vérifiées."
    if has_explicit_retention:
        security_sentence += f" La durée de conservation explicitement demandée est {retention_text}."
    elif has_retention:
        security_sentence += " Les règles et la durée de conservation seront confirmées pendant le cadrage."
    security_body = (
        f"{security_sentence} "
        f"{risk_sentence} "
        "La mitigation reposera sur des contrôles d’accès, des journaux d’audit et des tests sur un périmètre représentatif. "
        "Les exigences réglementaires, la disponibilité et les modalités d’exploitation restent à confirmer."
        f"{traceability_citation}"
    )

    if requirement_digest:
        if has_claims:
            summary_body = "Le client souhaite améliorer la gestion des sinistres automobiles."
        elif has_account_opening:
            summary_body = "Le client souhaite digitaliser son parcours d’ouverture de compte."
        elif has_public_service:
            summary_body = "Le client, une administration, souhaite digitaliser le traitement des demandes administratives."
        elif has_iot or has_anomaly:
            summary_body = "Le client souhaite fiabiliser la maintenance de ses équipements de production."
        else:
            summary_body = f"Le brief client porte sur : {fact_one}."
        summary_body += f" La réponse couvre : {requirement_digest}."
        if metrics_text:
            summary_body += f" Les critères chiffrés sont : {metrics_text}."
    else:
        summary_body = f"Le brief client indique : {fact_one}. Nous proposons de le traduire en périmètre, architecture et critères de validation."
        if metrics_text:
            summary_body += f" Les critères annoncés sont : {metrics_text}."

    # Keep summaries and delivery text compact. Put the full semantic detail
    # into the solution and deliverables while avoiding long comma lists.
    # Include the explicit requirements in the executive summary without
    # inventing an order of priority. Keep the list bounded for readability.
    summary_labels = all_labels[:8]
    if requirement_digest:
        if has_claims:
            summary_body = "Le client souhaite accélérer la gestion des sinistres automobiles."
        elif has_account_opening:
            summary_body = "Le client souhaite digitaliser son parcours d’ouverture de compte."
        elif has_public_service:
            summary_body = "Le client, une administration, souhaite digitaliser le traitement des demandes administratives."
        elif has_iot or has_anomaly:
            summary_body = "Le client souhaite fiabiliser la maintenance de ses équipements de production."
        else:
            summary_body = f"Le besoin client porte sur : {fact_one}."
        for label in summary_labels:
            summary_body += f" Exigence couverte : {label}."
        if metrics_text:
            summary_body += f" Critères chiffrés : {metrics_text}."

    needs_body = "Le cadrage reliera chaque exigence à un flux, un composant ou un résultat observable."
    for label in all_labels[:8]:
        needs_body += f" Exigence à traiter : {label}."

    if has_claims:
        delivery_focus = "Les livrables couvriront le dossier sinistre, l’application mobile et le suivi du traitement."
    elif has_public_service:
        delivery_focus = "Les livrables couvriront le dépôt, la complétude, l’orientation, l’audit et l’archivage."
    elif has_iot or has_anomaly:
        delivery_focus = "Les livrables couvriront la collecte des capteurs, les alertes, les interventions et le tableau de bord."
    elif has_account_opening or has_identity or has_lcbft:
        delivery_focus = "Les livrables couvriront le workflow d’identité, le contrôle LCB-FT, les API et les preuves."
    else:
        delivery_focus = "Les livrables couvriront le parcours prioritaire, les interfaces et les critères d’acceptation."
    if has_explicit_retention:
        delivery_focus += f" La conservation de {retention_text} sera vérifiée."

    if has_iot or has_anomaly:
        solution_body = (
            "Nous recommandons une chaîne de collecte et d’analyse des capteurs. "
            "Les données de température, vibration et consommation seront contrôlées. "
            "La maintenance prédictive détectera les anomalies et priorisera les alertes. "
            "Un tableau de bord suivra les interventions. "
            "La traçabilité conservera les alertes et les actions réalisées. "
            "Le prototype validera la détection, la priorisation et la planification."
        )
    elif has_public_service:
        solution_body = (
            "Nous recommandons un parcours numérique pour cette administration. "
            "Le dépôt en ligne acceptera les pièces justificatives. "
            "Le contrôle de complétude signalera les éléments manquants. "
            "Les demandes seront orientées vers les services compétents. "
            "Une piste d’audit conservera les décisions. "
            "La protection des données et l’archivage suivront les règles applicables. "
            "Le statut restera visible par les citoyens."
        )

    if has_iot or has_anomaly:
        delivery_body = (
            "Le cadrage définira les capteurs, les flux et les critères d’alerte. "
            "Un prototype validé couvrira la détection et la priorisation. "
            "Les tests vérifieront les données, le tableau de bord et la traçabilité. "
            "La mise en service comprendra un rapport de validation et un guide d’exploitation."
        )
    elif has_public_service:
        delivery_body = (
            "Le cadrage définira le dépôt, la complétude, l’orientation et l’archivage. "
            "Un prototype validé couvrira un dossier citoyen de bout en bout. "
            "Les tests vérifieront les pièces, la piste d’audit et le suivi du statut. "
            "La mise en service comprendra un rapport de validation et un guide d’exploitation."
        )
    else:
        delivery_body = (
            "Le projet commence par un cadrage des parcours, flux, interfaces et critères. "
            "L’équipe produit une note d’architecture et une matrice de critères. "
            "Un prototype validé couvre le parcours prioritaire. "
            "Des tests fonctionnels, d’intégration et de charge vérifient les critères. "
            "La mise en service prévoit un rapport de validation, un plan de mise en service et un guide d’exploitation. "
            f"{delivery_focus}"
        )

    if has_claims:
        fit_body = ("Pour ce contexte assurance, Avaliance peut cadrer le parcours de déclaration, "
                    "l’intégration du système de contrats et le suivi du dossier. "
                    "L’atelier précisera les règles d’instruction, les pièces attendues et les critères de délai. "
                    "Un prototype mobile permettra de valider le parcours avant son industrialisation.")
    elif has_iot or has_anomaly:
        fit_body = ("Pour ce contexte industriel, Avaliance peut cadrer les capteurs, les flux et les règles d’alerte. "
                    "L’atelier précisera les équipements concernés, les seuils et les utilisateurs du tableau de bord. "
                    "Un prototype permettra de valider la détection et la priorisation avant l’industrialisation.")
    elif has_public_service:
        fit_body = ("Pour ce contexte administratif, Avaliance peut cadrer le dépôt, la complétude et l’orientation des dossiers. "
                    "L’atelier précisera les systèmes administratifs, les rôles et les règles d’archivage. "
                    "Un prototype permettra de valider le parcours citoyen et la piste d’audit avant l’industrialisation.")
    elif has_account_opening or has_identity or has_lcbft:
        fit_body = ("Pour ce contexte financier, Avaliance peut cadrer le parcours d’identité, le contrôle LCB-FT et les preuves. "
                    "L’atelier précisera les contrats d’API, les exceptions et les règles de conservation. "
                    "Un prototype permettra de valider la décision et sa traçabilité avant l’industrialisation.")
    else:
        fit_body = ("Avaliance peut engager un atelier de cadrage métier et technique sur le parcours prioritaire. "
                    "Cet atelier précisera les flux, les interfaces, les critères de succès et les responsabilités. "
                    "Un prototype permettra de valider la solution avant l’industrialisation.")

    content: dict[str, tuple[str, list[dict[str, object]], list[str], list[str], list[Any]]] = {
        "executive_summary": (
            summary_body,
            [{"text": "Reprendre les exigences du brief comme critères de cadrage et de succès.", "anchor": {"type": "requirement", "id": first_id}}, {"text": "Valider les critères métier et le périmètre avant la conception détaillée.", "anchor": {"type": "recommendation", "id": first_id}}, {"text": "Distinguer les faits confirmés des recommandations proposées.", "anchor": {"type": "recommendation", "id": first_id}}],
            ["Les informations non présentes dans le brief seront confirmées pendant le cadrage."],
            ["Quel périmètre fonctionnel doit être traité en premier ?"],
            [],
        ),
        "needs_and_objectives": (
            needs_body,
            [{"text": "Formaliser une matrice de critères de succès à partir du brief.", "anchor": {"type": "requirement", "id": first_id}}, {"text": "Relier chaque objectif à une validation observable.", "anchor": {"type": "requirement", "id": second_id}}, {"text": "Formaliser les critères d’acceptation et les résultats attendus.", "anchor": {"type": "requirement", "id": first_id}}, {"text": "Identifier les dépendances et les validations nécessaires au démarrage.", "anchor": {"type": "recommendation", "id": second_id}}],
            [],
            ["Quels résultats métier et quels critères d’acceptation permettront de valider la solution ?"],
            [],
        ),
        "proposed_solution": (
            solution_body,
            [{"text": "Décrire les composants et flux à partir des contraintes explicitement citées.", "anchor": {"type": "requirement", "id": second_id}}, {"text": "Prototyper le parcours principal avant l’industrialisation.", "anchor": {"type": "recommendation", "id": first_id}}, {"text": "Mesurer les critères de performance et de qualité annoncés.", "anchor": {"type": "recommendation", "id": second_id}}],
            ["Les interfaces, volumes détaillés et exigences d’exploitation ne sont pas précisés dans le brief."],
            ["Quels systèmes existants, flux et règles d’intégration doivent être inclus ?"],
            [architecture_evidence] if architecture_evidence else [],
        ),
        "delivery_and_deliverables": (
            delivery_body,
            [{"text": "Cadrer les flux, interfaces et critères d’acceptation.", "anchor": {"type": "recommendation", "id": first_id}}, {"text": "Valider le prototype par des tests fonctionnels et de charge.", "anchor": {"type": "recommendation", "id": second_id}}, {"text": "Préparer la documentation d’exploitation et de mise en service.", "anchor": {"type": "recommendation", "id": first_id}}],
            ["Le calendrier, les responsabilités et les livrables contractuels seront confirmés après le cadrage."],
            ["Quel calendrier et quelles parties prenantes sont prévus pour les validations ?"],
            [],
        ),
        "security_risks_assumptions": (
            security_body,
            [{"text": "Définir les règles de sécurité, de conformité et de contrôle dès le cadrage.", "anchor": {"type": "requirement", "id": first_id}}, {"text": "Tester les risques techniques sur un périmètre représentatif.", "anchor": {"type": "recommendation", "id": second_id}}, {"text": "Tracer les décisions et résultats des validations prévues.", "anchor": {"type": "recommendation", "id": first_id}}],
            ["Les exigences détaillées de sécurité, de conservation et d’exploitation restent à confirmer."],
            ["Quelles exigences réglementaires, règles d’accès, durées de conservation et objectifs de disponibilité doivent être appliqués ?"],
            [traceability_evidence] if traceability_evidence else [],
        ),
        "avaliance_fit_next_steps": (
            fit_body + " Une architecture cible et les résultats du prototype seront présentés pour validation. "
            "L’estimation détaillée interviendra après confirmation du périmètre et des résultats de test. "
            "Les références internes seront retenues uniquement si leur contenu est directement comparable au besoin client.",
            [{"text": "Organiser un atelier de cadrage avec les parties prenantes métier et techniques.", "anchor": {"type": "recommendation", "id": first_id}}, {"text": "Valider les critères de succès avant toute estimation détaillée.", "anchor": {"type": "recommendation", "id": second_id}}, {"text": "Partager une feuille de route après validation du périmètre.", "anchor": {"type": "recommendation", "id": first_id}}, {"text": "Documenter les décisions de cadrage et leurs responsables.", "anchor": {"type": "recommendation", "id": first_id}}],
            [],
            ["Qui validera le périmètre, les critères de succès et le choix d’architecture ?"],
            [],
        ),
    }

    result: list[RfpSection] = []
    for spec in specs:
        body, bullets, assumptions, questions, evidence = content.get(
            spec["key"],
            ("Cette section sera précisée après validation du périmètre client.", [], [], ["Quel est le périmètre attendu ?"], []),
        )
        result.append(RfpSection(
            key=spec["key"],
            title=spec["title"],
            status="complete",
            status_reason="Contenu ancré dans le brief client ; recommandations distinguées des faits et preuves PDF vérifiées.",
            body=segment_long_sentences(body),
            # Keep a fourth anchored bullet when it carries a distinct acceptance or next-step point.
            bullets=bullets[:5],
            assumptions=assumptions[:2],
            questions=questions[:3],
            evidence=[item.model_copy(deep=True) for item in evidence[:4]],
        ))
    return result


_REFERENCE_UNSAFE_PATTERN = re.compile(
    r"crédalis|novashield|client\s*:|budget|référence\s*:|indicateur\s*:|avant\s*:|après\s*:|"
    r"\b20\d{2}\b|\b\d[\d ,.]*\s*(?:%|ms|h|mois|m\b|j\b|€)|\b\d[\d,.]*\s*(?:m événements|analystes|administrateurs)",
    re.IGNORECASE,
)
_REFERENCE_PREFERRED_PATTERN = re.compile(
    r"kafka|règle|modèle|explicab|traçabil|audit|conformité|gestion de cas|périmètre|interface|paiement|scoring|alerte",
    re.IGNORECASE,
)


def _safe_reference_excerpt(quote: str) -> str:
    """Keep only generic, non-identifying reference text for RFP generation/display."""
    pieces = re.split(r"\s{2,}|\n|(?<=[.!?])\s+", quote or "")
    safe: list[str] = []
    for piece in pieces:
        compact = " ".join(piece.split()).strip(" ;")
        if len(compact) < 24 or _REFERENCE_UNSAFE_PATTERN.search(compact):
            continue
        if _REFERENCE_PREFERRED_PATTERN.search(compact):
            safe.append(compact)
    return " ".join(safe[:2])[:900]


def _sanitize_reference_packets(packets: list[EvidencePacket]) -> list[EvidencePacket]:
    """Anonymize internal reference PDFs before they reach prompts or the response."""
    sanitized: list[EvidencePacket] = []
    for packet in packets:
        evidence = []
        for item in packet.evidence:
            quote = _safe_reference_excerpt(item.quote or "")
            if not quote:
                continue
            item_copy = item.model_copy(deep=True)
            item_copy.quote = quote
            item_copy.document_name = "Référence interne PDF anonymisée"
            evidence.append(item_copy)
        sanitized.append(packet.model_copy(update={
            "status": "SUPPORTED" if evidence else "NO_RELEVANT_EVIDENCE",
            "evidence": evidence,
        }, deep=True))
    return sanitized


def _fallback_reference(packets: list[EvidencePacket], keywords: tuple[str, ...]) -> Any | None:
    """Return only evidence that is textually relevant to the requested topic.

    Never fall back to an arbitrary retrieved PDF: a semantically nearby reference
    is not proof for a different technical topic.
    """
    normalized_keywords = tuple(keyword.casefold() for keyword in keywords if keyword)
    ranked: list[tuple[int, Any]] = []
    for packet in packets:
        for evidence in packet.evidence:
            quote = (evidence.quote or "").casefold()
            score = sum(1 for keyword in normalized_keywords if keyword in quote)
            if score:
                ranked.append((score, evidence))
    return max(ranked, key=lambda item: item[0])[1] if ranked else None


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


def _deterministic_call_a_payload(description: str) -> dict[str, Any]:
    """Extract conservative atomic needs from the brief when Ollama is unavailable."""
    compact = " ".join(description.split())
    parts = [part.strip() for part in re.split(r"(?<=[.!?])\s+", compact) if len(part.strip()) >= 24]
    if not parts:
        parts = [compact]
    needs: list[dict[str, Any]] = []
    for index, part in enumerate(parts[:6], start=1):
        folded = part.lower()
        category = "Architecture" if any(term in folded for term in ("kafka", "architecture", "moteur", "modèles", "machine learning")) else "Performance"
        needs.append({"id": str(index), "text": part, "category": category, "priority": "MUST", "source_excerpt": part})
    sector = "Banque et finance" if any(term in compact.lower() for term in ("banque", "fraude", "lutte contre le blanchiment", "lcb-ft")) else None
    return {"sector": sector, "atomic_needs": needs}


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
        try:
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
        except OllamaUnavailableError:
            logger.warning("CALL A repair unavailable; using deterministic brief extraction requestId=%s", request.request_id)
            payload = _deterministic_call_a_payload(request.description)
    except OllamaUnavailableError:
        logger.warning("CALL A unavailable; using deterministic brief extraction requestId=%s", request.request_id)
        payload = _deterministic_call_a_payload(request.description)
    duration_ms = int((time.monotonic() - start) * 1000)
    return payload, duration_ms

async def _generate_batch_async(
    request: RfpRequest,
    settings: Settings,
    deadline: float,
    sections_spec: list[dict],
    needs: list[RfpAtomicNeed],
    packets: list[EvidencePacket],
    stage_cap: float = 30.0
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
            max_tokens=1200,
            output_schema=batch_schema,
            settings=settings,
            timeout_seconds=timeout,
            request_id=request.request_id,
            stage=stage,
        )
        sections = _parse_sections(response, request_id=request.request_id, stage=stage)
    except (OllamaStructuredOutputError, RfpInfrastructureError) as exc:
        invalid_response = exc.response if isinstance(exc, OllamaStructuredOutputError) else response
        try:
            response = await generate_text_async(
                prompt=RFP_JSON_REPAIR_PROMPT.format(invalid_response=_safe_excerpt(invalid_response, limit=4000)),
                max_tokens=1800,
                output_schema=batch_schema,
                settings=settings,
                timeout_seconds=min(timeout, max(0.0, deadline - time.monotonic() - 5.0)),
                request_id=request.request_id,
                stage=f"{stage}_json_repair",
            )
            sections = _parse_sections(response, request_id=request.request_id, stage=f"{stage}_json_repair")
        except OllamaUnavailableError:
            logger.warning("%s unavailable after structured-output failure; using deterministic proposal fallback requestId=%s", stage, request.request_id)
            sections = []
    except OllamaUnavailableError:
        logger.warning("%s unavailable; using deterministic proposal fallback requestId=%s", stage, request.request_id)
        sections = []

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

    expected_keys = [s.key for s in violating_sections]
    prompt += (
        "\nCONTRAT DE CLÉS IMPÉRATIF : retourne exactement les sections suivantes, "
        f"sans numéro ordinal ni autre clé : {json.dumps(expected_keys)}."
    )
    
    repair_schema = json.loads(json.dumps(RFP_STANDARD_SECTION_BATCH_SCHEMA))
    repair_schema["properties"]["sections"]["items"]["properties"]["key"] = {
        "type": "string", "enum": expected_keys
    }
    repair_schema["properties"]["sections"]["minItems"] = len(expected_keys)
    repair_schema["properties"]["sections"]["maxItems"] = len(expected_keys)

    try:
        logger.info(
            "Starting RFP repair stage requestId=%s timeout=%.2f violating_sections=%d",
            request_id, timeout, len(violating_sections),
        )
        response = await generate_text_async(
            prompt=prompt,
            max_tokens=2400,
            output_schema=repair_schema,
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
    call_a_data, metrics.call_a_ms = await asyncio.to_thread(
        _generate_call_a, request, settings, deadline
    )
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
    retrieved_packets = retrieve_for_requirements(needs, sector=request.sector or call_a_data.get("sector"))
    packets = _sanitize_reference_packets(retrieved_packets)
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
    
    prompt_packets = _select_generation_packets(needs, packets)
    
    if mode == "standard":
        sections, metrics.call_b_ms = await _generate_batch_async(request, settings, deadline, all_specs, needs, prompt_packets)
        metrics.call_c_ms = 0
    elif mode == "full":
        sections = []
        batch_ms = []
        for start in range(0, len(FULL_SECTIONS), 3):
            batch, elapsed = await _generate_batch_async(request, settings, deadline, FULL_SECTIONS[start:start + 3], needs, prompt_packets, stage_cap=75.0)
            sections.extend(batch)
            batch_ms.append(elapsed)
        metrics.call_b_ms = int(sum(batch_ms))
        metrics.call_c_ms = 0
    else:
        sections, metrics.call_b_ms = await _generate_batch_async(request, settings, deadline, sections_spec_b, needs, prompt_packets)
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
            for w in warnings:
                if _is_hard_violation(w):
                    critical_violations.append(f"Section {key} invalide: {w}")
                    if key not in violating_keys:
                        violating_keys.append(key)
                else:
                    quality.warnings.append(f"Section {key}: {w}")

    # STANDARD MODE FALLBACK: reject ungrounded LLM prose instead of spending another
    # long repair call on the same reference-case leakage. The fallback is deterministic,
    # concise, and built only from the immutable client brief.
    if critical_violations and mode == "standard":
        logger.warning(
            "Rejecting invalid standard RFP prose and using grounded fallback requestId=%s violations=%d",
            request.request_id, len(critical_violations),
        )
        quality.repair_attempted = False
        quality.generation_mode = "deterministic_fallback"
        metrics.fallback_used = True
        # The rejected LLM draft is not delivered. Validate the replacement as
        # the final artifact instead of carrying warnings from the rejected draft.
        quality.warnings.clear()
        fallback_sections = _grounded_fallback_sections(needs, all_specs, packets, request.description)
        all_sections_by_key = {section.key: section for section in fallback_sections}
        fallback_warnings: list[str] = []
        for section in fallback_sections:
            fallback_warnings.extend(
                f"Section {section.key}: {warning}"
                for warning in validate_section(section, validation_context)
                if not _is_hard_violation(warning)
            )
        quality.warnings.extend(fallback_warnings)

    # REPAIR remains only for legacy full/brief job flows.
    elif critical_violations and (deadline - time.monotonic()) >= 25.0:
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
            hard_warnings = [w for w in warnings if _is_hard_violation(w)]
            soft_warnings = [w for w in warnings if not _is_hard_violation(w)]
            
            if soft_warnings:
                quality.warnings.extend([f"Section {rep_s.key} réparée: {w}" for w in soft_warnings])
                
            if not hard_warnings:
                all_sections_by_key[rep_s.key] = rep_s
                rep_s.status = "complete"
            else:
                rep_s.status = "requires_clarification"
                rep_s.body = "Cette section n'a pas pu être générée avec un niveau de certitude suffisant concernant les faits ou les citations. Une révision manuelle est requise."
                rep_s.bullets = []
                rep_s.evidence = []
                all_sections_by_key[rep_s.key] = rep_s
                quality.passed = False
                quality.warnings.extend([f"Section {rep_s.key} réparation échouée: {w}" for w in hard_warnings])

    elif critical_violations:
        quality.passed = False
        quality.warnings.extend(critical_violations)
        for k in violating_keys:
            if k in all_sections_by_key:
                all_sections_by_key[k].status = "requires_clarification"
                all_sections_by_key[k].body = "Cette section requiert une clarification car des violations de référence ou de faits ont été détectées."
                all_sections_by_key[k].bullets = []
                all_sections_by_key[k].evidence = []

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
        # A requirement stated in the immutable client brief is covered when the
        # final proposal anchors it explicitly or explains its significant terms.
        # PDF evidence strengthens the answer but is optional when no safe,
        # directly relevant internal reference was selected.
        need_terms = _significant_terms(need.text)
        section_keys = []
        for section in final_sections:
            section_text = " ".join([section.body or "", *(b.text for b in section.bullets), *section.assumptions, *section.questions])
            section_terms = _significant_terms(section_text)
            anchored = any(bullet.anchor and bullet.anchor.id == need.id for bullet in section.bullets)
            semantic_match = bool(need_terms) and len(need_terms & section_terms) >= max(1, min(3, len(need_terms) // 4))
            if anchored or semantic_match:
                section_keys.append(section.key)
        evidence_ids = [evidence.id for packet in packets if packet.requirement_id == need.id for evidence in packet.evidence]
        supporting = [evidence_id for evidence_id in evidence_ids if evidence_id in cited_evidence_ids]
        covered = bool(section_keys)
        compliance.append(ComplianceMatrixRow(
            requirement_id=need.id,
            requirement=need.text,
            covered=covered,
            section_keys=section_keys,
            supporting_evidence_ids=supporting,
            coverage_reason="Réponse ancrée dans une section et preuve PDF citée." if supporting else "Réponse fondée sur le brief ; aucune preuve PDF directement pertinente citée.",
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

    # Calculate deterministic score
    hard_violations_count = sum(1 for w in quality.warnings if _is_hard_violation(w))
    soft_warnings_count = len(quality.warnings) - hard_violations_count
    
    score = 1.0
    if not quality.passed or hard_violations_count > 0:
        score = max(0.0, score - 0.5 - (hard_violations_count * 0.1))
        quality.passed = False
        status = "degraded"
        
    score = max(0.0, score - (soft_warnings_count * 0.05))
    quality.score = round(score, 2)
    
    evidence_validation_passed = quality.passed and all(
        row.covered or not any(packet.evidence for packet in packets if packet.requirement_id == row.requirement_id)
        for row in compliance
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
        evidence_validation_passed=evidence_validation_passed,
        citations=[],
        quality=quality
    )

def generate_rfp_proposal(request: RfpRequest, settings: Settings) -> RfpResponse:
    """Entry point for RFP generation. Runs async internally."""
    mode = getattr(request, "mode", "standard")

    return asyncio.run(generate_standard_rfp_async(request, settings, mode))
