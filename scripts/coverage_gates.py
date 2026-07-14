#!/usr/bin/env python3
"""Evaluate geographic/source coverage regression and Phase 5 target gates."""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def _pct(value: int, total: int) -> float:
    return value / total * 100 if total else 0.0


_LOCATION_NEUTRAL_RAW = re.compile(
    r"\b(remote|remotely|worldwide|anywhere|global|emea|africa|afrique|áfrica|afrika|"
    r"sub[ -]?saharan|pan[ -]?african|regional)\b",
    re.I,
)
_LOCATION_NEUTRAL_EVIDENCE = {
    "remote_from_kenya",
    "remote_regional_or_africa",
    "remote_global_or_worldwide",
    "international_applicants_explicitly_welcome",
}


def is_explicit_location_neutral(opportunity: dict) -> bool:
    """True for intentionally country-neutral regional/global opportunities.

    A missing country is not a data defect when the source explicitly says the
    role is remote, worldwide, EMEA-wide, Africa-wide, or region-wide. The old
    gate counted these legitimate opportunities as ``unknown country`` and
    could block publication merely because the feed gained more global roles.
    """
    location = opportunity.get("location") or {}
    if location.get("country_code"):
        return False

    scope = str(location.get("scope") or "").casefold()
    work_mode = str(opportunity.get("work_mode") or "").casefold()
    raw = str(location.get("raw") or "")
    region = location.get("region_canonical") or location.get("region")
    evidence = set((opportunity.get("eligibility") or {}).get("evidence") or [])

    if evidence & _LOCATION_NEUTRAL_EVIDENCE:
        return True
    if region and scope in {"regional", "international"}:
        return True
    if work_mode in {"remote_global", "remote_regional", "remote_kenya"}:
        return scope in {"regional", "international", "national"} or bool(_LOCATION_NEUTRAL_RAW.search(raw))
    return False




def is_official_location_pending(opportunity: dict) -> bool:
    """True for a real official vacancy whose duty station is not yet exposed.

    This is deliberately narrower than a generic missing-country exception. It
    requires a verified organisation, an official application URL, an
    institution-controlled source, and a vacancy-specific detail URL/title.
    These records remain visible as ``Location not stated`` and are monitored
    under their own capped metric rather than being silently treated as clean.
    """
    location = opportunity.get("location") or {}
    if location.get("country_code") or is_explicit_location_neutral(opportunity):
        return False
    organisation = opportunity.get("organisation") or {}
    source = opportunity.get("source") or {}
    source_kind = str(source.get("kind") or "").casefold()
    source_name = str(source.get("name") or "").casefold()
    title = str(opportunity.get("title") or "").strip()
    apply_url = str(opportunity.get("apply_url") or "").strip()
    source_url = str(source.get("url") or "").strip()
    detail_url = str(opportunity.get("raw_description_url") or apply_url).strip()
    summary = str(opportunity.get("summary") or "").strip()

    controlled_source = (
        source_kind in {"institution_official", "direct_or_official", "employer_official"}
        or source.get("confidence") == "official"
        or any(term in source_name for term in ("official career", "institutional board", "pageup", "cornerstone", "oracle candidate", "successfactors"))
    )
    vacancy_specific = bool(
        detail_url
        and (not source_url or detail_url.rstrip("/") != source_url.rstrip("/"))
        and title.casefold() not in {"career", "careers", "jobs", "vacancies", "current vacancies", "work with us"}
    )
    return bool(
        opportunity.get("apply_is_official")
        and organisation.get("verified")
        and controlled_source
        and vacancy_specific
        and len(title) >= 4
        and (summary or detail_url)
    )


def evaluate_coverage_gates(feed: dict, config: dict) -> dict:
    opportunities = feed.get("opportunities") or []
    total = len(opportunities)
    regions = Counter((row.get("location") or {}).get("region_canonical") or "unknown" for row in opportunities)
    country_buckets = []
    for row in opportunities:
        code = (row.get("location") or {}).get("country_code")
        if code:
            bucket = code
        elif is_explicit_location_neutral(row):
            bucket = "location_neutral"
        elif is_official_location_pending(row):
            bucket = "official_location_pending"
        else:
            bucket = "unknown"
        country_buckets.append(bucket)
    countries = Counter(country_buckets)
    sources = Counter((row.get("source") or {}).get("name") or "unknown" for row in opportunities)
    official = sum(1 for row in opportunities if row.get("apply_is_official"))

    errors: list[str] = []
    warnings: list[str] = []
    regression = config.get("regression_gates") or {}
    targets = config.get("phase5_targets") or {}

    for region, minimum in (regression.get("minimum_by_region") or {}).items():
        if regions.get(region, 0) < minimum:
            errors.append(f"{region} coverage {regions.get(region, 0)} is below regression floor {minimum}")
    unresolved_pct = _pct(countries.get("unknown", 0), total)
    unresolved_limit = regression.get("max_unresolved_location_percent", regression.get("max_unknown_country_percent", 100))
    if unresolved_pct > unresolved_limit:
        errors.append(f"unresolved-location share {unresolved_pct:.1f}% exceeds {unresolved_limit}%")
    pending_pct = _pct(countries.get("official_location_pending", 0), total)
    pending_limit = regression.get("max_official_location_pending_percent", 100)
    if pending_pct > pending_limit:
        errors.append(f"official-location-pending share {pending_pct:.1f}% exceeds {pending_limit}%")
    physical_countries = Counter({
        key: value for key, value in countries.items()
        if key not in {"unknown", "location_neutral", "official_location_pending"}
    })
    if physical_countries:
        country, count = physical_countries.most_common(1)[0]
        concentration = _pct(count, total)
        if concentration > regression.get("max_single_country_percent", 100):
            errors.append(f"single-country concentration {country}={concentration:.1f}% exceeds {regression['max_single_country_percent']}%")
    if sources:
        source, count = sources.most_common(1)[0]
        concentration = _pct(count, total)
        if concentration > regression.get("max_single_source_percent", 100):
            errors.append(f"single-source concentration {source}={concentration:.1f}% exceeds {regression['max_single_source_percent']}%")
    if official < regression.get("minimum_official_apply_records", 0):
        errors.append(f"official application records {official} below regression floor {regression['minimum_official_apply_records']}")

    for region, minimum in (targets.get("minimum_by_region") or {}).items():
        if regions.get(region, 0) < minimum:
            warnings.append(f"Phase 5 target: {region} has {regions.get(region, 0)} records; target is {minimum}")
    if physical_countries:
        country, count = physical_countries.most_common(1)[0]
        concentration = _pct(count, total)
        if concentration > targets.get("max_single_country_percent", 100):
            warnings.append(f"Phase 5 target: {country} concentration is {concentration:.1f}%; target maximum is {targets['max_single_country_percent']}%")
    if sources:
        source, count = sources.most_common(1)[0]
        concentration = _pct(count, total)
        if concentration > targets.get("max_single_source_percent", 100):
            warnings.append(f"Phase 5 target: {source} concentration is {concentration:.1f}%; target maximum is {targets['max_single_source_percent']}%")
    pending_target = targets.get("max_official_location_pending_percent", 100)
    if pending_pct > pending_target:
        warnings.append(
            f"Phase 5 target: official-location-pending share is {pending_pct:.1f}%; "
            f"target maximum is {pending_target}%"
        )
    official_target = targets.get("minimum_official_apply_records", 0)
    if official < official_target:
        warnings.append(f"Phase 5 target: official application records are {official}; target is {official_target}")

    return {
        "report_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "feed_generated_at": (feed.get("meta") or {}).get("generated_at"),
        "feed_version": (feed.get("meta") or {}).get("feed_version"),
        "status": "failed" if errors else "passed",
        "errors": errors,
        "warnings": warnings,
        "metrics": {
            "opportunity_count": total,
            "by_region": dict(regions),
            "by_country_code": dict(countries),
            "physical_country_records": sum(physical_countries.values()),
            "location_neutral_records": countries.get("location_neutral", 0),
            "location_neutral_percent": round(_pct(countries.get("location_neutral", 0), total), 1),
            "official_location_pending_records": countries.get("official_location_pending", 0),
            "official_location_pending_percent": round(pending_pct, 1),
            "unresolved_location_records": countries.get("unknown", 0),
            "unresolved_location_percent": round(unresolved_pct, 1),
            "by_source": dict(sources),
            "official_apply_records": official,
            "official_apply_percent": round(_pct(official, total), 1),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feed", default="feed.json")
    parser.add_argument("--config", default="config/coverage_gates.json")
    parser.add_argument("--out", default="reports/coverage_gate_report.json")
    parser.add_argument("--fail-on-errors", action="store_true")
    args = parser.parse_args()
    feed = json.loads(Path(args.feed).read_text(encoding="utf-8"))
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    report = evaluate_coverage_gates(feed, config)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for warning in report["warnings"]:
        print(f"WARN {warning}")
    for error in report["errors"]:
        print(f"ERROR {error}")
    print(f"Coverage gates: {report['status']} ({len(report['errors'])} errors, {len(report['warnings'])} target warnings)")
    if args.fail_on_errors and report["errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
