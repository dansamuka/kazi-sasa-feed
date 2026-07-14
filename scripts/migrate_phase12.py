#!/usr/bin/env python3
"""Migrate existing snapshots to Africa/access certification schema v3.8."""
from __future__ import annotations

import argparse
import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

from phase2_enrichment import Phase2Enricher
from pipeline.deduplicate import deduplicate_opportunities
from validate_feed import validate_feed

FEED_VERSION = "3.8"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def build_enricher(root: Path) -> Phase2Enricher:
    return Phase2Enricher(
        load(root / "config/organisations.json"),
        load(root / "config/african_locations.json"),
        load(root / "config/role_taxonomy.json"),
        load(root / "config/source_registry.json"),
        load(root / "config/investment_taxonomy.json"),
        load(root / "config/ngo_taxonomy.json"),
        load(root / "config/global_country_codes.json"),
    )


def migrate_data(root: Path, data: dict, *, mark_bootstrap: bool = False) -> tuple[dict, dict]:
    enricher = build_enricher(root)
    rows = []
    rejected = []
    for original in data.get("opportunities", []):
        row = enricher.enrich(deepcopy(original))
        relevance = row.get("africa_relevance") or {}
        if relevance.get("status") == "non_african":
            rejected.append({
                "id": row.get("id"), "title": row.get("title"),
                "organisation": (row.get("organisation") or {}).get("name"),
                "location": row.get("location"),
                "reason": "known_non_african_without_africa_remit",
            })
            continue
        rows.append(row)

    rows, dedup = deduplicate_opportunities(rows)
    now = datetime.now(timezone.utc)
    old_meta = dict(data.get("meta") or {})
    meta = dict(old_meta)
    meta.update({
        "feed_version": FEED_VERSION,
        "opportunity_count": len(rows),
        "source_count": len({(row.get("source") or {}).get("name") for row in rows if (row.get("source") or {}).get("name")}),
        "africa_access_certification_version": "1.0",
        "government_deduplication_version": "3.0",
        "eligibility_evidence_version": "2.0",
    })
    if mark_bootstrap:
        meta.update({
            "source_data_generated_at": old_meta.get("source_data_generated_at") or old_meta.get("generated_at"),
            "generated_at": now.isoformat().replace("+00:00", "Z"),
            "next_expected_update": (now + timedelta(hours=6)).isoformat().replace("+00:00", "Z"),
            "bootstrap_schema_migration": True,
            "live_refresh_completed": False,
        })
    result = {"meta": meta, "opportunities": rows}
    validation = validate_feed(result, load(root / "taxonomy.json"), load(root / "config/role_taxonomy.json"))
    if validation.errors or validation.warnings:
        raise RuntimeError(f"Phase 12 migration is not clean: errors={validation.errors}; warnings={validation.warnings}")
    stats = {
        "input": len(data.get("opportunities", [])),
        "non_african_removed": len(rejected),
        "published": len(rows),
        "government_deduplication_loss_percent": dedup.get("government_loss_percent", 0.0),
        "rejected": rejected,
        "deduplication": dedup,
    }
    return result, stats


def migrate(root: Path, path: Path, *, mark_bootstrap: bool = False) -> dict:
    result, stats = migrate_data(root, load(path), mark_bootstrap=mark_bootstrap)
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return stats


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", default=["feed.json", "seed.json"])
    parser.add_argument("--bootstrap", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    for value in args.paths:
        path = (root / value).resolve()
        stats = migrate(root, path, mark_bootstrap=args.bootstrap)
        print(value, json.dumps({k: v for k, v in stats.items() if k not in {"rejected", "deduplication"}}, sort_keys=True))


if __name__ == "__main__":
    main()
