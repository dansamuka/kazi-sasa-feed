#!/usr/bin/env python3
"""Upgrade the existing published feed to v3.8 before attempting a long live refresh.

The script is idempotent. A successful live Phase 11 feed is left untouched.
An older feed is migrated in place, preserving its current listings where valid
and recording that the source data itself has not yet been freshly collected.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from migrate_phase12 import migrate


def needs_bootstrap(feed: dict) -> bool:
    meta = feed.get("meta") or {}
    if str(meta.get("feed_version")) != "3.8":
        return True
    if str(meta.get("official_vacancy_quality_version") or "0") < "1.1":
        return True
    if str(meta.get("publication_repair_version") or "0") < "1.0":
        return True
    if str(meta.get("africa_access_certification_version") or "0") < "1.0":
        return True
    required = ("government_profile", "public_institution_profile", "multinational_profile", "africa_relevance", "african_applicant_access")
    return any(any(field not in row for field in required) for row in feed.get("opportunities", []))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--feed", default="feed.json")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    path = (root / args.feed).resolve()
    feed = json.loads(path.read_text(encoding="utf-8"))
    if not args.force and not needs_bootstrap(feed):
        print("Published feed already satisfies Africa/access certification bootstrap requirements; no change.")
        return
    stats = migrate(root, path, mark_bootstrap=True)
    print("Bootstrapped published feed:", json.dumps(stats, sort_keys=True))


if __name__ == "__main__":
    main()
