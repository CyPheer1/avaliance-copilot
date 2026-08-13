import json
from pathlib import Path

import pytest

from data.generate_synthetic_corpus import (
    MISSION_TYPES,
    SECTORS,
    generate_corpus,
    validate_mission,
    write_corpus,
)


def test_generation_is_deterministic_and_covers_all_categories():
    first = generate_corpus(300, 42)
    second = generate_corpus(300, 42)

    assert first == second
    assert {mission["sector"] for mission in first} == set(SECTORS)
    assert {mission["mission_type"] for mission in first} == set(MISSION_TYPES)
    assert sum(len(mission["documents"]) for mission in first) == 900
    assert all(mission["synthetic"] for mission in first)


def test_writer_creates_records_and_machine_readable_manifest(tmp_path: Path):
    missions = generate_corpus(10, 7)
    output = tmp_path / "corpus"

    manifest = write_corpus(missions, output, seed=7, mode="templates")
    record_files = sorted(path for path in output.glob("*.json") if path.name != "manifest.json")
    stored_manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))

    assert len(record_files) == 10
    assert stored_manifest == manifest
    assert manifest["mission_count"] == 10
    assert manifest["document_count"] == 29


def test_validation_rejects_non_synthetic_or_named_organization():
    mission = generate_corpus(1, 42)[0]
    mission["summary"] = "Mission réelle pour Contoso"

    with pytest.raises(ValueError, match="organisation.*interdit"):
        validate_mission(mission)