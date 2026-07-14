#!/usr/bin/env python3
"""Generate or verify Phase 1 compatibility artifacts from registries."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from registry import (
    LEGACY_CONFIG_FILE,
    legacy_ats_payload,
    legacy_sources_payload,
    load_organisation_registry,
    load_source_registry,
)


def serialise(payload: dict) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail if generated artifacts are stale")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    organisations = load_organisation_registry(root / "config" / "organisations.json")
    source_registry = load_source_registry(root / "config" / "source_registry.json")

    outputs = {
        root / "config" / filename: legacy_ats_payload(organisations, adapter)
        for adapter, filename in LEGACY_CONFIG_FILE.items()
    }
    outputs[root / "sources.json"] = legacy_sources_payload(source_registry)

    stale: list[str] = []
    for path, payload in outputs.items():
        expected = serialise(payload)
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if current == expected:
            continue
        if args.check:
            stale.append(str(path.relative_to(root)))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(expected, encoding="utf-8")
            print(f"Wrote {path.relative_to(root)}")

    if stale:
        for path in stale:
            print(f"ERROR stale generated artifact: {path}", file=sys.stderr)
        print("Run: python3 scripts/generate_legacy_configs.py", file=sys.stderr)
        raise SystemExit(1)
    if args.check:
        print(f"All {len(outputs)} generated registry artifacts are current.")


if __name__ == "__main__":
    main()
