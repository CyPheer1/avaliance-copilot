"""Adaptive, evidence-safe RFP proposal composition."""

from __future__ import annotations

from ..schemas import RfpCitation, RfpClaim, RfpRequirements, RfpSection, RfpTable


def _facts(requirements: RfpRequirements) -> list[str]:
    values = [
        *requirements.business_problem,
        *requirements.project_type,
        *requirements.technologies_and_constraints,
        *requirements.security_and_compliance,
        *requirements.expected_deliverables,
        *requirements.scale,
        *requirements.timeline_and_urgency,
    ]
    return list(dict.fromkeys(values))[:5]


def _evidence(citations: list[RfpCitation]) -> list[RfpClaim]:
    return [
        RfpClaim(
            text=f"Extrait de référence interne vérifiée : {citation.content[:360].strip()}",
            citation_indexes=[citation.source_index],
        )
        for citation in citations[:3]
        if citation.content.strip()
    ]


def _section(key: str, title: str, *, facts: list[str] | None = None, recommendations: list[str] | None = None, evidence: list[RfpClaim] | None = None, tables: list[RfpTable] | None = None) -> RfpSection:
    return RfpSection(
        key=key,
        title=title,
        facts_from_brief=facts or [],
        recommendations=recommendations or [],
        verified_references=evidence or [],
        tables=tables or [],
    )


def build_adaptive_proposal(requirements: RfpRequirements, citations: list[RfpCitation]) -> list[RfpSection]:
    """Compose only sections that are relevant to explicit brief requirements.

    Unknown details are grouped once in the closing clarifications section rather
    than repeated in template rows or empty headings.
    """
    facts = _facts(requirements)
    verified = _evidence(citations)
    security = requirements.security_and_compliance
    constraints = requirements.technologies_and_constraints
    timeline = requirements.timeline_and_urgency
    deliverables = requirements.expected_deliverables
    sections = [
        _section(
            "executive_summary",
            "Synthèse exécutive",
            facts=facts,
            recommendations=["Nous proposons un cadrage rapide afin de prioriser les décisions de sécurité, de continuité et de déploiement avant l’échéance annoncée."],
            evidence=verified,
        ),
    ]

    if security or constraints:
        sections.append(_section(
            "security_and_resilience",
            "Sécurité et résilience opérationnelle",
            facts=[*security, *constraints],
            recommendations=["Structurer les chantiers de segmentation, d’authentification forte, de journalisation et de reprise autour de critères de réception mesurables."],
            evidence=verified,
        ))

    phases_rows = [
        ["Cadrage", "Qualifier les actifs, flux, priorités et responsabilités", "Décisions de périmètre et feuille de route validées"],
        ["Conception", "Définir l’architecture cible et les contrôles de sécurité", "Dossier d’architecture et plan de mise en œuvre"],
        ["Déploiement et preuve", "Mettre en œuvre, superviser et tester les scénarios critiques", "Recette, exercice de continuité et transfert aux équipes"],
    ]
    sections.append(_section(
        "delivery_approach",
        "Démarche et livrables",
        facts=deliverables,
        recommendations=["Organiser la réalisation par incréments, avec une validation conjointe des contrôles et des scénarios de reprise à chaque étape."],
        tables=[RfpTable(title="Phases de la mission", columns=["Phase", "Objectif", "Résultat attendu"], rows=phases_rows)],
    ))

    if timeline:
        sections.append(_section(
            "roadmap",
            "Jalons prioritaires",
            facts=timeline,
            tables=[RfpTable(
                title="Trajectoire proposée",
                columns=["Jalon", "Décision attendue"],
                rows=[
                    ["Lancement", "Valider les sites, actifs critiques et responsables de chantier"],
                    ["Architecture cible", "Arbitrer les priorités de segmentation, MFA, SIEM et continuité"],
                    ["Préparation de l’échéance", "Valider la recette et l’exercice de reprise avant l’échéance réglementaire"],
                ],
            )],
        ))

    if security or constraints:
        sections.append(_section(
            "risks_and_governance",
            "Risques et gouvernance",
            recommendations=["Installer un comité de pilotage court et régulier, avec un suivi des risques, arbitrages et preuves de conformité."],
            tables=[RfpTable(
                title="Risques à piloter",
                columns=["Risque", "Mesure de maîtrise"],
                rows=[
                    ["Connaissance incomplète des flux inter-sites", "Cartographier les flux prioritaires avant la segmentation"],
                    ["Couverture inégale des journaux", "Définir les sources et cas d’usage SIEM prioritaires"],
                    ["Reprise non éprouvée", "Planifier un exercice réaliste et capitaliser les écarts"],
                ],
            )],
        ))

    sections.append(_section(
        "clarifications",
        "Points à clarifier",
        recommendations=["Confirmer au cadrage le périmètre des actifs critiques, les solutions existantes, les responsabilités d’astreinte et les critères de succès de la mise en conformité."],
    ))
    return sections
