"""Adaptive, evidence-safe RFP proposal composition."""

from __future__ import annotations

from ..schemas import RfpBlock, RfpCitation, RfpRequirements, RfpSection, RfpTable


def _facts(requirements: RfpRequirements) -> list[str]:
    values = [
        *requirements.business_problem, *requirements.project_type,
        *requirements.technologies_and_constraints, *requirements.security_and_compliance,
        *requirements.expected_deliverables, *requirements.scale,
        *requirements.timeline_and_urgency,
    ]
    return list(dict.fromkeys(values))[:5]


def _section(section_id: str, title: str, blocks: list[RfpBlock]) -> RfpSection:
    """Never emit an empty heading or placeholder-only table."""
    return RfpSection(id=section_id, key=section_id, title=title, level=2, blocks=blocks)


def _paragraphs(items: list[str], evidence_ids: list[str] | None = None) -> list[RfpBlock]:
    return [RfpBlock(kind="paragraph", text=item, evidence_ids=evidence_ids or []) for item in items if item.strip()]


def build_adaptive_proposal(requirements: RfpRequirements, citations: list[RfpCitation]) -> list[RfpSection]:
    """Choose proposal sections from actual brief signals, never from a fixed plan."""
    facts = _facts(requirements)
    evidence_ids = [f"evidence-{citation.chunk_id}" for citation in citations[:3] if citation.content.strip()]
    security = requirements.security_and_compliance
    constraints = requirements.technologies_and_constraints
    timeline = requirements.timeline_and_urgency
    deliverables = requirements.expected_deliverables
    sections = [_section("executive-summary", "Synthèse exécutive", [
        *_paragraphs(facts[:2]),
        RfpBlock(kind="callout", text="Nous proposons un cadrage ciblé pour transformer les priorités exprimées en décisions de mise en œuvre et critères de réception.", evidence_ids=evidence_ids),
    ])]

    if security or constraints:
        sections.append(_section("security-resilience", "Sécurité et résilience opérationnelle", [
            *_paragraphs([*security, *constraints]),
            RfpBlock(kind="bullets", items=[
                "Structurer la segmentation, l’authentification forte, la journalisation et la continuité autour de preuves de mise en œuvre.",
                "Prioriser les actifs et flux critiques au cadrage avant tout déploiement.",
            ], evidence_ids=evidence_ids),
        ]))

    approach_rows = [
        ["Cadrage", "Qualifier actifs, flux, priorités et responsabilités", "Décisions de périmètre et feuille de route"],
        ["Conception", "Définir l’architecture cible et les contrôles", "Dossier d’architecture et plan de mise en œuvre"],
        ["Déploiement et preuve", "Mettre en œuvre, superviser et tester", "Recette, exercice de continuité et transfert"],
    ]
    sections.append(_section("delivery-approach", "Démarche et livrables", [
        *_paragraphs(deliverables),
        RfpBlock(kind="table", table=RfpTable(title="Démarche proposée", columns=["Étape", "Objectif", "Résultat attendu"], rows=approach_rows)),
    ]))

    if timeline:
        sections.append(_section("priority-milestones", "Jalons prioritaires", [
            *_paragraphs(timeline),
            RfpBlock(kind="table", table=RfpTable(title="Trajectoire proposée", columns=["Jalon", "Décision attendue"], rows=[
                ["Lancement", "Valider les sites, actifs critiques et responsables"],
                ["Architecture cible", "Arbitrer les priorités de protection et de supervision"],
                ["Préparation de l’échéance", "Valider la recette et l’exercice de reprise"],
            ])),
        ]))

    if security or constraints:
        sections.append(_section("risks-governance", "Risques et gouvernance", [
            RfpBlock(kind="table", table=RfpTable(title="Risques à piloter", columns=["Risque", "Mesure de maîtrise"], rows=[
                ["Connaissance incomplète des flux", "Cartographier les flux prioritaires avant la segmentation"],
                ["Couverture inégale des journaux", "Définir les sources et cas d’usage de supervision prioritaires"],
                ["Reprise non éprouvée", "Planifier un exercice réaliste et capitaliser les écarts"],
            ])),
            RfpBlock(kind="callout", text="Un pilotage régulier permet de suivre les arbitrages, les risques et les preuves attendues."),
        ]))

    sections.append(_section("clarifications", "Points à clarifier", [
        RfpBlock(kind="bullets", items=["Confirmer le périmètre des actifs critiques et des solutions existantes.", "Préciser les responsabilités d’astreinte et les critères de succès."]),
    ]))
    return sections
