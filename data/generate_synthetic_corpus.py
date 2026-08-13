"""Generate a deterministic, entirely synthetic French mission corpus."""

from __future__ import annotations

import argparse
import json
import random
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any


SECTORS = ("banque", "assurance", "télécom", "transport", "énergie")
MISSION_TYPES = (
    "modernisation applicative",
    "migration cloud",
    "data et BI",
    "cybersécurité",
    "DevOps",
)
TECHNOLOGY_STACKS = (
    ("Java", "Spring Boot", "PostgreSQL"),
    ("React", "TypeScript", "Azure"),
    ("Python", "FastAPI", "Kubernetes"),
    ("Terraform", "Docker", "GitLab CI"),
    ("Kafka", "Spark", "Power BI"),
)
DOCUMENT_KINDS = (
    "contexte projet",
    "note d'architecture",
    "retour d'expérience",
    "extrait de proposition",
)
FORBIDDEN_NAMES = ("avalıance", "avaliance", "acme", "contoso", "fabrikam")


def _slug(value: str) -> str:
    normalized = value.lower().translate(str.maketrans({
        "à": "a", "â": "a", "ç": "c", "é": "e", "è": "e", "ê": "e", "ë": "e",
        "î": "i", "ï": "i", "ô": "o", "ù": "u", "û": "u", "ü": "u",
    }))
    return re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")


def build_mission(index: int, rng: random.Random) -> dict[str, Any]:
    sector = SECTORS[index % len(SECTORS)]
    mission_type = MISSION_TYPES[(index // len(SECTORS)) % len(MISSION_TYPES)]
    stack = list(TECHNOLOGY_STACKS[index % len(TECHNOLOGY_STACKS)])
    rng.shuffle(stack)
    year = 2020 + index % 6
    mission_number = index + 1
    title = f"Mission synthétique {mission_number:03d} - {mission_type} dans le secteur {sector}"
    summary = (
        f"Cette mission fictive concerne un acteur anonyme du secteur {sector}. "
        f"L'équipe a conduit une {mission_type} avec {', '.join(stack)}. "
        "La solution a amélioré la fiabilité, la sécurité et la maîtrise des délais, "
        "sans utiliser de donnée client réelle."
    )
    document_count = 2 + index % 3
    documents = []
    for document_index in range(document_count):
        kind = DOCUMENT_KINDS[document_index]
        documents.append(
            {
                "chunk_index": document_index,
                "kind": kind,
                "content": (
                    f"{kind.capitalize()} fictif de la mission {mission_number:03d}. "
                    f"Dans le secteur {sector}, la {mission_type} repose sur {', '.join(stack)}. "
                    "Le scénario décrit des ateliers, des choix techniques et des résultats "
                    "entièrement synthétiques destinés à une démonstration hors ligne."
                ),
            }
        )

    return {
        "id": f"mission-{mission_number:03d}",
        "title": title,
        "sector": sector,
        "mission_type": mission_type,
        "technologies": stack,
        "year": year,
        "referent_tag": f"référent-fictif-{1 + index % 12:02d}",
        "summary": summary,
        "synthetic": True,
        "documents": documents,
    }


def validate_mission(mission: dict[str, Any]) -> None:
    required = {
        "id",
        "title",
        "sector",
        "mission_type",
        "technologies",
        "year",
        "referent_tag",
        "summary",
        "synthetic",
        "documents",
    }
    missing = required.difference(mission)
    if missing:
        raise ValueError(f"Champs obligatoires absents: {sorted(missing)}")
    if mission["sector"] not in SECTORS or mission["mission_type"] not in MISSION_TYPES:
        raise ValueError("Secteur ou type de mission non pris en charge")
    if mission["synthetic"] is not True or not 2 <= len(mission["documents"]) <= 4:
        raise ValueError("Chaque mission doit être synthétique et contenir 2 à 4 documents")
    if not mission["technologies"] or not all(isinstance(item, str) for item in mission["technologies"]):
        raise ValueError("La stack technologique est invalide")

    serialized = json.dumps(mission, ensure_ascii=False).lower()
    if any(name in serialized for name in FORBIDDEN_NAMES):
        raise ValueError("Le corpus contient un nom d'organisation interdit")
    for document in mission["documents"]:
        if set(document) != {"chunk_index", "kind", "content"} or not document["content"].strip():
            raise ValueError("Document synthétique invalide")


def generate_corpus(count: int, seed: int) -> list[dict[str, Any]]:
    if count < 1:
        raise ValueError("Le nombre de missions doit être positif")
    rng = random.Random(seed)
    missions = [build_mission(index, rng) for index in range(count)]
    for mission in missions:
        validate_mission(mission)
    return missions


def write_corpus(missions: list[dict[str, Any]], output: Path, seed: int, mode: str) -> dict[str, Any]:
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{output.name}-", dir=output.parent))
    try:
        for mission in missions:
            path = temporary / f"{mission['id']}-{_slug(mission['sector'])}.json"
            path.write_text(json.dumps(mission, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        manifest = {
            "schema_version": 1,
            "mode": mode,
            "seed": seed,
            "mission_count": len(missions),
            "document_count": sum(len(mission["documents"]) for mission in missions),
            "sectors": sorted({mission["sector"] for mission in missions}),
            "mission_types": sorted({mission["mission_type"] for mission in missions}),
            "synthetic": True,
        }
        (temporary / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        if output.exists():
            shutil.rmtree(output)
        temporary.replace(output)
        return manifest
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("templates",), default="templates")
    parser.add_argument("--count", type=int, default=300)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=Path, default=Path("data/corpus"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    missions = generate_corpus(args.count, args.seed)
    manifest = write_corpus(missions, args.output, args.seed, args.mode)
    print(
        f"Corpus synthétique généré: {manifest['mission_count']} missions, "
        f"{manifest['document_count']} documents ({args.output})"
    )


if __name__ == "__main__":
    main()