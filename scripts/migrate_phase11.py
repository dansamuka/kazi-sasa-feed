#!/usr/bin/env python3
"""Migrate existing feed snapshots to the Phase 11 schema and repair legacy source-default contamination.

This migration is intentionally useful for the *published* last-known-good feed.
It can upgrade a v3.6/v3.7 feed to v3.8 without waiting for every live source to
finish successfully. Legacy IDs are preserved; invalid generic official pages
and clearly non-African official vacancies are removed during the quality
repair because they should never have been published as Africa opportunities.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import re
from pathlib import Path
from typing import Any

from collectors.official_common import is_official_opportunity_in_scope, is_valid_job_title
from phase2_enrichment import Phase2Enricher
from refresh_feed import FeedBuilder

PHASE11_FEED_VERSION = "3.8"
from validate_feed import validate_feed


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _version_tuple(value: Any) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in str(value or "0").split("."))
    except ValueError:
        return (0,)


def _organisation_maps(organisations: dict[str, Any]) -> tuple[dict[str, set[str]], dict[str, bool]]:
    defaults: dict[str, set[str]] = {}
    allow_non_african: dict[str, bool] = {}
    for org in organisations.get("organisations", []):
        org_id = str(org.get("id") or "")
        values: set[str] = set()
        allow = False
        for source in org.get("sources", []):
            config = source.get("config") or {}
            values.update(str(value) for value in config.get("default_specialisations", []) if value)
            allow = allow or bool(config.get("include_non_african_roles"))
        defaults[org_id] = values
        allow_non_african[org_id] = allow
    return defaults, allow_non_african


def _is_official(row: dict[str, Any]) -> bool:
    source = row.get("source") or {}
    return bool(
        row.get("apply_is_official")
        or source.get("confidence") == "official"
        or source.get("kind") in {"employer_official", "government_official", "institution_official"}
    )


def _has_africa_remit(row: dict[str, Any]) -> bool:
    text = " ".join(str(value or "") for value in (row.get("title"), row.get("summary"), row.get("eligibility_notes")))
    return bool(re.search(r"\b(?:africa|african|sub[- ]saharan|east africa|west africa|central africa|southern africa|north africa)\b", text, re.I))


def _explicit_non_african_iso(row: dict[str, Any], african_iso2: set[str]) -> bool:
    location = row.get("location") or {}
    raw = str(location.get("raw") or "")
    # Common public ATS formats end in a two-letter country code: "Kyiv, UA".
    matches = re.findall(r"(?:^|[,/|\s])([A-Z]{2})(?=$|[,/|\s])", raw)
    return any(code not in african_iso2 and code not in {"EU", "UK"} for code in matches)


def _repair_source_defaults(
    row: dict[str, Any],
    *,
    builder: FeedBuilder,
    defaults_by_org: dict[str, set[str]],
) -> dict[str, Any]:
    """Move institution-level defaults out of role fields in legacy rows.

    Phase 7 originally inserted defaults such as ``investment_operations`` into
    every World Bank vacancy. Phase 8.1 changed collectors to store those values
    as context only. This repair applies that correction to an already-published
    feed so a Legal Analyst is no longer presented as an investment role.
    """
    repaired = deepcopy(row)
    organisation = repaired.get("organisation") or {}
    org_id = str(organisation.get("id") or "")
    defaults = defaults_by_org.get(org_id, set())
    existing = list(dict.fromkeys(repaired.get("specialisations") or repaired.get("categories") or []))
    if not defaults or not existing or not set(existing).intersection(defaults):
        return repaired

    source = repaired.get("source") or {}
    source_pack = (repaired.get("institution_profile") or {}).get("source_pack") or (repaired.get("ngo_profile") or {}).get("source_pack")
    if source.get("kind") not in {"institution_official", "employer_official"} and source_pack not in {
        "phase7_dfi_multilateral", "phase8_ngo_un_development"
    }:
        return repaired

    inferred = builder.infer_specialisations(repaired.get("title"), repaired.get("summary"), limit=3)
    non_default = [value for value in existing if value not in defaults]
    clean = list(dict.fromkeys([*inferred, *non_default]))[:3]
    repaired["source_context_specialisations"] = sorted(defaults)
    repaired["specialisations"] = clean
    repaired["categories"] = clean
    inferred_industry = builder.industry_for_specialisations(clean)
    if inferred_industry:
        repaired["industry"] = inferred_industry
    return repaired


def repair_and_enrich(root: Path, data: dict[str, Any], *, mark_bootstrap: bool = False) -> tuple[dict[str, Any], dict[str, int]]:
    organisations = load(root / "config/organisations.json")
    locations = load(root / "config/african_locations.json")
    role_taxonomy = load(root / "config/role_taxonomy.json")
    source_registry = load(root / "config/source_registry.json")
    investment_taxonomy = load(root / "config/investment_taxonomy.json")
    ngo_taxonomy = load(root / "config/ngo_taxonomy.json")
    taxonomy = load(root / "taxonomy.json")

    enricher = Phase2Enricher(
        organisations, locations, role_taxonomy, source_registry,
        investment_taxonomy, ngo_taxonomy,
    )
    inference_builder = FeedBuilder(taxonomy, source_registry)
    defaults_by_org, allow_non_african = _organisation_maps(organisations)
    african_iso2 = {str(country.get("iso2")) for country in locations.get("countries", []) if country.get("iso2")}

    previous_meta = dict(data.get("meta") or {})
    legacy_quality = (
        _version_tuple(previous_meta.get("feed_version")) < (3, 8)
        or str(previous_meta.get("official_vacancy_quality_version") or "0") < "1.1"
    )

    rows: list[dict[str, Any]] = []
    stats = {
        "input": len(data.get("opportunities", [])),
        "invalid_title_removed": 0,
        "non_african_official_removed": 0,
        "source_defaults_repaired": 0,
        "published": 0,
    }
    for original in data.get("opportunities", []):
        row = deepcopy(original)
        if legacy_quality:
            before_specs = list(row.get("specialisations") or row.get("categories") or [])
            row = _repair_source_defaults(row, builder=inference_builder, defaults_by_org=defaults_by_org)
            after_specs = list(row.get("specialisations") or row.get("categories") or [])
            if before_specs != after_specs:
                stats["source_defaults_repaired"] += 1

        official = _is_official(row)
        org_name = (row.get("organisation") or {}).get("name")
        if legacy_quality and official and not is_valid_job_title(row.get("title"), org_name):
            stats["invalid_title_removed"] += 1
            continue

        enriched = enricher.enrich(row)
        if legacy_quality and official:
            org_id = str((enriched.get("organisation") or {}).get("id") or "")
            allow = allow_non_african.get(org_id, False)
            location = enriched.get("location") or {}
            in_scope = is_official_opportunity_in_scope(
                location,
                str(enriched.get("title") or ""),
                str(enriched.get("summary") or ""),
                allow_non_african=allow,
            )
            explicit_non_african = _explicit_non_african_iso(enriched, african_iso2)
            if (not in_scope or (explicit_non_african and not allow and not _has_africa_remit(enriched))):
                stats["non_african_official_removed"] += 1
                continue
        rows.append(enriched)

    now = datetime.now(timezone.utc)
    meta = data.setdefault("meta", {})
    original_generated = previous_meta.get("source_data_generated_at") or previous_meta.get("generated_at")
    meta.update(
        {
            "feed_version": PHASE11_FEED_VERSION,
            "opportunity_count": len(rows),
            "source_count": len({(row.get("source") or {}).get("name") for row in rows if (row.get("source") or {}).get("name")}),
            "enterprise_adapter_version": "1.1",
            "ngo_source_pack_version": "1.0",
            "ngo_taxonomy_version": "1.0",
            "ngo_classifier_version": "1.1",
            "official_vacancy_quality_version": "1.1",
            "publication_repair_version": "1.0",
            "government_source_pack_version": "1.0",
            "government_schema_version": "1.0",
            "kenya_public_institutions_version": "1.0",
            "multinational_source_pack_version": "1.0",
            "multinational_adapter_version": "1.0",
        }
    )
    if mark_bootstrap:
        meta.update(
            {
                "generated_at": now.isoformat().replace("+00:00", "Z"),
                "next_expected_update": (now + timedelta(hours=6)).isoformat().replace("+00:00", "Z"),
                "source_data_generated_at": original_generated,
                "bootstrap_schema_migration": True,
                "live_refresh_completed": False,
            }
        )
    data["opportunities"] = rows
    stats["published"] = len(rows)

    validation = validate_feed(data, taxonomy, role_taxonomy)
    if validation.errors or validation.warnings:
        raise RuntimeError(f"Migrated feed is not clean: errors={validation.errors}; warnings={validation.warnings}")
    return data, stats


def migrate(root: Path, path: Path, *, mark_bootstrap: bool = False) -> dict[str, int]:
    data, stats = repair_and_enrich(root, load(path), mark_bootstrap=mark_bootstrap)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", default=["feed.json", "seed.json"])
    parser.add_argument("--bootstrap", action="store_true", help="Mark the output as a schema-migrated last-known-good feed")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    for value in args.paths:
        stats = migrate(root, root / value, mark_bootstrap=args.bootstrap)
        print("Migrated", value, json.dumps(stats, sort_keys=True))
