"""Coverage and source-health reporting for the Kazi Sasa feed pipeline."""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from coverage_gates import is_explicit_location_neutral, is_official_location_pending


def _percent(count: int, total: int) -> float:
    return round((count / total * 100.0), 1) if total else 0.0


def _sorted_counter(counter: Counter) -> dict[str, int]:
    return dict(sorted(counter.items(), key=lambda item: (-item[1], item[0])))


def build_coverage_report(feed: dict, validation_errors: int = 0, validation_warnings: int = 0) -> dict:
    opportunities = feed.get("opportunities", [])
    total = len(opportunities)

    by_source = Counter()
    by_confidence = Counter()
    by_org_type = Counter()
    by_opportunity_type = Counter()
    by_industry = Counter()
    by_country = Counter()
    by_scope = Counter()
    by_work_mode = Counter()
    by_role_family = Counter()
    by_thematic_sector = Counter()
    by_eligibility_status = Counter()
    by_city = Counter()
    by_region_canonical = Counter()
    by_location_language = Counter()
    by_location_confidence = Counter()
    by_admin_area = Counter()
    by_location_resolution = Counter()
    by_investment_classification = Counter()
    by_investment_track = Counter()
    by_dfi_relevance = Counter()
    by_investment_confidence = Counter()
    by_institution_type = Counter()
    by_institution_source_pack = Counter()
    by_phase7_priority = Counter()
    by_ngo_classification = Counter()
    by_ngo_track = Counter()
    by_ngo_group = Counter()
    by_phase8_priority = Counter()
    by_public_institution_category = Counter()
    by_multinational_sector = Counter()
    by_phase11_priority = Counter()
    by_africa_relevance = Counter()
    by_african_applicant_access = Counter()
    by_access_evidence_strength = Counter()
    by_certification_level = Counter()

    for opp in opportunities:
        source = opp.get("source") or {}
        org = opp.get("organisation") or {}
        location = opp.get("location") or {}
        by_source[source.get("name") or "Unknown"] += 1
        by_confidence[source.get("confidence") or "unknown"] += 1
        by_org_type[org.get("type_detail") or org.get("type") or "unknown"] += 1
        by_opportunity_type[opp.get("opportunity_type") or "unknown"] += 1
        by_industry[opp.get("industry") or "unknown"] += 1
        by_country[location.get("country_canonical") or location.get("country") or "unknown"] += 1
        by_scope[location.get("scope") or "unknown"] += 1
        by_work_mode[opp.get("work_mode") or "unknown"] += 1
        by_role_family[opp.get("role_family") or "unknown"] += 1
        by_city[location.get("city") or "unknown"] += 1
        by_region_canonical[location.get("region_canonical") or "unknown"] += 1
        by_location_language[location.get("location_language") or "unknown"] += 1
        by_admin_area[location.get("admin_area") or "unknown"] += 1
        if location.get("country_code"):
            by_location_resolution["physical_country"] += 1
        elif is_explicit_location_neutral(opp):
            by_location_resolution["location_neutral"] += 1
        elif is_official_location_pending(opp):
            by_location_resolution["official_location_pending"] += 1
        else:
            by_location_resolution["unresolved"] += 1
        confidence = location.get("normalisation_confidence")
        if isinstance(confidence, (int, float)):
            bucket = "high_0.90_plus" if confidence >= 0.9 else "medium_0.60_0.89" if confidence >= 0.6 else "low_below_0.60"
        else:
            bucket = "unknown"
        by_location_confidence[bucket] += 1
        by_eligibility_status[(opp.get("eligibility") or {}).get("status") or "unknown"] += 1
        for theme in opp.get("thematic_sectors") or []:
            by_thematic_sector[theme] += 1
        investment = opp.get("investment_profile") or {}
        by_investment_classification[investment.get("classification") or "unknown"] += 1
        by_investment_track[investment.get("track") or "none"] += 1
        by_dfi_relevance[investment.get("dfi_relevance") or "unknown"] += 1
        institution = opp.get("institution_profile") or {}
        by_institution_type[institution.get("institution_type") or "unknown"] += 1
        by_institution_source_pack[institution.get("source_pack") or "none"] += 1
        by_phase7_priority["priority" if institution.get("phase7_priority_institution") else "other"] += 1
        ngo = opp.get("ngo_profile") or {}
        by_ngo_classification[ngo.get("classification") or "unknown"] += 1
        by_ngo_track[ngo.get("track") or "none"] += 1
        by_ngo_group[ngo.get("organisation_group") or "other"] += 1
        by_phase8_priority["priority" if ngo.get("phase8_priority_organisation") else "other"] += 1
        public_profile = opp.get("public_institution_profile") or {}
        by_public_institution_category[public_profile.get("category") or "none"] += 1
        multi = opp.get("multinational_profile") or {}
        by_multinational_sector[multi.get("sector") or "none"] += 1
        by_phase11_priority["priority" if multi.get("phase11_priority_employer") else "other"] += 1
        africa_profile = opp.get("africa_relevance") or {}
        access_profile = opp.get("african_applicant_access") or {}
        by_africa_relevance[africa_profile.get("status") or "missing"] += 1
        by_african_applicant_access[access_profile.get("status") or "missing"] += 1
        by_access_evidence_strength[access_profile.get("evidence_strength") or "missing"] += 1
        by_certification_level[
            f"{africa_profile.get('certification_level') or 'missing'}|{access_profile.get('certification_level') or 'missing'}"
        ] += 1
        investment_confidence = investment.get("confidence")
        if isinstance(investment_confidence, (int, float)):
            investment_bucket = "high_0.85_plus" if investment_confidence >= 0.85 else "medium_0.65_0.84" if investment_confidence >= 0.65 else "low_below_0.65"
        else:
            investment_bucket = "unknown"
        by_investment_confidence[investment_bucket] += 1

    completeness_fields = {
        "country": lambda o: bool((o.get("location") or {}).get("country_canonical") or (o.get("location") or {}).get("country")),
        "work_mode": lambda o: bool(o.get("work_mode")),
        "industry": lambda o: bool(o.get("industry")),
        "specialisations": lambda o: bool(o.get("specialisations")),
        "seniority": lambda o: bool(o.get("seniority")),
        "years_experience": lambda o: o.get("years_experience_min") is not None,
        "education_required": lambda o: bool(o.get("education_required")),
        "contract_type_known": lambda o: o.get("contract_type") not in (None, "unknown"),
        "deadline": lambda o: bool(o.get("deadline")),
        "skills_required": lambda o: bool(o.get("skills_required")),
        "compensation": lambda o: bool(o.get("compensation")),
        "eligibility_notes": lambda o: bool(o.get("eligibility_notes")),
        "official_apply_url": lambda o: bool(o.get("apply_is_official")),
        "organisation_registry_id": lambda o: bool((o.get("organisation") or {}).get("id")),
        "country_code": lambda o: bool((o.get("location") or {}).get("country_code")),
        "city": lambda o: bool((o.get("location") or {}).get("city")),
        "role_family": lambda o: bool(o.get("role_family")),
        "thematic_sectors": lambda o: bool(o.get("thematic_sectors")),
        "eligibility_evidence": lambda o: bool((o.get("eligibility") or {}).get("evidence")),
        "meaningful_eligibility_evidence": lambda o: (o.get("african_applicant_access") or {}).get("evidence_strength") not in (None, "none"),
        "africa_relevance_profile": lambda o: bool(o.get("africa_relevance")),
        "african_applicant_access_profile": lambda o: bool(o.get("african_applicant_access")),
        "source_registry_id": lambda o: bool((o.get("source") or {}).get("id")),
        "country_iso3": lambda o: bool((o.get("location") or {}).get("country_iso3")),
        "admin_area": lambda o: bool((o.get("location") or {}).get("admin_area")),
        "coordinates": lambda o: bool((o.get("location") or {}).get("coordinates")),
        "location_evidence": lambda o: bool((o.get("location") or {}).get("normalisation_evidence")),
        "location_language": lambda o: bool((o.get("location") or {}).get("location_language")),
        "eligibility_language": lambda o: bool((o.get("eligibility") or {}).get("detected_language")),
        "investment_profile": lambda o: bool(o.get("investment_profile")),
        "investment_evidence": lambda o: bool((o.get("investment_profile") or {}).get("evidence") or (o.get("investment_profile") or {}).get("negative_evidence")),
        "institution_profile": lambda o: bool(o.get("institution_profile")),
        "institution_registry_id": lambda o: bool((o.get("institution_profile") or {}).get("registry_id")),
        "public_institution_profile": lambda o: bool(o.get("public_institution_profile")),
        "multinational_profile": lambda o: bool(o.get("multinational_profile")),
    }
    completeness = {}
    for field, predicate in completeness_fields.items():
        count = sum(1 for opp in opportunities if predicate(opp))
        completeness[field] = {"count": count, "percent": _percent(count, total)}

    return {
        "report_version": "5.0",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "feed_generated_at": (feed.get("meta") or {}).get("generated_at"),
        "feed_version": (feed.get("meta") or {}).get("feed_version"),
        "summary": {
            "opportunity_count": total,
            "source_count": len(by_source),
            "organisation_count": len({(o.get("organisation") or {}).get("name") for o in opportunities}),
            "validation_errors": validation_errors,
            "validation_warnings": validation_warnings,
            "represented_country_codes": len({(o.get("location") or {}).get("country_code") for o in opportunities if (o.get("location") or {}).get("country_code")}),
            "represented_cities": len({(o.get("location") or {}).get("city") for o in opportunities if (o.get("location") or {}).get("city")}),
            "supported_languages": (feed.get("meta") or {}).get("supported_languages", []),
            "location_registry_version": (feed.get("meta") or {}).get("location_registry_version"),
            "investment_taxonomy_version": (feed.get("meta") or {}).get("investment_taxonomy_version"),
            "investment_roles": sum(1 for o in opportunities if (o.get("investment_profile") or {}).get("is_investment_role")),
            "dfi_direct_roles": sum(1 for o in opportunities if (o.get("investment_profile") or {}).get("dfi_relevance") == "direct_investment"),
            "dfi_institutional_roles": sum(1 for o in opportunities if (o.get("investment_profile") or {}).get("dfi_relevance") == "institutional_role"),
            "dfi_or_multilateral_opportunities": sum(1 for o in opportunities if (o.get("institution_profile") or {}).get("is_dfi_or_multilateral")),
            "phase7_priority_institution_opportunities": sum(1 for o in opportunities if (o.get("institution_profile") or {}).get("phase7_priority_institution")),
            "ngo_or_un_opportunities": sum(1 for o in opportunities if (o.get("ngo_profile") or {}).get("is_ngo_or_un")),
            "phase8_priority_organisation_opportunities": sum(1 for o in opportunities if (o.get("ngo_profile") or {}).get("phase8_priority_organisation")),
            "ngo_programme_roles": sum(1 for o in opportunities if (o.get("ngo_profile") or {}).get("is_programme_role")),
            "kenya_public_institution_opportunities": sum(1 for o in opportunities if (o.get("public_institution_profile") or {}).get("is_kenya_public_institution")),
            "multinational_opportunities": sum(1 for o in opportunities if (o.get("multinational_profile") or {}).get("is_multinational")),
            "phase11_priority_employer_opportunities": sum(1 for o in opportunities if (o.get("multinational_profile") or {}).get("phase11_priority_employer")),
            "certified_default_opportunities": sum(1 for o in opportunities if (o.get("africa_relevance") or {}).get("default_visible") and (o.get("african_applicant_access") or {}).get("certification_level") in {"certified", "conditional"}),
        },
        "coverage": {
            "by_source": _sorted_counter(by_source),
            "by_source_confidence": _sorted_counter(by_confidence),
            "by_organisation_type": _sorted_counter(by_org_type),
            "by_opportunity_type": _sorted_counter(by_opportunity_type),
            "by_industry": _sorted_counter(by_industry),
            "by_country": _sorted_counter(by_country),
            "by_location_scope": _sorted_counter(by_scope),
            "by_work_mode": _sorted_counter(by_work_mode),
            "by_role_family": _sorted_counter(by_role_family),
            "by_thematic_sector": _sorted_counter(by_thematic_sector),
            "by_eligibility_status": _sorted_counter(by_eligibility_status),
            "by_city": _sorted_counter(by_city),
            "by_region_canonical": _sorted_counter(by_region_canonical),
            "by_location_language": _sorted_counter(by_location_language),
            "by_location_confidence": _sorted_counter(by_location_confidence),
            "by_admin_area": _sorted_counter(by_admin_area),
            "by_location_resolution": _sorted_counter(by_location_resolution),
            "by_investment_classification": _sorted_counter(by_investment_classification),
            "by_investment_track": _sorted_counter(by_investment_track),
            "by_dfi_relevance": _sorted_counter(by_dfi_relevance),
            "by_investment_confidence": _sorted_counter(by_investment_confidence),
            "by_institution_type": _sorted_counter(by_institution_type),
            "by_institution_source_pack": _sorted_counter(by_institution_source_pack),
            "by_phase7_priority": _sorted_counter(by_phase7_priority),
            "by_ngo_classification": _sorted_counter(by_ngo_classification),
            "by_ngo_track": _sorted_counter(by_ngo_track),
            "by_ngo_organisation_group": _sorted_counter(by_ngo_group),
            "by_phase8_priority": _sorted_counter(by_phase8_priority),
            "by_public_institution_category": _sorted_counter(by_public_institution_category),
            "by_multinational_sector": _sorted_counter(by_multinational_sector),
            "by_phase11_priority": _sorted_counter(by_phase11_priority),
            "by_africa_relevance": _sorted_counter(by_africa_relevance),
            "by_african_applicant_access": _sorted_counter(by_african_applicant_access),
            "by_access_evidence_strength": _sorted_counter(by_access_evidence_strength),
            "by_certification_level": _sorted_counter(by_certification_level),
        },
        "data_completeness": completeness,
    }


def build_investment_coverage_report(feed: dict) -> dict:
    opportunities = feed.get("opportunities", [])
    investment_roles = [row for row in opportunities if (row.get("investment_profile") or {}).get("is_investment_role")]
    institutional_roles = [row for row in opportunities if (row.get("investment_profile") or {}).get("classification") == "institutional_support"]
    by_track = Counter((row.get("investment_profile") or {}).get("track") or "none" for row in investment_roles)
    by_country = Counter(((row.get("location") or {}).get("country_canonical") or (row.get("location") or {}).get("country") or "unknown") for row in investment_roles)
    by_source = Counter(((row.get("source") or {}).get("name") or "Unknown") for row in investment_roles)
    by_org_type = Counter(((row.get("organisation") or {}).get("type_detail") or (row.get("organisation") or {}).get("type") or "unknown") for row in investment_roles)
    by_classification = Counter((row.get("investment_profile") or {}).get("classification") or "unknown" for row in opportunities)
    by_dfi = Counter((row.get("investment_profile") or {}).get("dfi_relevance") or "unknown" for row in opportunities)
    false_positive_guarded = sum(1 for row in opportunities if (row.get("investment_profile") or {}).get("negative_evidence"))
    return {
        "report_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "feed_generated_at": (feed.get("meta") or {}).get("generated_at"),
        "feed_version": (feed.get("meta") or {}).get("feed_version"),
        "summary": {
            "opportunity_count": len(opportunities),
            "investment_role_count": len(investment_roles),
            "institutional_support_role_count": len(institutional_roles),
            "investment_role_percent": _percent(len(investment_roles), len(opportunities)),
            "direct_dfi_investment_count": by_dfi.get("direct_investment", 0),
            "dfi_institutional_role_count": by_dfi.get("institutional_role", 0),
            "false_positive_guarded_count": false_positive_guarded,
            "represented_investment_tracks": len([key for key, value in by_track.items() if key != "none" and value]),
        },
        "coverage": {
            "by_classification": _sorted_counter(by_classification),
            "by_track": _sorted_counter(by_track),
            "by_dfi_relevance": _sorted_counter(by_dfi),
            "by_country": _sorted_counter(by_country),
            "by_source": _sorted_counter(by_source),
            "by_organisation_type": _sorted_counter(by_org_type),
        },
    }



def build_dfi_coverage_report(feed: dict) -> dict:
    """Summarise Phase 7 DFI/multilateral institution and role coverage."""
    opportunities = feed.get("opportunities", [])
    institution_rows = [
        row for row in opportunities
        if (row.get("institution_profile") or {}).get("is_dfi_or_multilateral")
    ]
    priority_rows = [
        row for row in opportunities
        if (row.get("institution_profile") or {}).get("phase7_priority_institution")
    ]
    investment_rows = [
        row for row in institution_rows
        if (row.get("investment_profile") or {}).get("is_investment_role")
    ]
    by_institution = Counter(
        (row.get("organisation") or {}).get("name") or "Unknown" for row in institution_rows
    )
    by_type = Counter(
        (row.get("institution_profile") or {}).get("institution_type") or "unknown"
        for row in institution_rows
    )
    by_country = Counter(
        (row.get("location") or {}).get("country_canonical")
        or (row.get("location") or {}).get("country")
        or "unknown"
        for row in institution_rows
    )
    by_source = Counter(
        (row.get("source") or {}).get("name") or "Unknown" for row in institution_rows
    )
    by_role_family = Counter(row.get("role_family") or "unknown" for row in institution_rows)
    by_dfi_relevance = Counter(
        (row.get("investment_profile") or {}).get("dfi_relevance") or "unknown"
        for row in institution_rows
    )
    by_track = Counter(
        (row.get("investment_profile") or {}).get("track") or "none"
        for row in investment_rows
    )
    official = sum(1 for row in institution_rows if row.get("apply_is_official"))
    return {
        "report_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "feed_generated_at": (feed.get("meta") or {}).get("generated_at"),
        "feed_version": (feed.get("meta") or {}).get("feed_version"),
        "summary": {
            "opportunity_count": len(opportunities),
            "dfi_or_multilateral_opportunity_count": len(institution_rows),
            "phase7_priority_institution_opportunity_count": len(priority_rows),
            "dfi_investment_role_count": len(investment_rows),
            "represented_institutions": len(by_institution),
            "represented_countries": len([key for key in by_country if key != "unknown"]),
            "official_application_count": official,
            "official_application_percent": _percent(official, len(institution_rows)),
        },
        "coverage": {
            "by_institution": _sorted_counter(by_institution),
            "by_institution_type": _sorted_counter(by_type),
            "by_country": _sorted_counter(by_country),
            "by_source": _sorted_counter(by_source),
            "by_role_family": _sorted_counter(by_role_family),
            "by_dfi_relevance": _sorted_counter(by_dfi_relevance),
            "by_investment_track": _sorted_counter(by_track),
        },
    }

def build_source_health_report(
    per_source_counts: dict[str, int],
    statuses: dict[str, dict[str, Any]],
    configured_counts: dict[str, int] | None = None,
) -> dict:
    configured_counts = configured_counts or {}
    names = sorted(set(per_source_counts) | set(statuses) | set(configured_counts))
    sources = []
    for name in names:
        status_data = statuses.get(name, {})
        count = int(per_source_counts.get(name, 0))
        status = status_data.get("status")
        if not status:
            status = "collected" if count > 0 else "empty"
        row = {
            "source": name,
            "status": status,
            "accepted": count,
            "configured_targets": int(configured_counts.get(name, 0)),
        }
        for key in (
            "reason", "error", "duration_ms", "returned_count", "added_delta",
            "source_kind", "schedule_class", "freshness_hours", "timeout_seconds",
            "missing_env", "count_mismatch", "rolled_back_partial",
        ):
            if key in status_data:
                row[key] = status_data[key]
        sources.append(row)

    return {
        "report_version": "2.0",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "sources": sources,
        "summary": {
            "source_count": len(sources),
            "collected": sum(1 for row in sources if row["status"] == "collected"),
            "empty": sum(1 for row in sources if row["status"] == "empty"),
            "skipped": sum(1 for row in sources if row["status"].startswith("skipped")),
            "errors": sum(1 for row in sources if row["status"] == "error"),
            "accepted_total": sum(row["accepted"] for row in sources),
        },
    }


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def build_ngo_coverage_report(feed: dict) -> dict:
    opportunities = feed.get("opportunities", [])
    institution_rows = [r for r in opportunities if (r.get("ngo_profile") or {}).get("is_ngo_or_un")]
    priority_rows = [r for r in opportunities if (r.get("ngo_profile") or {}).get("phase8_priority_organisation")]
    programme_rows = [r for r in opportunities if (r.get("ngo_profile") or {}).get("is_programme_role")]
    by_org = Counter((r.get("organisation") or {}).get("name") or "Unknown" for r in institution_rows)
    by_group = Counter((r.get("ngo_profile") or {}).get("organisation_group") or "unknown" for r in institution_rows)
    by_class = Counter((r.get("ngo_profile") or {}).get("classification") or "unknown" for r in opportunities)
    by_track = Counter((r.get("ngo_profile") or {}).get("track") or "none" for r in programme_rows)
    by_country = Counter((r.get("location") or {}).get("country_canonical") or (r.get("location") or {}).get("country") or "unknown" for r in institution_rows)
    by_source = Counter((r.get("source") or {}).get("name") or "Unknown" for r in institution_rows)
    by_role = Counter(r.get("role_family") or "unknown" for r in institution_rows)
    official = sum(1 for r in institution_rows if r.get("apply_is_official"))
    return {
        "report_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "feed_generated_at": (feed.get("meta") or {}).get("generated_at"),
        "feed_version": (feed.get("meta") or {}).get("feed_version"),
        "summary": {
            "opportunity_count": len(opportunities),
            "ngo_or_un_opportunity_count": len(institution_rows),
            "phase8_priority_opportunity_count": len(priority_rows),
            "programme_role_count": len(programme_rows),
            "represented_organisations": len(by_org),
            "represented_countries": len([k for k in by_country if k != "unknown"]),
            "official_application_count": official,
            "official_application_percent": _percent(official, len(institution_rows)),
        },
        "coverage": {
            "by_organisation": _sorted_counter(by_org),
            "by_organisation_group": _sorted_counter(by_group),
            "by_classification": _sorted_counter(by_class),
            "by_track": _sorted_counter(by_track),
            "by_country": _sorted_counter(by_country),
            "by_source": _sorted_counter(by_source),
            "by_role_family": _sorted_counter(by_role),
        },
    }


def build_government_coverage_report(feed: dict) -> dict:
    opportunities = feed.get("opportunities", [])
    rows = [r for r in opportunities if (r.get("government_profile") or {}).get("is_government_or_public_service")]
    priority = [r for r in rows if (r.get("government_profile") or {}).get("phase9_priority_portal")]
    by_country = Counter((r.get("location") or {}).get("country_canonical") or (r.get("location") or {}).get("country") or "unknown" for r in rows)
    by_portal = Counter((r.get("organisation") or {}).get("name") or "Unknown" for r in rows)
    by_grade = Counter((r.get("government_profile") or {}).get("public_service_grade") or "unknown" for r in rows)
    by_role = Counter(r.get("role_family") or "unknown" for r in rows)
    with_reference = sum(1 for r in rows if (r.get("government_profile") or {}).get("advert_reference"))
    with_deadline = sum(1 for r in rows if r.get("deadline"))
    with_positions = sum(1 for r in rows if (r.get("government_profile") or {}).get("number_of_positions"))
    return {
        "report_version": "1.0",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "feed_generated_at": (feed.get("meta") or {}).get("generated_at"),
        "feed_version": (feed.get("meta") or {}).get("feed_version"),
        "summary": {
            "opportunity_count": len(opportunities),
            "government_opportunity_count": len(rows),
            "phase9_priority_opportunity_count": len(priority),
            "represented_portals": len(by_portal),
            "represented_countries": len([k for k in by_country if k != "unknown"]),
            "with_advert_reference_count": with_reference,
            "with_deadline_count": with_deadline,
            "with_number_of_positions_count": with_positions,
        },
        "coverage": {
            "by_country": _sorted_counter(by_country),
            "by_portal": _sorted_counter(by_portal),
            "by_public_service_grade": _sorted_counter(by_grade),
            "by_role_family": _sorted_counter(by_role),
        },
    }


def build_public_institution_coverage_report(feed: dict, registry: dict | None = None) -> dict:
    opportunities = feed.get("opportunities", [])
    rows = [r for r in opportunities if (r.get("public_institution_profile") or {}).get("is_kenya_public_institution")]
    by_category = Counter((r.get("public_institution_profile") or {}).get("category") or "unknown" for r in rows)
    by_org = Counter((r.get("organisation") or {}).get("name") or "Unknown" for r in rows)
    by_role = Counter(r.get("role_family") or "unknown" for r in rows)
    by_city = Counter((r.get("location") or {}).get("city") or "unknown" for r in rows)
    configured = (registry or {}).get("institutions", [])
    enabled = [r for r in configured if r.get("enabled")]
    return {
        "report_version":"1.0",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00","Z"),
        "feed_generated_at": (feed.get("meta") or {}).get("generated_at"),
        "feed_version": (feed.get("meta") or {}).get("feed_version"),
        "summary": {
            "configured_institution_count": len(configured),
            "enabled_institution_count": len(enabled),
            "opportunity_count": len(rows),
            "represented_institutions": len(by_org),
            "represented_categories": len([k for k in by_category if k != "unknown"]),
        },
        "coverage": {
            "by_category": _sorted_counter(by_category),
            "by_institution": _sorted_counter(by_org),
            "by_role_family": _sorted_counter(by_role),
            "by_city": _sorted_counter(by_city),
        },
    }


def build_multinational_coverage_report(feed: dict, registry: dict | None = None) -> dict:
    opportunities = feed.get("opportunities", [])
    rows = [r for r in opportunities if (r.get("multinational_profile") or {}).get("is_multinational")]
    priority = [r for r in rows if (r.get("multinational_profile") or {}).get("phase11_priority_employer")]
    by_sector = Counter((r.get("multinational_profile") or {}).get("sector") or "unknown" for r in rows)
    by_org = Counter((r.get("organisation") or {}).get("name") or "Unknown" for r in rows)
    by_country = Counter((r.get("location") or {}).get("country_canonical") or (r.get("location") or {}).get("country") or "unknown" for r in rows)
    by_city = Counter((r.get("location") or {}).get("city") or "unknown" for r in rows)
    by_role = Counter(r.get("role_family") or "unknown" for r in rows)
    by_source = Counter((r.get("source") or {}).get("name") or "Unknown" for r in rows)
    configured = (registry or {}).get("employers", [])
    enabled = [r for r in configured if r.get("enabled")]
    registry_city = Counter(city for employer in configured for city in employer.get("cities", []))
    registry_sector = Counter(employer.get("sector") or "unknown" for employer in configured)
    official = sum(1 for r in rows if r.get("apply_is_official"))
    return {
        "report_version":"1.0",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00","Z"),
        "feed_generated_at": (feed.get("meta") or {}).get("generated_at"),
        "feed_version": (feed.get("meta") or {}).get("feed_version"),
        "summary": {
            "configured_employer_count": len(configured),
            "enabled_employer_count": len(enabled),
            "multinational_opportunity_count": len(rows),
            "phase11_priority_opportunity_count": len(priority),
            "represented_employers": len(by_org),
            "represented_countries": len([k for k in by_country if k != "unknown"]),
            "represented_cities": len([k for k in by_city if k != "unknown"]),
            "official_application_count": official,
            "official_application_percent": _percent(official, len(rows)),
        },
        "coverage": {
            "by_sector": _sorted_counter(by_sector),
            "by_employer": _sorted_counter(by_org),
            "by_country": _sorted_counter(by_country),
            "by_city": _sorted_counter(by_city),
            "by_role_family": _sorted_counter(by_role),
            "by_source": _sorted_counter(by_source),
            "registry_city_footprint": _sorted_counter(registry_city),
            "registry_sector_footprint": _sorted_counter(registry_sector),
        },
    }
