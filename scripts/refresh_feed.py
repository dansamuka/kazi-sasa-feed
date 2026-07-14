#!/usr/bin/env python3
"""Builds feed.json by running every collector in scripts/collectors/.

Runs each collector, aggregates all opportunities into a single FeedBuilder,
validates the result against SCHEMA.md, and only writes the output file if
validation passes. Individual collector failures are logged but don't abort
the whole run - so a broken ReliefWeb response doesn't lose you Greenhouse
data or vice versa, but if EVERY collector fails, the guard against writing
an empty feed.json over a good existing one kicks in.

Usage:
    python3 refresh_feed.py --out feed.json
"""
from __future__ import annotations

import argparse
from html import unescape
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from validate_feed import validate_feed  # noqa: E402
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
from phase2_enrichment import Phase2Enricher  # noqa: E402
from collectors.base import CollectorContext  # noqa: E402
from collectors.registry import collector_manifest, default_collector_specs, adapter_targets  # noqa: E402
from pipeline.collect import CollectorRunner  # noqa: E402
from pipeline.http import HttpClient  # noqa: E402
from pipeline.deduplicate import deduplicate_opportunities  # noqa: E402
from coverage_gates import evaluate_coverage_gates  # noqa: E402
from certification_gates import evaluate as evaluate_certification, build_certified_feed  # noqa: E402
from normalizers.temporal import normalise_opportunity_temporal_fields  # noqa: E402


FEED_VERSION = "3.8"


def load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _taxonomy_key(value: str | None) -> str:
    """Normalise source taxonomy labels, including HTML entities."""
    if value is None:
        return ""
    return " ".join(unescape(str(value)).split()).casefold()


class FeedBuilder:
    """Accumulates opportunities and produces a schema-valid feed.json dict."""

    def __init__(self, taxonomy: dict, sources: dict, enricher: Phase2Enricher | None = None):
        self.taxonomy = taxonomy
        self.sources = sources
        self.enricher = enricher
        self._industry_aliases = self._build_alias_map(taxonomy.get("industries", []))
        self._specialisation_aliases = self._build_alias_map(taxonomy.get("specialisations", []))
        self._skill_aliases = self._build_alias_map(taxonomy.get("skills", []))
        self._specialisation_industries = {
            entry["id"]: entry.get("industry")
            for entry in taxonomy.get("specialisations", [])
        }
        self._source_specialisation_aliases = {
            _taxonomy_key(source_key): {
                _taxonomy_key(raw): target
                for raw, target in mappings.items()
            }
            for source_key, mappings in taxonomy.get("source_specialisation_aliases", {}).items()
        }
        self._ignored_specialisation_terms = {
            _taxonomy_key(source_key): {_taxonomy_key(term) for term in terms}
            for source_key, terms in taxonomy.get("ignored_specialisation_terms", {}).items()
        }
        self.opportunities: list[dict] = []
        self.rejected_scope: list[dict] = []

    @staticmethod
    def _build_alias_map(entries: list[dict]) -> dict:
        alias_map = {}
        for entry in entries:
            alias_map[entry["id"]] = entry["id"]
            label = entry.get("label")
            if label:
                alias_map[_taxonomy_key(label)] = entry["id"]
            for alias in entry.get("aliases", []):
                alias_map[_taxonomy_key(alias)] = entry["id"]
        return alias_map

    def map_industry(self, raw: str) -> str | None:
        """Maps a source's raw category/department term to a v3 industry id.
        Returns None (not the raw term) when unmapped - unlike categories/
        skills, industry is meant to be a clean single-select field the app
        filters on directly, so an unmapped raw string is worse than nothing
        here. Logs a warning either way so gaps in taxonomy.json surface.
        """
        if not raw:
            return None
        mapped = self._industry_aliases.get(_taxonomy_key(raw))
        if mapped is None:
            print(f"WARN: industry term '{raw}' not in taxonomy.json industries - add it or an alias for it", file=sys.stderr)
            return None
        return mapped

    def map_specialisation(self, raw: str, source_key: str | None = None) -> str | None:
        """Map a raw source department/category to a canonical specialisation.

        Raw source labels must never leak into ``feed.json``. Source-specific
        mappings handle employer-internal labels such as Stripe's numeric
        department codes, while broad source categories that add no useful
        specialisation signal can be explicitly ignored.
        """
        if not raw:
            return None

        normalised = _taxonomy_key(raw)
        source_key_normalised = _taxonomy_key(source_key or "*")

        ignored = self._ignored_specialisation_terms.get("*", set()) | self._ignored_specialisation_terms.get(
            source_key_normalised, set()
        )
        if normalised in ignored:
            return None

        source_map = self._source_specialisation_aliases.get(source_key_normalised, {})
        global_map = self._source_specialisation_aliases.get("*", {})
        mapped = source_map.get(normalised) or global_map.get(normalised) or self._specialisation_aliases.get(normalised)
        if mapped is None:
            print(
                f"WARN: specialisation '{raw}' from {source_key_normalised} is unmapped; dropping it rather than publishing raw taxonomy",
                file=sys.stderr,
            )
            return None
        if mapped not in self._specialisation_aliases:
            print(
                f"WARN: configured mapping for '{raw}' points to unknown specialisation id '{mapped}'; dropping it",
                file=sys.stderr,
            )
            return None
        return mapped

    def map_specialisations(
        self,
        raw_terms: list[str] | tuple[str, ...],
        source_key: str | None = None,
        limit: int = 3,
    ) -> list[str]:
        """Map, filter and de-duplicate a list of source taxonomy terms."""
        mapped: list[str] = []
        for raw in raw_terms:
            value = self.map_specialisation(raw, source_key=source_key)
            if value and value not in mapped:
                mapped.append(value)
            if len(mapped) >= limit:
                break
        return mapped

    def map_category(self, raw: str, source_key: str | None = None) -> str | None:
        """Deprecated alias kept for any older/simpler collector code that
        hasn't been migrated to map_specialisation - same behaviour."""
        return self.map_specialisation(raw, source_key=source_key)

    def map_skill(self, raw: str) -> str | None:
        mapped = self._skill_aliases.get(_taxonomy_key(raw))
        if mapped is None:
            print(f"WARN: skill '{raw}' not in taxonomy.json - dropping raw term", file=sys.stderr)
            return None
        return mapped

    def map_skills(self, raw_terms: list[str] | tuple[str, ...]) -> list[str]:
        """Map, filter and de-duplicate skill terms without leaking raw values."""
        mapped: list[str] = []
        for raw in raw_terms:
            value = self.map_skill(raw)
            if value and value not in mapped:
                mapped.append(value)
        return mapped

    def industry_for_specialisations(self, specialisations: list[str]) -> str | None:
        """Return the first canonical parent industry for mapped specialisations."""
        for specialisation in specialisations:
            industry = self._specialisation_industries.get(specialisation)
            if industry:
                return industry
        return None

    def infer_specialisations(self, title: str | None, context: str | None = None, limit: int = 3) -> list[str]:
        """Infer canonical specialisations from job-specific text only.

        Registry defaults describe an institution, not every role it hires. This
        matcher therefore uses the title first and a short job-specific context
        second, preferring longer aliases and never using employer descriptions.
        """
        title_key = _taxonomy_key(title)
        context_key = _taxonomy_key(context)
        matches: list[tuple[int, int, str]] = []
        seen_ids: set[str] = set()
        for raw_alias, specialisation in self._specialisation_aliases.items():
            alias = _taxonomy_key(raw_alias)
            if not alias or len(alias) < 4 or specialisation in seen_ids:
                continue
            pattern = rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])"
            if re.search(pattern, title_key):
                matches.append((2, len(alias), specialisation)); seen_ids.add(specialisation)
            elif len(alias) >= 8 and re.search(pattern, context_key):
                matches.append((1, len(alias), specialisation)); seen_ids.add(specialisation)
        matches.sort(key=lambda row: (-row[0], -row[1], row[2]))
        return [row[2] for row in matches[:limit]]

    def confidence_for_domain(self, domain: str) -> str:
        for source in self.sources.get("sources", []):
            if source.get("domain") == domain:
                return source["default_confidence"]
        return self.sources.get("default_for_unknown_source", "unverified")

    def add(self, opportunity: dict):
        opportunity = normalise_opportunity_temporal_fields(opportunity)
        enriched = self.enricher.enrich(opportunity) if self.enricher else opportunity
        relevance = enriched.get("africa_relevance") or {}
        # Certification rule: known non-African duty stations without an
        # explicit Africa remit are never published in the Africa feed.
        if relevance.get("status") == "non_african":
            self.rejected_scope.append({
                "id": enriched.get("id"),
                "title": enriched.get("title"),
                "organisation": (enriched.get("organisation") or {}).get("name"),
                "location": enriched.get("location"),
                "reason": "known_non_african_without_africa_remit",
                "africa_relevance": relevance,
            })
            return
        self.opportunities.append(enriched)

    def deduplicate(self) -> int:
        """Resolve ID, URL and conservative semantic duplicates.

        Employer/government/institution-official records replace aggregator
        copies even when the aggregator was collected first. A structured
        report is retained for publication diagnostics.
        """
        self.opportunities, self.deduplication_report = deduplicate_opportunities(self.opportunities)
        return int(self.deduplication_report["removed_count"])

    def build(self, feed_version: str = FEED_VERSION, is_sample_data: bool = False) -> dict:
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        next_update = (datetime.now(timezone.utc) + timedelta(hours=6)).isoformat().replace("+00:00", "Z")
        return {
            "meta": {
                "feed_version": feed_version,
                "generated_at": now,
                "next_expected_update": next_update,
                "opportunity_count": len(self.opportunities),
                "source_count": len({o["source"]["name"] for o in self.opportunities if "source" in o}),
                "schema_url": "https://raw.githubusercontent.com/dansamuka/kazi-sasa-feed/main/SCHEMA.md",
                "is_sample_data": is_sample_data,
                "supported_languages": ["en", "fr", "pt", "ar", "sw"],
                "location_registry_version": "2.0",
                "source_expansion_version": "1.0",
                "deduplication_version": "2.0",
                "investment_taxonomy_version": "1.0",
                "investment_classifier_version": "1.0",
                "dfi_source_pack_version": "1.0",
                "enterprise_adapter_version": "1.1",
                "ngo_source_pack_version": "1.0",
                "ngo_taxonomy_version": "1.0",
                "ngo_classifier_version": "1.1",
                "official_vacancy_quality_version": "1.1",
                "publication_repair_version": "1.0",
                "bootstrap_schema_migration": False,
                "live_refresh_completed": True,
                "government_source_pack_version": "1.0",
                "government_schema_version": "1.0",
                "kenya_public_institutions_version": "1.0",
                "multinational_source_pack_version": "1.0",
                "multinational_adapter_version": "1.0",
                "africa_access_certification_version": "1.0",
                "government_deduplication_version": "3.0",
                "eligibility_evidence_version": "2.0",
            },
            "opportunities": self.opportunities,
        }


def _adapter_config(here: Path, organisations_path: str, adapter: str, legacy_name: str) -> list[dict]:
    """Backward-compatible Phase 1 helper, now delegated to the collector registry."""
    context = CollectorContext(
        builder=None,
        repo_root=here,
        organisations_path=organisations_path,
        env={},
    )
    return adapter_targets(context, adapter, legacy_name)


def _resolve_repo_path(here: Path, value: str) -> Path:
    path = (here / value).resolve()
    if here.resolve() not in path.parents and path != here.resolve():
        raise ValueError(f"resolved path {path} is outside repo root {here.resolve()}")
    return path


def _write_runtime_reports(
    here: Path,
    source_health_path: str,
    collector_manifest_path: str,
    collector_errors_path: str,
    per_source_counts: dict[str, int],
    source_statuses: dict[str, dict],
    configured_counts: dict[str, int],
    http_stats: dict,
) -> tuple[Path, Path, Path]:
    health_path = _resolve_repo_path(here, source_health_path)
    manifest_path = _resolve_repo_path(here, collector_manifest_path)
    errors_path = _resolve_repo_path(here, collector_errors_path)

    health_report = build_source_health_report(per_source_counts, source_statuses, configured_counts)
    health_report["http"] = dict(http_stats)
    write_json(health_path, health_report)
    write_json(
        manifest_path,
        {
            "manifest_version": "1.0",
            "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "collectors": collector_manifest(),
        },
    )
    write_json(
        errors_path,
        {
            "report_version": "1.0",
            "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "errors": [
                {"source": key, **status}
                for key, status in source_statuses.items()
                if status.get("status") == "error"
            ],
            "skipped": [
                {"source": key, **status}
                for key, status in source_statuses.items()
                if str(status.get("status", "")).startswith("skipped")
            ],
        },
    )
    return health_path, manifest_path, errors_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="feed.json", help="Output path")
    parser.add_argument("--taxonomy", default="taxonomy.json")
    parser.add_argument("--sources", default="config/source_registry.json")
    parser.add_argument("--organisations", default="config/organisations.json")
    parser.add_argument("--locations", default="config/african_locations.json")
    parser.add_argument("--global-countries", default="config/global_country_codes.json")
    parser.add_argument("--role-taxonomy", default="config/role_taxonomy.json")
    parser.add_argument("--investment-taxonomy", default="config/investment_taxonomy.json")
    parser.add_argument("--ngo-taxonomy", default="config/ngo_taxonomy.json")
    parser.add_argument("--coverage-report", default="reports/coverage_report.json")
    parser.add_argument("--source-health", default="reports/source_health.json")
    parser.add_argument("--collector-manifest", default="reports/collector_manifest.json")
    parser.add_argument("--collector-errors", default="reports/collector_errors.json")
    parser.add_argument("--deduplication-report", default="reports/deduplication_report.json")
    parser.add_argument("--coverage-gate-report", default="reports/coverage_gate_report.json")
    parser.add_argument("--investment-coverage-report", default="reports/investment_coverage_report.json")
    parser.add_argument("--dfi-coverage-report", default="reports/dfi_coverage_report.json")
    parser.add_argument("--ngo-coverage-report", default="reports/ngo_coverage_report.json")
    parser.add_argument("--government-coverage-report", default="reports/government_coverage_report.json")
    parser.add_argument("--public-institution-coverage-report", default="reports/kenya_public_institutions_report.json")
    parser.add_argument("--multinational-coverage-report", default="reports/multinational_coverage_report.json")
    parser.add_argument("--certification-report", default="reports/africa_eligibility_certification_report.json")
    parser.add_argument("--rejected-records", default="reports/rejected_records.json")
    parser.add_argument("--certified-feed", default="certified_feed.json")
    parser.add_argument("--public-institution-registry", default="config/kenya_public_institutions.json")
    parser.add_argument("--multinational-registry", default="config/multinational_targets.json")
    parser.add_argument("--coverage-gates", default="config/coverage_gates.json")
    parser.add_argument("--no-http-cache", action="store_true", help="Disable the short-lived shared GET cache")
    parser.add_argument(
        "--only-source",
        action="append",
        default=[],
        help="Run only a registered collector key. Repeat for multiple sources.",
    )
    parser.add_argument("--list-collectors", action="store_true", help="Print registered collector metadata and exit")
    args = parser.parse_args()

    here = Path(__file__).parent.parent  # feed/ - scripts/ is one level down
    if args.list_collectors:
        print(json.dumps({"collectors": collector_manifest()}, indent=2))
        return

    taxonomy = load_json(here / args.taxonomy)
    sources = load_json(here / args.sources)

    enricher = Phase2Enricher(
        load_json(here / args.organisations),
        load_json(here / args.locations),
        load_json(here / args.role_taxonomy),
        sources,
        load_json(here / args.investment_taxonomy),
        load_json(here / args.ngo_taxonomy),
        load_json(here / args.global_countries),
    )
    builder = FeedBuilder(taxonomy, sources, enricher=enricher)

    specs = default_collector_specs()
    known_keys = {spec.key for spec in specs}
    requested_keys = set(args.only_source)
    unknown_keys = sorted(requested_keys - known_keys)
    if unknown_keys:
        print(f"ERROR: unknown collector key(s): {', '.join(unknown_keys)}", file=sys.stderr)
        print(f"Known collectors: {', '.join(sorted(known_keys))}", file=sys.stderr)
        sys.exit(2)

    http_client = HttpClient(
        cache_dir=here / ".cache" / "http",
        cache_enabled=not args.no_http_cache,
    )
    context = CollectorContext(
        builder=builder,
        repo_root=here,
        organisations_path=args.organisations,
        env=os.environ,
        http=http_client,
        selected_sources=requested_keys or None,
    )
    try:
        run_summary = CollectorRunner(specs).run(context)
    finally:
        http_client.close()
    per_source_counts = run_summary.per_source_counts
    source_statuses = run_summary.statuses
    configured_counts = run_summary.configured_counts

    removed = builder.deduplicate()
    if removed:
        print(f"INFO: deduplicated {removed} cross-source duplicates", file=sys.stderr)

    print(f"INFO: collected per source: {per_source_counts}", file=sys.stderr)

    if not builder.opportunities:
        try:
            health_path, manifest_path, errors_path = _write_runtime_reports(
                here, args.source_health, args.collector_manifest, args.collector_errors,
                per_source_counts, source_statuses, configured_counts, http_client.stats,
            )
            print(f"Wrote failure diagnostics to {health_path}, {manifest_path}, and {errors_path}", file=sys.stderr)
        except ValueError as exc:
            print(f"ERROR: could not write failure diagnostics: {exc}", file=sys.stderr)
        print(
            "No opportunities collected across any source. Refusing to overwrite "
            "feed.json with an empty result. Check the per-source counts and "
            "error messages above.",
            file=sys.stderr,
        )
        sys.exit(1)

    feed = builder.build()

    result = validate_feed(feed, taxonomy, load_json(here / args.role_taxonomy))
    for w in result.warnings:
        print(f"WARN  {w}", file=sys.stderr)
    for e in result.errors:
        print(f"ERROR {e}", file=sys.stderr)
    if not result.ok or result.warnings:
        print("Generated feed failed clean validation - not writing output.", file=sys.stderr)
        sys.exit(1)

    coverage_gate_report = evaluate_coverage_gates(feed, load_json(here / args.coverage_gates))
    for warning in coverage_gate_report["warnings"]:
        print(f"WARN coverage: {warning}", file=sys.stderr)
    for error in coverage_gate_report["errors"]:
        print(f"ERROR coverage: {error}", file=sys.stderr)
    if coverage_gate_report["errors"]:
        print("Generated feed failed Phase 5 regression coverage gates - not writing output.", file=sys.stderr)
        sys.exit(1)

    certification_report = evaluate_certification(
        feed, getattr(builder, "deduplication_report", {})
    )
    for warning in certification_report["warnings"]:
        print(f"WARN certification: {warning}", file=sys.stderr)
    for error in certification_report["errors"]:
        print(f"ERROR certification: {error}", file=sys.stderr)
    if certification_report["errors"]:
        print("Generated feed failed Africa/access certification gates - not writing output.", file=sys.stderr)
        sys.exit(1)

    try:
        out_path = _resolve_repo_path(here, args.out)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    # Sanity check: this exact class of bug happened once already (a workflow
    # argument that, combined with `here` already being repo-root-absolute,
    # resolved one directory ABOVE the repo - silently writing outside git
    # tracking while every step still reported success). Refuse to write
    # anywhere outside `here` rather than repeat that silently.
    if here.resolve() not in out_path.parents and out_path != here.resolve():
        print(
            f"ERROR: resolved output path {out_path} is outside the repo root "
            f"{here.resolve()} - refusing to write there. Check the --out argument "
            f"(this exact bug happened before: a workflow passing '../feed.json' "
            f"combined with `here` already being absolute repo-root walked one "
            f"directory too far up, and every step still reported success while "
            f"silently discarding the real output).",
            file=sys.stderr,
        )
        sys.exit(1)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(feed, f, indent=2)
        f.write("\n")

    try:
        coverage_path = _resolve_repo_path(here, args.coverage_report)
        deduplication_path = _resolve_repo_path(here, args.deduplication_report)
        coverage_gate_path = _resolve_repo_path(here, args.coverage_gate_report)
        investment_coverage_path = _resolve_repo_path(here, args.investment_coverage_report)
        dfi_coverage_path = _resolve_repo_path(here, args.dfi_coverage_report)
        ngo_coverage_path = _resolve_repo_path(here, args.ngo_coverage_report)
        government_coverage_path = _resolve_repo_path(here, args.government_coverage_report)
        public_institution_coverage_path = _resolve_repo_path(here, args.public_institution_coverage_report)
        multinational_coverage_path = _resolve_repo_path(here, args.multinational_coverage_report)
        certification_path = _resolve_repo_path(here, args.certification_report)
        rejected_path = _resolve_repo_path(here, args.rejected_records)
        certified_feed_path = _resolve_repo_path(here, args.certified_feed)
        health_path, manifest_path, errors_path = _write_runtime_reports(
            here, args.source_health, args.collector_manifest, args.collector_errors,
            per_source_counts, source_statuses, configured_counts, http_client.stats,
        )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    write_json(
        coverage_path,
        build_coverage_report(feed, validation_errors=len(result.errors), validation_warnings=len(result.warnings)),
    )
    write_json(deduplication_path, {"report_version": "1.0", **getattr(builder, "deduplication_report", {"input_count": len(builder.opportunities), "published_count": len(builder.opportunities), "removed_count": 0, "events": []})})
    write_json(coverage_gate_path, coverage_gate_report)
    write_json(certification_path, certification_report)
    write_json(certified_feed_path, build_certified_feed(feed))
    write_json(rejected_path, {
        "report_version": "1.0",
        "generated_at": feed["meta"]["generated_at"],
        "rejected_count": len(builder.rejected_scope),
        "records": builder.rejected_scope,
    })
    write_json(investment_coverage_path, build_investment_coverage_report(feed))
    write_json(dfi_coverage_path, build_dfi_coverage_report(feed))
    write_json(ngo_coverage_path, build_ngo_coverage_report(feed))
    write_json(government_coverage_path, build_government_coverage_report(feed))
    write_json(
        public_institution_coverage_path,
        build_public_institution_coverage_report(feed, load_json(here / args.public_institution_registry)),
    )
    write_json(
        multinational_coverage_path,
        build_multinational_coverage_report(feed, load_json(here / args.multinational_registry)),
    )
    print(f"Wrote {len(builder.opportunities)} opportunities to {out_path}")
    print(f"Wrote coverage report to {coverage_path}")
    print(f"Wrote source health report to {health_path}")
    print(f"Wrote collector manifest to {manifest_path}")
    print(f"Wrote collector error log to {errors_path}")
    print(f"Wrote deduplication report to {deduplication_path}")
    print(f"Wrote coverage gate report to {coverage_gate_path}")
    print(f"Wrote investment coverage report to {investment_coverage_path}")
    print(f"Wrote DFI coverage report to {dfi_coverage_path}")
    print(f"Wrote NGO/UN coverage report to {ngo_coverage_path}")
    print(f"Wrote government coverage report to {government_coverage_path}")
    print(f"Wrote Kenya public-institution coverage report to {public_institution_coverage_path}")
    print(f"Wrote multinational coverage report to {multinational_coverage_path}")
    print(f"Wrote Africa/access certification report to {certification_path}")
    print(f"Wrote certified default feed to {certified_feed_path}")
    print(f"Wrote rejected records audit to {rejected_path}")


if __name__ == "__main__":
    main()
