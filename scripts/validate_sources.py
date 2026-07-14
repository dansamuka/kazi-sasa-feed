#!/usr/bin/env python3
"""Validate sources.json governance rules and reject duplicate registrations."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter

VALID_CONFIDENCE = {"official", "aggregated", "community", "unverified"}


def validate_sources(data: dict) -> list[str]:
    errors: list[str] = []
    sources = data.get("sources")
    if not isinstance(sources, list):
        return ["top-level sources must be a list"]

    names = Counter()
    domains = Counter()
    pairs = Counter()
    for index, source in enumerate(sources):
        label = f"sources[{index}]"
        if not isinstance(source, dict):
            errors.append(f"{label} must be an object")
            continue
        name = source.get("name")
        domain = source.get("domain")
        confidence = source.get("default_confidence")
        if not name:
            errors.append(f"{label}.name is required")
        if confidence not in VALID_CONFIDENCE:
            errors.append(f"{label}.default_confidence must be one of {sorted(VALID_CONFIDENCE)}")
        if name:
            names[name.strip().lower()] += 1
        if domain:
            domains[domain.strip().lower()] += 1
        pairs[((name or "").strip().lower(), (domain or "").strip().lower())] += 1

    for pair, count in pairs.items():
        if count > 1:
            errors.append(f"duplicate source registration {pair!r} appears {count} times")
    for domain, count in domains.items():
        if count > 1:
            errors.append(f"domain '{domain}' appears {count} times")

    if data.get("default_for_unknown_source") not in VALID_CONFIDENCE:
        errors.append("default_for_unknown_source is missing or invalid")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sources_path", nargs="?", default="sources.json")
    args = parser.parse_args()
    with open(args.sources_path, encoding="utf-8") as handle:
        data = json.load(handle)
    errors = validate_sources(data)
    for error in errors:
        print(f"ERROR {error}")
    print(f"{len(errors)} error(s)")
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
