#!/usr/bin/env python3
"""Migrate an existing feed snapshot to Phase 0's strict v3 baseline."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).parent))
from collectors._common import classify_industry, is_relevant_opportunity, parse_location  # noqa: E402
from refresh_feed import FEED_VERSION, FeedBuilder, load_json  # noqa: E402
from phase2_enrichment import Phase2Enricher  # noqa: E402
from validate_feed import validate_feed  # noqa: E402


def _source_key(opp: dict) -> str:
    opp_id = str(opp.get("id") or "")
    source_url = ((opp.get("source") or {}).get("url") or "").rstrip("/")
    parsed = urlparse(source_url)
    tail = parsed.path.rstrip("/").split("/")[-1] if parsed.path else ""
    if opp_id.startswith("greenhouse-"):
        return f"greenhouse:{tail}" if tail else "greenhouse"
    if opp_id.startswith("lever-"):
        return f"lever:{tail}" if tail else "lever"
    if opp_id.startswith("ashby-"):
        return f"ashby:{tail}" if tail else "ashby"
    if opp_id.startswith("pinpoint-"):
        subdomain = parsed.netloc.split(".")[0] if parsed.netloc else ""
        return f"pinpoint:{subdomain}" if subdomain else "pinpoint"
    return opp_id.split("-", 1)[0].lower() if "-" in opp_id else "*"


def _merge_location(original: dict) -> dict:
    original = original or {}
    parsed = parse_location(original.get("raw"))
    # Structured country values from APIs such as Adzuna/ReliefWeb are more
    # authoritative than trying to infer a country from a city-only raw label.
    if not parsed.get("country") and original.get("country"):
        parsed["country"] = original["country"]
        if str(original["country"]).lower() == "kenya":
            parsed["scope"] = "national"
        elif original.get("scope") in {"regional", "national"}:
            parsed["scope"] = original.get("scope")
        else:
            parsed["scope"] = "international"
    if original.get("region") and not parsed.get("region"):
        parsed["region"] = original.get("region")
    if original.get("relocation_country"):
        parsed["relocation_country"] = original.get("relocation_country")
    return parsed


def migrate(
    feed: dict, taxonomy: dict, sources: dict, enricher: Phase2Enricher | None = None,
    role_taxonomy: dict | None = None,
) -> tuple[dict, list[dict]]:
    builder = FeedBuilder(taxonomy, sources, enricher=enricher)
    kept: list[dict] = []
    rejected: list[dict] = []
    is_sample = bool((feed.get("meta") or {}).get("is_sample_data"))

    for original in feed.get("opportunities", []):
        opp = dict(original)
        location = _merge_location(opp.get("location") or {})
        opp["location"] = location
        summary = opp.get("summary") or ""
        if not is_sample and not is_relevant_opportunity(location, summary):
            rejected.append({
                "id": opp.get("id"),
                "title": opp.get("title"),
                "source": (opp.get("source") or {}).get("name"),
                "location_raw": location.get("raw"),
                "reason": "no verified African/global location or role-specific international mobility evidence",
            })
            continue

        raw_terms = opp.get("specialisations") or opp.get("categories") or []
        mapped = builder.map_specialisations(list(raw_terms), source_key=_source_key(opp))
        opp["categories"] = mapped
        opp["specialisations"] = mapped
        opp["skills_required"] = builder.map_skills(list(opp.get("skills_required") or []))
        opp["skills_preferred"] = builder.map_skills(list(opp.get("skills_preferred") or []))
        if not opp.get("industry"):
            opp["industry"] = builder.industry_for_specialisations(mapped) or classify_industry(
                opp.get("title"), opp.get("summary")
            )
        kept.append(enricher.enrich(opp) if enricher else opp)

    now = datetime.now(timezone.utc)
    meta = dict(feed.get("meta") or {})
    meta.update({
        "feed_version": FEED_VERSION,
        "generated_at": now.isoformat().replace("+00:00", "Z"),
        "next_expected_update": (now + timedelta(hours=6)).isoformat().replace("+00:00", "Z"),
        "opportunity_count": len(kept),
        "source_count": len({(o.get("source") or {}).get("name") for o in kept}),
        "is_sample_data": is_sample,
        "investment_taxonomy_version": "1.0",
        "investment_classifier_version": "1.0",
    })
    result = {"meta": meta, "opportunities": kept}
    validation = validate_feed(result, taxonomy, role_taxonomy)
    if validation.errors or validation.warnings:
        for warning in validation.warnings:
            print(f"WARN {warning}", file=sys.stderr)
        for error in validation.errors:
            print(f"ERROR {error}", file=sys.stderr)
        raise RuntimeError(
            f"normalised feed is not clean: {len(validation.errors)} errors, {len(validation.warnings)} warnings"
        )
    return result, rejected


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("feed_path", nargs="?", default="feed.json")
    parser.add_argument("--out", default="feed.json")
    parser.add_argument("--taxonomy", default="taxonomy.json")
    parser.add_argument("--sources", default="sources.json")
    parser.add_argument("--rejected", default="reports/phase0_rejected_records.json")
    parser.add_argument("--organisations", default="config/organisations.json")
    parser.add_argument("--locations", default="config/african_locations.json")
    parser.add_argument("--role-taxonomy", default="config/role_taxonomy.json")
    parser.add_argument("--source-registry", default="config/source_registry.json")
    parser.add_argument("--investment-taxonomy", default="config/investment_taxonomy.json")
    parser.add_argument("--ngo-taxonomy", default="config/ngo_taxonomy.json")
    args = parser.parse_args()

    feed = load_json(Path(args.feed_path))
    taxonomy = load_json(Path(args.taxonomy))
    sources = load_json(Path(args.sources))
    role_taxonomy = load_json(Path(args.role_taxonomy))
    enricher = Phase2Enricher(
        load_json(Path(args.organisations)),
        load_json(Path(args.locations)),
        role_taxonomy,
        load_json(Path(args.source_registry)),
        load_json(Path(args.investment_taxonomy)),
        load_json(Path(args.ngo_taxonomy)),
    )
    result, rejected = migrate(feed, taxonomy, sources, enricher=enricher, role_taxonomy=role_taxonomy)
    Path(args.out).write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    rejected_path = Path(args.rejected)
    rejected_path.parent.mkdir(parents=True, exist_ok=True)
    rejected_payload = {
        "report_version": "1.0",
        "generated_at": result["meta"]["generated_at"],
        "rejected_count": len(rejected),
        "records": rejected,
    }
    rejected_path.write_text(json.dumps(rejected_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(result['opportunities'])} opportunities; rejected {len(rejected)}")


if __name__ == "__main__":
    main()
