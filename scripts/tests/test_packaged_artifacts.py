"""Ensure the feed artifacts shipped in the ZIP pass the same clean CI gates."""
from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
REPO = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

from validate_feed import validate_feed  # noqa: E402


def _load(name: str):
    return json.loads((REPO / name).read_text(encoding="utf-8"))


def test_packaged_feed_is_clean():
    result = validate_feed(_load("feed.json"), _load("taxonomy.json"), _load("config/role_taxonomy.json"))
    assert result.errors == []
    assert result.warnings == []


def test_packaged_seed_is_clean():
    result = validate_feed(_load("seed.json"), _load("taxonomy.json"), _load("config/role_taxonomy.json"))
    assert result.errors == []
    assert result.warnings == []


def test_all_source_mapping_targets_exist():
    taxonomy = _load("taxonomy.json")
    valid = {entry["id"] for entry in taxonomy["specialisations"]}
    targets = {
        target
        for mappings in taxonomy.get("source_specialisation_aliases", {}).values()
        for target in mappings.values()
    }
    assert targets <= valid
