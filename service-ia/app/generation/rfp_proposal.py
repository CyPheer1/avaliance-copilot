"""Adaptive, evidence-safe RFP proposal composition."""

from __future__ import annotations

from ..schemas import RfpBlock, RfpCitation, RfpRequirements, RfpSection, RfpTable


def _slug(value: str) -> str:
    return "-".join("".join(character.lower() if character.isalnum() else " " for character in value).split()[:6]) or "brief"


def _section(title: str, blocks: list[RfpBlock]) -> RfpSection:
    """Create an identifier from the brief-derived title, never from a catalog."""
    section_id = _slug(title)
    return RfpSection(id=section_id, key=section_id, title=title, level=2, blocks=blocks)


def _paragraphs(items: list[str], evidence_ids: list[str] | None = None) -> list[RfpBlock]:
    return [RfpBlock(kind="paragraph", text=item, evidence_ids=evidence_ids or []) for item in items if item.strip()]


def _topic_title(fact: str, fallback: str) -> str:
    words = fact.strip().rstrip(".?!;").split()
    return " ".join(words[:8]).capitalize() if words else fallback


def build_adaptive_proposal(requirements: RfpRequirements, citations: list[RfpCitation]) -> list[RfpSection]:
    """Compose sections directly from the distinct subjects extracted from the brief."""
    evidence_ids = [f"evidence-{citation.chunk_id}" for citation in citations[:3] if citation.content.strip()]
    groups = [
        requirements.business_problem,
        requirements.project_type,
        requirements.technologies_and_constraints,
        requirements.security_and_compliance,
        requirements.expected_deliverables,
        requirements.scale,
        requirements.timeline_and_urgency,
    ]
    sections: list[RfpSection] = []
    used_titles: set[str] = set()
    for group in groups:
        distinct = list(dict.fromkeys(item.strip() for item in group if item.strip()))
        if not distinct:
            continue
        title = _topic_title(distinct[0], "Sujet à cadrer")
        normalized = _slug(title)
        if normalized in used_titles:
            continue
        used_titles.add(normalized)
        blocks = _paragraphs(distinct[:2], evidence_ids)
        blocks.append(RfpBlock(kind="callout", text="À confirmer au cadrage : périmètre, responsables, priorités et critères de réception."))
        sections.append(_section(title, blocks))

    if not sections:
        sections.append(_section("Cadrage du besoin exprimé", [
            RfpBlock(kind="paragraph", text="Le brief ne contient pas encore de sujet suffisamment précis pour structurer une proposition."),
            RfpBlock(kind="callout", text="À confirmer au cadrage : objectifs, périmètre, contraintes et résultat attendu."),
        ]))
    return sections
