#!/usr/bin/env python3
"""Enrich an existing feed/seed snapshot with additive Phase 2 fields."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from phase2_enrichment import Phase2Enricher, legacy_projection
from validate_feed import validate_feed


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _digest(opportunities: list[dict]) -> str:
    payload = json.dumps(
        [legacy_projection(row) for row in opportunities],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def migrate(root: Path, input_path: Path, output_path: Path, feed_version: str = "3.1") -> dict:
    feed = _load(input_path)
    before_digest = _digest(feed.get("opportunities", []))
    enricher = Phase2Enricher(
        _load(root / "config/organisations.json"),
        _load(root / "config/african_locations.json"),
        _load(root / "config/role_taxonomy.json"),
        _load(root / "config/source_registry.json"),
    )
    feed["opportunities"] = [enricher.enrich(row) for row in feed.get("opportunities", [])]
    feed.setdefault("meta", {})["feed_version"] = feed_version
    feed["meta"]["opportunity_count"] = len(feed["opportunities"])
    after_digest = _digest(feed["opportunities"])
    if before_digest != after_digest:
        raise RuntimeError(f"legacy projection changed during additive migration: {before_digest} != {after_digest}")

    result = validate_feed(feed, _load(root / "taxonomy.json"), _load(root / "config/role_taxonomy.json"))
    if result.errors or result.warnings:
        raise RuntimeError(f"migrated artifact is not clean: errors={result.errors}, warnings={result.warnings}")
    output_path.write_text(json.dumps(feed, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"input": str(input_path), "output": str(output_path), "legacy_projection_sha256": after_digest}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", help="feed or seed JSON files to migrate in place")
    parser.add_argument("--root", default=None)
    parser.add_argument("--feed-version", default="3.1")
    args = parser.parse_args()
    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parent.parent
    for raw in args.paths:
        path = (root / raw).resolve() if not Path(raw).is_absolute() else Path(raw)
        result = migrate(root, path, path, args.feed_version)
        print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
