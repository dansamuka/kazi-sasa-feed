#!/usr/bin/env python3
"""Africa relevance and African-applicant access certification gates."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CERTIFIED_RELEVANCE = {
    "africa_based_confirmed",
    "africa_regional",
    "remote_confirmed_open_to_africa",
    "africa_remit_non_african_location",
}
CERTIFIED_OR_CONDITIONAL_ACCESS = {
    "confirmed_any_african_national",
    "confirmed_specific_african_nationality",
    "confirmed_international_recruitment",
    "likely_open",
    "work_authorisation_required",
    "local_only",
}
EXCLUDED_ACCESS = {"not_open", "internal_only"}


def is_certified_default(row: dict[str, Any]) -> bool:
    relevance = (row.get("africa_relevance") or {}).get("status")
    access = (row.get("african_applicant_access") or {}).get("status")
    return relevance in CERTIFIED_RELEVANCE and access in CERTIFIED_OR_CONDITIONAL_ACCESS and access not in EXCLUDED_ACCESS


def build_certified_feed(feed: dict[str, Any]) -> dict[str, Any]:
    rows = [row for row in feed.get("opportunities", []) if is_certified_default(row)]
    meta = dict(feed.get("meta") or {})
    meta.update({
        "opportunity_count": len(rows),
        "source_count": len({(row.get("source") or {}).get("name") for row in rows if (row.get("source") or {}).get("name")}),
        "certified_subset": True,
        "parent_opportunity_count": len(feed.get("opportunities", [])),
    })
    return {"meta": meta, "opportunities": rows}


def evaluate(feed: dict[str, Any], deduplication_report: dict[str, Any] | None = None) -> dict[str, Any]:
    rows = feed.get("opportunities", [])
    deduplication_report = deduplication_report or {}
    errors: list[str] = []
    warnings: list[str] = []

    by_relevance = Counter((row.get("africa_relevance") or {}).get("status") or "missing" for row in rows)
    by_access = Counter((row.get("african_applicant_access") or {}).get("status") or "missing" for row in rows)
    by_strength = Counter((row.get("african_applicant_access") or {}).get("evidence_strength") or "missing" for row in rows)
    default_rows = [row for row in rows if is_certified_default(row)]

    missing_profiles = [row.get("id") for row in rows if not row.get("africa_relevance") or not row.get("african_applicant_access")]
    if missing_profiles:
        errors.append(f"{len(missing_profiles)} opportunities are missing Africa/access certification profiles")

    non_african = [row for row in rows if (row.get("africa_relevance") or {}).get("status") == "non_african"]
    if non_african:
        errors.append(f"{len(non_african)} known non-African roles without an Africa remit were published")

    bad_default = [row for row in default_rows if (row.get("africa_relevance") or {}).get("status") not in CERTIFIED_RELEVANCE]
    if bad_default:
        errors.append(f"{len(bad_default)} default-visible rows lack certified Africa relevance")

    weak_likely = [
        row for row in rows
        if (row.get("african_applicant_access") or {}).get("status") == "likely_open"
        and (row.get("african_applicant_access") or {}).get("evidence_strength") not in {"explicit", "structured_source", "strong_inference"}
    ]
    if weak_likely:
        errors.append(f"{len(weak_likely)} likely-open roles lack strong evidence")

    missing_structured_nationality = []
    for row in rows:
        government = row.get("government_profile") or {}
        if government.get("citizenship_required") is True and not government.get("eligible_nationalities"):
            missing_structured_nationality.append(row.get("id"))
    if missing_structured_nationality:
        errors.append(
            f"{len(missing_structured_nationality)} citizenship-restricted government roles lack nationality codes"
        )

    government_loss = float(deduplication_report.get("government_loss_percent") or 0.0)
    if government_loss > 5.0:
        errors.append(f"government deduplication loss is {government_loss:.1f}%; maximum is 5%")

    pending = by_relevance.get("official_location_pending", 0)
    unresolved = by_relevance.get("unresolved", 0)
    total = len(rows) or 1
    pending_pct = round(pending / total * 100, 1)
    unresolved_pct = round(unresolved / total * 100, 1)
    if pending_pct > 10.0:
        warnings.append(f"broad index official-location-pending share is {pending_pct:.1f}%; certified default hides these rows")
    if unresolved_pct > 2.0:
        warnings.append(f"broad index unresolved-location share is {unresolved_pct:.1f}%; certified default hides these rows")
    if not default_rows:
        if (feed.get("meta") or {}).get("live_refresh_completed") and rows:
            errors.append("live refresh produced no certified or conditional African-access opportunities")
        else:
            warnings.append("certified default subset is empty")

    return {
        "report_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "feed_generated_at": (feed.get("meta") or {}).get("generated_at"),
        "feed_version": (feed.get("meta") or {}).get("feed_version"),
        "status": "passed" if not errors else "failed",
        "errors": errors,
        "warnings": warnings,
        "summary": {
            "broad_index_count": len(rows),
            "certified_default_count": len(default_rows),
            "certified_default_percent": round(len(default_rows) / total * 100, 1),
            "known_non_african_published": len(non_african),
            "official_location_pending_percent": pending_pct,
            "unresolved_location_percent": unresolved_pct,
            "government_deduplication_loss_percent": government_loss,
        },
        "coverage": {
            "by_africa_relevance": dict(by_relevance.most_common()),
            "by_african_applicant_access": dict(by_access.most_common()),
            "by_evidence_strength": dict(by_strength.most_common()),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--feed", default="feed.json")
    parser.add_argument("--deduplication-report", default="reports/deduplication_report.json")
    parser.add_argument("--out", default="reports/africa_eligibility_certification_report.json")
    parser.add_argument("--certified-feed", default="certified_feed.json")
    parser.add_argument("--fail-on-errors", action="store_true")
    args = parser.parse_args()
    feed = json.loads(Path(args.feed).read_text(encoding="utf-8"))
    dedup_path = Path(args.deduplication_report)
    dedup = json.loads(dedup_path.read_text(encoding="utf-8")) if dedup_path.exists() else {}
    report = evaluate(feed, dedup)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    Path(args.certified_feed).write_text(json.dumps(build_certified_feed(feed), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for warning in report["warnings"]:
        print(f"WARN certification: {warning}")
    for error in report["errors"]:
        print(f"ERROR certification: {error}")
    if args.fail_on_errors and report["errors"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
