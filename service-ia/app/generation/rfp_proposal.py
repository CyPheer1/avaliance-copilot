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


def _section(
    key: str,
    title: str,
    *,
    facts: list[str] | None = None,
    recommendations: list[str] | None = None,
    tables: list[RfpTable] | None = None,
) -> RfpSection:
    """Create a customer-facing section without exposing retrieval internals.

    RFP brief facts are context, not evidence claims. PDF material is only added
    later when a claim has been individually validated against its source.
    """
    return RfpSection(
        key=key,
        title=title,
        facts_from_brief=facts or [],
        recommendations=recommendations or [],
        verified_references=[],
        tables=tables or [],
    )


def build_adaptive_proposal(requirements: RfpRequirements, citations: list[RfpCitation]) -> list[RfpSection]:
    """Compose only sections that are relevant to explicit brief requirements.

    Unknown details are grouped once in the closing clarifications section rather
    than repeated in template rows or empty headings.
    """
    facts = _facts(requirements)
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
        ),
    ]

    if security or constraints:
        sections.append(_section(
            "security_and_resilience",
            "Sécurité et résilience opérationnelle",
            facts=[*security, *constraints],
            recommendations=["Structurer les chantiers de segmentation, d’authentification forte, de journalisation et de reprise autour de critères de réception mesurables."],
        ))

    is_data_consolidation = any(term in " ".join(facts).lower() for term in ("base", "donnée", "kpi", "reporting", "attrition"))
    if is_data_consolidation:
        sections.extend([
            _section(
                "proposed_approach",
                "Approche proposée",
                recommendations=[
                    "Mettre en place une trajectoire de consolidation progressive : cartographie des quatorze sources, définition d’un modèle de données commun, puis industrialisation des flux prioritaires.",
                    "Construire les indicateurs commerciaux et d’attrition à partir de règles métier tracées, avec des contrôles de complétude, de fraîcheur et de cohérence avant publication.",
                ],
            ),
            _section(
                "governance",
                "Gouvernance et qualité des données",
                recommendations=[
                    "Installer une gouvernance associant métiers, data owners et équipes techniques ; chaque indicateur disposera d’un propriétaire, d’une définition validée et d’un niveau de qualité mesuré.",
                    "Traiter l’identité client unique comme un chantier dédié : règles de rapprochement, gestion des doublons, traçabilité des décisions et dispositif de correction partagé.",
                ],
            ),
            _section(
                "delivery_plan",
                "Plan de réalisation",
                recommendations=[
                    "Prévoir un premier lot orienté vers le reporting du lundi, afin de valider rapidement les sources, les règles de calcul et le circuit de publication.",
                    "Conduire ensuite les lots de consolidation par domaine, avec recette métier, suivi des anomalies et transfert de compétences avant généralisation.",
                ],
                tables=[RfpTable(
                    title="Phases proposées",
                    columns=["Phase", "Objectif", "Résultat attendu"],
                    rows=[
                        ["Cadrage", "Qualifier les sources, usages et priorités", "Périmètre, règles de gouvernance et feuille de route validés"],
                        ["Socle de données", "Consolider les données prioritaires et l’identité client", "Modèle commun, contrôles qualité et traçabilité opérationnels"],
                        ["Reporting", "Industrialiser les KPI et le cycle hebdomadaire", "Rapport du lundi validé par les métiers"],
                    ],
                )],
            ),
            _section(
                "risks_assumptions",
                "Risques et hypothèses",
                recommendations=[
                    "Les principaux risques concernent la qualité hétérogène des sources, les écarts de définition des KPI et la disponibilité des référents métier. Ils seront pilotés dans un registre de décisions et de risques.",
                    "Databricks sera évalué au regard des contraintes de volumétrie, d’intégration, de sécurité, d’exploitation et de coût ; il ne constitue pas une solution présélectionnée.",
                ],
            ),
            _section(
                "next_steps",
                "Questions de cadrage et prochaines étapes",
                recommendations=[
                    "Confirmer les quatorze sources, les propriétaires de données, le périmètre du premier reporting du lundi, les règles d’identité client et les critères d’acceptation.",
                    "Préciser les volumes, fréquences de mise à jour, contraintes d’hébergement, outils existants et disponibilité des équipes pour établir un chiffrage et un planning réalistes.",
                    "Aucune référence suffisamment proche n’a été identifiée.",
                ],
            ),
        ])
    else:
        phases_rows = [
            ["Cadrage", "Qualifier le périmètre, les flux, les priorités et les responsabilités", "Décisions de périmètre et feuille de route validées"],
            ["Conception", "Définir la cible, les règles de gestion et les critères de réception", "Dossier de conception et plan de mise en œuvre"],
            ["Déploiement", "Mettre en œuvre par incréments et accompagner la recette", "Recette et transfert aux équipes"],
        ]
        sections.append(_section(
            "delivery_approach",
            "Démarche et livrables",
            facts=deliverables,
            recommendations=["Organiser la réalisation par incréments, avec une validation conjointe des priorités et des résultats à chaque étape."],
            tables=[RfpTable(title="Phases de la mission", columns=["Phase", "Objectif", "Résultat attendu"], rows=phases_rows)],
        ))
        sections.append(_section(
            "clarifications",
            "Points à clarifier",
            recommendations=["Confirmer au cadrage le périmètre, les solutions existantes, les responsabilités et les critères de succès."],
        ))
    return sections
