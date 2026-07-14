#!/usr/bin/env python3
"""Migrate packaged feed/seed snapshots to Kenya-public-institution + Phase 11 schema."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from phase2_enrichment import Phase2Enricher
from refresh_feed import FEED_VERSION


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def migrate(root: Path, path: Path) -> None:
    data = load(path)
    enricher = Phase2Enricher(
        load(root / "config/organisations.json"),
        load(root / "config/african_locations.json"),
        load(root / "config/role_taxonomy.json"),
        load(root / "config/source_registry.json"),
        load(root / "config/investment_taxonomy.json"),
        load(root / "config/ngo_taxonomy.json"),
    )
    rows = [enricher.enrich(row) for row in data.get("opportunities", [])]
    data["opportunities"] = rows
    meta = data.setdefault("meta", {})
    meta.update(
        {
            "feed_version": FEED_VERSION,
            "opportunity_count": len(rows),
            "enterprise_adapter_version": "1.1",
            "ngo_source_pack_version": "1.0",
            "ngo_taxonomy_version": "1.0",
            "ngo_classifier_version": "1.1",
            "official_vacancy_quality_version": "1.1",
            "government_source_pack_version": "1.0",
            "government_schema_version": "1.0",
            "kenya_public_institutions_version": "1.0",
            "multinational_source_pack_version": "1.0",
            "multinational_adapter_version": "1.0",
        }
    )
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", default=["feed.json", "seed.json"])
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    for value in args.paths:
        migrate(root, root / value)
        print("Migrated", value)
