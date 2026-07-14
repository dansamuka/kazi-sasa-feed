#!/usr/bin/env python3
"""Generate coverage and snapshot health reports from an existing feed.

Unlike a live refresh this cannot know request timings or upstream errors, but
it uses the same Phase 3 collector registry so source inventory cannot drift
from the production orchestrator.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from collections import Counter
from collections.abc import Sized
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from collectors.base import CollectorContext  # noqa: E402
from collectors.registry import collector_manifest, default_collector_specs  # noqa: E402
from reporting import (  # noqa: E402
    build_coverage_report,
    build_investment_coverage_report,
    build_dfi_coverage_report,
    build_ngo_coverage_report,
    build_government_coverage_report,
    build_public_institution_coverage_report,
    build_multinational_coverage_report,
    build_source_health_report,
    write_json,
)
from coverage_gates import evaluate_coverage_gates  # noqa: E402
from pipeline.deduplicate import deduplicate_opportunities  # noqa: E402
from validate_feed import validate_feed  # noqa: E402


def _collector_key(opportunity: dict) -> str:
    opp_id = str(opportunity.get("id") or "")
    return opp_id.split("-", 1)[0].lower() if "-" in opp_id else "unknown"


def _count_config(config) -> int:
    if config is None:
        return 0
    if isinstance(config, dict):
        return len(config.get("boards", config))
    if isinstance(config, Sized) and not isinstance(config, (str, bytes, bytearray)):
        return len(config)
    return 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feed", default="feed.json")
    parser.add_argument("--taxonomy", default="taxonomy.json")
    parser.add_argument("--coverage", default="reports/coverage_report.json")
    parser.add_argument("--role-taxonomy", default="config/role_taxonomy.json")
    parser.add_argument("--organisations", default="config/organisations.json")
    parser.add_argument("--health", default="reports/source_health.json")
    parser.add_argument("--collector-manifest", default="reports/collector_manifest.json")
    parser.add_argument("--collector-errors", default="reports/collector_errors.json")
    parser.add_argument("--deduplication", default="reports/deduplication_report.json")
    parser.add_argument("--coverage-gates", default="config/coverage_gates.json")
    parser.add_argument("--coverage-gate-report", default="reports/coverage_gate_report.json")
    parser.add_argument("--investment-coverage", default="reports/investment_coverage_report.json")
    parser.add_argument("--dfi-coverage", default="reports/dfi_coverage_report.json")
    parser.add_argument("--ngo-coverage", default="reports/ngo_coverage_report.json")
    parser.add_argument("--government-coverage", default="reports/government_coverage_report.json")
    parser.add_argument("--public-institution-coverage", default="reports/kenya_public_institutions_report.json")
    parser.add_argument("--multinational-coverage", default="reports/multinational_coverage_report.json")
    parser.add_argument("--public-institution-registry", default="config/kenya_public_institutions.json")
    parser.add_argument("--multinational-registry", default="config/multinational_targets.json")
    args = parser.parse_args()

    feed_path = Path(args.feed).resolve()
    repo = feed_path.parent
    feed = json.loads(feed_path.read_text(encoding="utf-8"))
    taxonomy = json.loads(Path(args.taxonomy).read_text(encoding="utf-8"))
    role_taxonomy = json.loads(Path(args.role_taxonomy).read_text(encoding="utf-8"))
    validation = validate_feed(feed, taxonomy, role_taxonomy)

    counts = Counter(_collector_key(opp) for opp in feed.get("opportunities", []))
    specs = default_collector_specs()
    manifest_by_key = {row["key"]: row for row in collector_manifest()}
    context = CollectorContext(
        builder=None,
        repo_root=repo,
        organisations_path=args.organisations,
        env={},
    )
    configured_counts: dict[str, int] = {}
    statuses: dict[str, dict] = {}

    for spec in specs:
        if spec.resolve_config:
            configured_counts[spec.key] = _count_config(spec.resolve_config(context))
        count = int(counts.get(spec.key, 0))
        metadata = manifest_by_key[spec.key]
        statuses[spec.key] = {
            "status": "collected" if count else "empty",
            "reason": "observed in packaged feed snapshot" if count else "not represented in packaged feed snapshot",
            "source_kind": metadata["source_kind"],
            "schedule_class": metadata["schedule_class"],
            "freshness_hours": metadata["freshness_hours"],
            "timeout_seconds": metadata["timeout_seconds"],
        }
        counts.setdefault(spec.key, 0)

    write_json(
        Path(args.coverage),
        build_coverage_report(feed, len(validation.errors), len(validation.warnings)),
    )
    health_report = build_source_health_report(dict(counts), statuses, configured_counts)
    health_report["http"] = {
        "network_requests": 0,
        "cache_hits": 0,
        "throttle_sleeps": 0,
        "note": "Snapshot report generated without live HTTP collection; a live refresh replaces these metrics.",
    }
    write_json(Path(args.health), health_report)
    generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    write_json(
        Path(args.collector_manifest),
        {"manifest_version": "1.0", "generated_at": generated_at, "collectors": collector_manifest()},
    )
    write_json(
        Path(args.collector_errors),
        {
            "report_version": "1.0",
            "generated_at": generated_at,
            "errors": [],
            "skipped": [],
            "note": "Snapshot report generated without live collection; a live refresh replaces this file.",
        },
    )
    _, dedup_report = deduplicate_opportunities(list(feed.get("opportunities", [])))
    write_json(Path(args.deduplication), {"report_version": "1.0", **dedup_report, "note": "Snapshot audit; live refresh reports pre-publication cross-source removals."})
    coverage_config = json.loads(Path(args.coverage_gates).read_text(encoding="utf-8"))
    write_json(Path(args.coverage_gate_report), evaluate_coverage_gates(feed, coverage_config))
    write_json(Path(args.investment_coverage), build_investment_coverage_report(feed))
    write_json(Path(args.dfi_coverage), build_dfi_coverage_report(feed))
    write_json(Path(args.ngo_coverage), build_ngo_coverage_report(feed))
    write_json(Path(args.government_coverage), build_government_coverage_report(feed))
    public_registry = json.loads(Path(args.public_institution_registry).read_text(encoding="utf-8"))
    multinational_registry = json.loads(Path(args.multinational_registry).read_text(encoding="utf-8"))
    write_json(Path(args.public_institution_coverage), build_public_institution_coverage_report(feed, public_registry))
    write_json(Path(args.multinational_coverage), build_multinational_coverage_report(feed, multinational_registry))
    print(
        f"Wrote {args.coverage}, {args.health}, {args.collector_manifest}, "
        f"{args.collector_errors}, {args.deduplication}, {args.coverage_gate_report}, "
        f"and {args.investment_coverage}, {args.dfi_coverage}, {args.ngo_coverage}, {args.government_coverage}, "
        f"{args.public_institution_coverage}, {args.multinational_coverage}"
    )


if __name__ == "__main__":
    main()
