#!/usr/bin/env python3
"""Verify that the repository-root feed and generated site are the current additive schema outputs.

This deployment guard exists because a workflow can successfully run a collector while
writing to a path that Git does not stage. The guard validates the exact root artifacts
that will be committed and published.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


PHASE2_REQUIRED_OPPORTUNITY_FIELDS = {
    "role_family",
    "role_subfamily",
    "thematic_sectors",
    "eligibility",
}
PHASE2_REQUIRED_LOCATION_FIELDS = {
    "city",
    "country_code",
    "country_canonical",
    "region_canonical",
    "normalisation_confidence",
}
PHASE2_REQUIRED_ORGANISATION_FIELDS = {
    "id",
    "type_detail",
    "registry_managed",
}
PHASE2_REQUIRED_SOURCE_FIELDS = {
    "id",
    "kind",
    "registry_managed",
}
PHASE2_REQUIRED_ELIGIBILITY_FIELDS = {
    "status",
    "confidence",
    "citizenship_required",
    "eligible_nationalities",
    "work_authorisation_required",
    "evidence",
}

PHASE4_REQUIRED_LOCATION_FIELDS = {
    "country_iso3",
    "admin_area",
    "coordinates",
    "normalisation_evidence",
    "matched_location_alias",
    "location_language",
    "is_african",
}
PHASE4_REQUIRED_ELIGIBILITY_FIELDS = {"detected_language"}
PHASE5_REQUIRED_META_FIELDS = {
    "source_expansion_version": "1.0",
    "deduplication_version": "2.0",
}
PHASE6_REQUIRED_META_FIELDS = {
    "investment_taxonomy_version": "1.0",
    "investment_classifier_version": "1.0",
}
PHASE7_REQUIRED_META_FIELDS = {
    "dfi_source_pack_version": "1.0",
}
PHASE8_REQUIRED_META_FIELDS = {
    "enterprise_adapter_version": "1.1",
    "ngo_source_pack_version": "1.0",
    "ngo_taxonomy_version": "1.0",
    "ngo_classifier_version": "1.1",
    "official_vacancy_quality_version": "1.1",
}
PHASE7_REQUIRED_PROFILE_FIELDS = {
    "is_dfi_or_multilateral", "institution_type", "registry_id",
    "source_pack", "phase7_priority_institution",
}


PHASE9_REQUIRED_META_FIELDS = {
    "government_source_pack_version": "1.0",
    "government_schema_version": "1.0",
}
PHASE9_REQUIRED_PROFILE_FIELDS = {
    "is_government_or_public_service", "institution_type", "registry_id",
    "source_pack", "phase9_priority_portal", "advert_reference",
    "public_service_grade", "salary_scale", "number_of_positions",
    "citizenship_required", "eligible_nationalities", "application_method",
    "application_form_url", "internal_only", "county_or_region_requirement",
    "source_document_url",
}


PHASE11_REQUIRED_META_FIELDS = {
    "kenya_public_institutions_version": "1.0",
    "multinational_source_pack_version": "1.0",
    "multinational_adapter_version": "1.0",
}
PHASE11_REQUIRED_PUBLIC_PROFILE_FIELDS = {
    "is_kenya_public_institution", "category", "registry_id", "source_pack", "country_code",
}
PHASE11_REQUIRED_MULTINATIONAL_PROFILE_FIELDS = {
    "is_multinational", "sector", "registry_id", "source_pack",
    "phase11_priority_employer", "african_city_footprint",
}

PHASE12_REQUIRED_META_FIELDS = {
    "africa_access_certification_version": "1.0",
    "government_deduplication_version": "3.0",
    "eligibility_evidence_version": "2.0",
}
PHASE12_REQUIRED_AFRICA_FIELDS = {
    "status", "confidence", "evidence", "certification_level",
    "default_visible", "known_country_code", "known_country_name",
}
PHASE12_REQUIRED_ACCESS_FIELDS = {
    "status", "confidence", "evidence", "evidence_strength",
    "eligible_nationalities", "citizenship_required",
    "work_authorisation_required", "certification_level",
}

PHASE8_REQUIRED_PROFILE_FIELDS = {
    "is_ngo_or_un", "organisation_group", "classification", "track",
    "canonical_specialisation", "confidence", "evidence", "negative_evidence",
    "is_programme_role", "registry_id", "source_pack", "phase8_priority_organisation",
}

PHASE6_REQUIRED_PROFILE_FIELDS = {
    "classification", "track", "canonical_specialisation", "confidence",
    "evidence", "negative_evidence", "dfi_relevance", "dfi_confidence",
    "is_investment_role",
}


def parse_timestamp(value: str) -> datetime:
    if not value:
        raise ValueError("meta.generated_at is missing")
    normalised = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalised)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def verify_feed(
    feed: dict, expected_version: str, require_phase2: bool, max_age_minutes: int | None,
    require_phase4: bool = False,
    require_phase5: bool = False,
    require_phase6: bool = False,
    require_phase7: bool = False,
    require_phase8: bool = False,
    require_phase9: bool = False,
    require_phase11: bool = False,
    require_phase12: bool = False,
) -> list[str]:
    errors: list[str] = []
    meta = feed.get("meta") or {}
    opportunities = feed.get("opportunities")

    if meta.get("feed_version") != expected_version:
        errors.append(
            f"root feed version is {meta.get('feed_version')!r}; expected {expected_version!r}"
        )
    if not isinstance(opportunities, list) or not opportunities:
        errors.append("root feed has no opportunities")
        opportunities = []
    if meta.get("opportunity_count") != len(opportunities):
        errors.append(
            "meta.opportunity_count does not match the number of opportunities "
            f"({meta.get('opportunity_count')!r} != {len(opportunities)})"
        )

    try:
        generated_at = parse_timestamp(str(meta.get("generated_at") or ""))
    except (TypeError, ValueError) as exc:
        errors.append(str(exc))
    else:
        if max_age_minutes is not None:
            age_minutes = (datetime.now(timezone.utc) - generated_at).total_seconds() / 60
            if age_minutes < -5:
                errors.append(f"meta.generated_at is {abs(age_minutes):.1f} minutes in the future")
            elif age_minutes > max_age_minutes:
                errors.append(
                    f"root feed is stale: generated {age_minutes:.1f} minutes ago; "
                    f"maximum allowed age is {max_age_minutes} minutes"
                )

    if require_phase2:
        for index, opportunity in enumerate(opportunities):
            missing = PHASE2_REQUIRED_OPPORTUNITY_FIELDS - set(opportunity)
            if missing:
                errors.append(f"opportunities[{index}] missing Phase 2 fields: {sorted(missing)}")

            organisation = opportunity.get("organisation") or {}
            missing = PHASE2_REQUIRED_ORGANISATION_FIELDS - set(organisation)
            if missing:
                errors.append(
                    f"opportunities[{index}].organisation missing Phase 2 fields: {sorted(missing)}"
                )

            location = opportunity.get("location") or {}
            missing = PHASE2_REQUIRED_LOCATION_FIELDS - set(location)
            if missing:
                errors.append(
                    f"opportunities[{index}].location missing Phase 2 fields: {sorted(missing)}"
                )

            source = opportunity.get("source") or {}
            missing = PHASE2_REQUIRED_SOURCE_FIELDS - set(source)
            if missing:
                errors.append(
                    f"opportunities[{index}].source missing Phase 2 fields: {sorted(missing)}"
                )

            eligibility = opportunity.get("eligibility") or {}
            missing = PHASE2_REQUIRED_ELIGIBILITY_FIELDS - set(eligibility)
            if missing:
                errors.append(
                    f"opportunities[{index}].eligibility missing Phase 2 fields: {sorted(missing)}"
                )

            if len(errors) >= 25:
                errors.append("additional Phase 2 field errors omitted")
                break

    if require_phase4:
        if set(meta.get("supported_languages", [])) != {"en", "fr", "pt", "ar", "sw"}:
            errors.append("root feed meta.supported_languages must contain en/fr/pt/ar/sw")
        if meta.get("location_registry_version") != "2.0":
            errors.append("root feed meta.location_registry_version must be 2.0")
        for index, opportunity in enumerate(opportunities):
            location = opportunity.get("location") or {}
            missing = PHASE4_REQUIRED_LOCATION_FIELDS - set(location)
            if missing:
                errors.append(f"opportunities[{index}].location missing Phase 4 fields: {sorted(missing)}")
            eligibility = opportunity.get("eligibility") or {}
            missing = PHASE4_REQUIRED_ELIGIBILITY_FIELDS - set(eligibility)
            if missing:
                errors.append(f"opportunities[{index}].eligibility missing Phase 4 fields: {sorted(missing)}")
            if len(errors) >= 25:
                errors.append("additional Phase 4 field errors omitted")
                break

    if require_phase5:
        for field, expected in PHASE5_REQUIRED_META_FIELDS.items():
            if meta.get(field) != expected:
                errors.append(f"root feed meta.{field} must be {expected!r}")

    if require_phase6:
        for field, expected in PHASE6_REQUIRED_META_FIELDS.items():
            if meta.get(field) != expected:
                errors.append(f"root feed meta.{field} must be {expected!r}")
        for index, opportunity in enumerate(opportunities):
            profile = opportunity.get("investment_profile") or {}
            missing = PHASE6_REQUIRED_PROFILE_FIELDS - set(profile)
            if missing:
                errors.append(f"opportunities[{index}].investment_profile missing Phase 6 fields: {sorted(missing)}")
            if len(errors) >= 25:
                errors.append("additional Phase 6 field errors omitted")
                break

    if require_phase7:
        for field, expected in PHASE7_REQUIRED_META_FIELDS.items():
            if meta.get(field) != expected:
                errors.append(f"root feed meta.{field} must be {expected!r}")
        for index, opportunity in enumerate(opportunities):
            profile = opportunity.get("institution_profile") or {}
            missing = PHASE7_REQUIRED_PROFILE_FIELDS - set(profile)
            if missing:
                errors.append(f"opportunities[{index}].institution_profile missing Phase 7 fields: {sorted(missing)}")
            if len(errors) >= 25:
                errors.append("additional Phase 7 field errors omitted")
                break

    if require_phase8:
        for field, expected in PHASE8_REQUIRED_META_FIELDS.items():
            if meta.get(field) != expected:
                errors.append(f"root feed meta.{field} must be {expected!r}")
        for index, opportunity in enumerate(opportunities):
            profile = opportunity.get("ngo_profile") or {}
            missing = PHASE8_REQUIRED_PROFILE_FIELDS - set(profile)
            if missing:
                errors.append(f"opportunities[{index}].ngo_profile missing Phase 8 fields: {sorted(missing)}")
            if len(errors) >= 25:
                errors.append("additional Phase 8 field errors omitted")
                break

    if require_phase9:
        for field, expected in PHASE9_REQUIRED_META_FIELDS.items():
            if meta.get(field) != expected:
                errors.append(f"root feed meta.{field} must be {expected!r}")
        for index, opportunity in enumerate(opportunities):
            profile = opportunity.get("government_profile") or {}
            missing = PHASE9_REQUIRED_PROFILE_FIELDS - set(profile)
            if missing:
                errors.append(f"opportunities[{index}].government_profile missing Phase 9 fields: {sorted(missing)}")
            if len(errors) >= 25:
                errors.append("additional Phase 9 field errors omitted")
                break


    if require_phase11:
        for field, expected in PHASE11_REQUIRED_META_FIELDS.items():
            if meta.get(field) != expected:
                errors.append(f"root feed meta.{field} must be {expected!r}")
        for index, opportunity in enumerate(opportunities):
            public_profile = opportunity.get("public_institution_profile") or {}
            missing_public = PHASE11_REQUIRED_PUBLIC_PROFILE_FIELDS - set(public_profile)
            if missing_public:
                errors.append(f"opportunities[{index}].public_institution_profile missing Phase 11 fields: {sorted(missing_public)}")
            multinational_profile = opportunity.get("multinational_profile") or {}
            missing_multinational = PHASE11_REQUIRED_MULTINATIONAL_PROFILE_FIELDS - set(multinational_profile)
            if missing_multinational:
                errors.append(f"opportunities[{index}].multinational_profile missing Phase 11 fields: {sorted(missing_multinational)}")
            if len(errors) >= 25:
                errors.append("additional Phase 11 field errors omitted")
                break

    if require_phase12:
        for field, expected in PHASE12_REQUIRED_META_FIELDS.items():
            if meta.get(field) != expected:
                errors.append(f"root feed meta.{field} must be {expected!r}")
        for index, opportunity in enumerate(opportunities):
            relevance = opportunity.get("africa_relevance") or {}
            missing_relevance = PHASE12_REQUIRED_AFRICA_FIELDS - set(relevance)
            if missing_relevance:
                errors.append(f"opportunities[{index}].africa_relevance missing Phase 12 fields: {sorted(missing_relevance)}")
            access = opportunity.get("african_applicant_access") or {}
            missing_access = PHASE12_REQUIRED_ACCESS_FIELDS - set(access)
            if missing_access:
                errors.append(f"opportunities[{index}].african_applicant_access missing Phase 12 fields: {sorted(missing_access)}")
            if len(errors) >= 25:
                errors.append("additional Phase 12 field errors omitted")
                break

    return errors


PHASE3_SITE_MARKERS = {
    'countryPill', 'cityPill', 'roleFamilyPill', 'orgTypePill', 'eligibilityPill',
    '"role_family"', '"org_type"', '"eligibility_confidence"',
}
PHASE7_SITE_MARKERS = {
    'dfiInstitutionPill', 'dfiRelevancePill', '"is_dfi_or_multilateral"',
    '"phase7_priority_institution"', '"institution_type"',
}
PHASE8_SITE_MARKERS = {
    'ngoInstitutionPill', 'ngoTrackPill', '"is_ngo_or_un"',
    '"phase8_priority_organisation"', '"ngo_classification"', '"ngo_track"',
}
PHASE9_SITE_MARKERS = {
    'governmentPill', 'governmentGradePill', '"is_government_or_public_service"',
    '"phase9_priority_portal"', '"public_service_grade"',
}
PHASE11_SITE_MARKERS = {
    'publicInstitutionPill', 'publicInstitutionCategoryPill',
    'multinationalPill', 'multinationalSectorPill',
    '"is_kenya_public_institution"', '"public_institution_category"',
    '"is_multinational"', '"multinational_sector"', '"phase11_priority_employer"',
}
PHASE12_SITE_MARKERS = {
    'africaRelevancePill', 'africanAccessPill', 'certificationScopePill',
    '"africa_relevance"', '"african_applicant_access"', '"certified_default_view"',
}
PHASE6_SITE_MARKERS = {
    'investmentClassPill', 'investmentTrackPill', '"investment_track"', '"dfi_relevance"',
    '"investment_classification"',
}


def verify_site(site_html: str, feed: dict, require_phase3: bool = False, require_phase6: bool = False, require_phase7: bool = False, require_phase8: bool = False, require_phase9: bool = False, require_phase11: bool = False, require_phase12: bool = False) -> list[str]:
    errors: list[str] = []
    meta = feed.get("meta") or {}
    generated_at = str(meta.get("generated_at") or "")
    opportunity_count = str(meta.get("opportunity_count") or "")
    feed_version = str(meta.get("feed_version") or "")

    for label, value in {
        "generated_at": generated_at,
        "opportunity_count": opportunity_count,
        "feed_version": feed_version,
    }.items():
        if value and value not in site_html:
            errors.append(f"generated site does not contain the current feed {label} value {value!r}")
    if require_phase3:
        missing = sorted(marker for marker in PHASE3_SITE_MARKERS if marker not in site_html)
        if missing:
            errors.append(f"generated site is missing Phase 3 filters/payload markers: {missing}")
    if require_phase6:
        missing = sorted(marker for marker in PHASE6_SITE_MARKERS if marker not in site_html)
        if missing:
            errors.append(f"generated site is missing Phase 6 investment markers: {missing}")
    if require_phase7:
        missing = sorted(marker for marker in PHASE7_SITE_MARKERS if marker not in site_html)
        if missing:
            errors.append(f"generated site is missing Phase 7 DFI markers: {missing}")
    if require_phase8:
        missing = sorted(marker for marker in PHASE8_SITE_MARKERS if marker not in site_html)
        if missing:
            errors.append(f"generated site is missing Phase 8 NGO/UN markers: {missing}")
    if require_phase9:
        missing = sorted(marker for marker in PHASE9_SITE_MARKERS if marker not in site_html)
        if missing:
            errors.append(f"generated site is missing Phase 9 government markers: {missing}")
    if require_phase11:
        missing = sorted(marker for marker in PHASE11_SITE_MARKERS if marker not in site_html)
        if missing:
            errors.append(f"generated site is missing Phase 11 public-institution/multinational markers: {missing}")
    if require_phase12:
        missing = sorted(marker for marker in PHASE12_SITE_MARKERS if marker not in site_html)
        if missing:
            errors.append(f"generated site is missing Phase 12 certification markers: {missing}")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feed", default="feed.json")
    parser.add_argument("--site", default=None)
    parser.add_argument("--expected-version", default="3.8")
    parser.add_argument("--require-phase2", action="store_true")
    parser.add_argument("--require-phase4", action="store_true")
    parser.add_argument("--require-phase5", action="store_true")
    parser.add_argument("--require-phase6", action="store_true")
    parser.add_argument("--require-phase7", action="store_true")
    parser.add_argument("--require-phase8", action="store_true")
    parser.add_argument("--require-phase9", action="store_true")
    parser.add_argument("--require-phase11", action="store_true")
    parser.add_argument("--require-phase12", action="store_true")
    parser.add_argument("--require-phase3-site", action="store_true")
    parser.add_argument("--require-phase6-site", action="store_true")
    parser.add_argument("--require-phase7-site", action="store_true")
    parser.add_argument("--require-phase8-site", action="store_true")
    parser.add_argument("--require-phase9-site", action="store_true")
    parser.add_argument("--require-phase11-site", action="store_true")
    parser.add_argument("--require-phase12-site", action="store_true")
    parser.add_argument("--max-age-minutes", type=int, default=None)
    args = parser.parse_args()

    feed_path = Path(args.feed)
    if not feed_path.is_file():
        raise SystemExit(f"ERROR: expected published feed at {feed_path}, but it does not exist")

    feed = json.loads(feed_path.read_text(encoding="utf-8"))
    errors = verify_feed(
        feed, args.expected_version, args.require_phase2, args.max_age_minutes,
        require_phase4=args.require_phase4,
        require_phase5=args.require_phase5,
        require_phase6=args.require_phase6,
        require_phase7=args.require_phase7,
        require_phase8=args.require_phase8,
        require_phase9=args.require_phase9,
        require_phase11=args.require_phase11,
        require_phase12=args.require_phase12,
    )

    if args.site:
        site_path = Path(args.site)
        if not site_path.is_file():
            errors.append(f"expected generated site at {site_path}, but it does not exist")
        else:
            errors.extend(verify_site(
                site_path.read_text(encoding="utf-8"), feed,
                require_phase3=args.require_phase3_site,
                require_phase6=args.require_phase6_site,
                require_phase7=args.require_phase7_site,
                require_phase8=args.require_phase8_site,
                require_phase9=args.require_phase9_site,
                require_phase11=args.require_phase11_site,
                require_phase12=args.require_phase12_site,
            ))

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        raise SystemExit(1)

    print(
        "Verified published output: "
        f"version={feed['meta']['feed_version']} "
        f"opportunities={len(feed['opportunities'])} "
        f"generated_at={feed['meta']['generated_at']}"
    )


if __name__ == "__main__":
    main()
