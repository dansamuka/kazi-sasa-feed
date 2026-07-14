#!/usr/bin/env python3
"""Add Phase 6 investment/DFI classification to packaged feed snapshots.

The migration is additive for the current Android contract: IDs and every field
consumed by the current DTO projection remain unchanged. Phase 2 role metadata
may be refined because it is itself an additive feed field.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from phase2_enrichment import Phase2Enricher, legacy_projection
from validate_feed import validate_feed


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _digest(rows: list[dict]) -> str:
    payload = json.dumps(
        [legacy_projection(row) for row in rows], sort_keys=True,
        separators=(",", ":"), ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def migrate(root: Path, path: Path) -> dict:
    feed = _load(path)
    before_ids = [row.get("id") for row in feed.get("opportunities", [])]
    before = _digest(feed.get("opportunities", []))
    enricher = Phase2Enricher(
        _load(root / "config/organisations.json"),
        _load(root / "config/african_locations.json"),
        _load(root / "config/role_taxonomy.json"),
        _load(root / "config/source_registry.json"),
        _load(root / "config/investment_taxonomy.json"),
    )
    feed["opportunities"] = [enricher.enrich(row) for row in feed.get("opportunities", [])]
    meta = feed.setdefault("meta", {})
    meta["feed_version"] = "3.4"
    meta["opportunity_count"] = len(feed["opportunities"])
    meta["investment_taxonomy_version"] = "1.0"
    meta["investment_classifier_version"] = "1.0"
    after_ids = [row.get("id") for row in feed.get("opportunities", [])]
    after = _digest(feed["opportunities"])
    if before_ids != after_ids:
        raise RuntimeError("opportunity IDs or ordering changed during Phase 6 migration")
    if before != after:
        raise RuntimeError(f"legacy projection changed: {before} != {after}")

    result = validate_feed(
        feed, _load(root / "taxonomy.json"), _load(root / "config/role_taxonomy.json")
    )
    if result.errors or result.warnings:
        raise RuntimeError(f"Phase 6 artifact is not clean: errors={result.errors}, warnings={result.warnings}")
    path.write_text(json.dumps(feed, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    counts: dict[str, int] = {}
    tracks: dict[str, int] = {}
    for row in feed["opportunities"]:
        profile = row.get("investment_profile") or {}
        classification = profile.get("classification") or "missing"
        counts[classification] = counts.get(classification, 0) + 1
        if profile.get("track"):
            tracks[profile["track"]] = tracks.get(profile["track"], 0) + 1
    return {
        "path": str(path),
        "opportunities": len(feed["opportunities"]),
        "legacy_projection_sha256": after,
        "classification_counts": counts,
        "track_counts": tracks,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", help="feed/seed paths relative to repository root")
    parser.add_argument("--root", default=None)
    args = parser.parse_args()
    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parent.parent
    for raw in args.paths:
        path = Path(raw)
        if not path.is_absolute():
            path = root / path
        print(json.dumps(migrate(root, path.resolve()), ensure_ascii=False))


if __name__ == "__main__":
    main()
