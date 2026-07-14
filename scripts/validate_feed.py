#!/usr/bin/env python3
"""Validates feed.json against the Kazi Sasa feed contract (SCHEMA.md / spec §24).

Usage:
    python3 validate_feed.py feed.json
    python3 validate_feed.py feed.json --taxonomy taxonomy.json

Exits non-zero on any error, so the GitHub Actions workflow (§24 recommendation:
"add feed validation in GitHub Actions... invalid feed updates fail before they
reach the app") can gate the commit step on this. Prints every problem found
rather than stopping at the first one, since a batch feed regeneration is more
useful to debug all at once.
"""
import json
import re
import sys
import argparse
from datetime import datetime, timezone
from urllib.parse import urlparse

VALID_OPPORTUNITY_TYPES = {"job", "fellowship", "grant", "internship", "programme"}
VALID_ORG_TYPES = {
    "employer", "ngo", "multilateral", "private", "unverified", "dfi",
    "development_bank", "commercial_bank", "investment_firm", "asset_manager",
    "private_equity", "venture_capital", "multinational", "un_agency",
    "government", "regulator", "state_owned_enterprise", "university",
    "foundation", "consulting_firm",
}
VALID_WORK_MODES = {"onsite", "hybrid", "remote_kenya", "remote_regional", "remote_global"}
VALID_SENIORITY = {"entry", "mid", "senior", "leadership"}
VALID_LOCATION_SCOPE = {"local", "national", "regional", "international"}
VALID_DEADLINE_CONFIDENCE = {"explicit", "inferred", "unknown"}
VALID_SOURCE_CONFIDENCE = {"official", "aggregated", "community", "unverified"}
VALID_FLAGS = {"urgent", "relocation_worthy", "ai_relevant", "hidden_gem", "eligibility_review", "sample"}
# v3 additions (spec §4.1)
VALID_CONTRACT_TYPES = {"permanent", "contract", "fixed_term", "part_time", "consultant", "volunteer", "unknown"}
VALID_EDUCATION_LEVELS = {"none", "secondary", "diploma", "bachelor", "masters", "phd"}
VALID_ELIGIBILITY_STATUSES = {
    "eligible", "likely_eligible", "uncertain", "local_only",
    "citizenship_restricted", "internal_only", "ineligible",
}
ID_OR_NULL_RE = re.compile(r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$")
ISO2_RE = re.compile(r"^[A-Z]{2}$")
ISO3_RE = re.compile(r"^[A-Z]{3}$")
VALID_EXTRACTION_LANGUAGES = {"en", "fr", "pt", "ar", "sw"}

VALID_AFRICA_RELEVANCE_STATUSES = {
    "africa_based_confirmed", "africa_regional", "remote_confirmed_open_to_africa",
    "africa_remit_non_african_location", "official_location_pending",
    "global_access_unconfirmed", "non_african", "unresolved",
}
VALID_AFRICAN_APPLICANT_ACCESS_STATUSES = {
    "confirmed_any_african_national", "confirmed_specific_african_nationality",
    "confirmed_international_recruitment", "likely_open",
    "work_authorisation_required", "local_only", "internal_only", "unknown", "not_open",
}
VALID_CERTIFICATION_LEVELS = {"certified", "conditional", "unverified", "excluded"}
VALID_EVIDENCE_STRENGTHS = {"explicit", "structured_source", "strong_inference", "weak_inference", "none"}

REQUIRED_OPPORTUNITY_FIELDS = ["id", "title", "opportunity_type", "organisation", "location", "source"]


class ValidationErrors:
    def __init__(self):
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, msg: str):
        self.errors.append(msg)

    def warn(self, msg: str):
        self.warnings.append(msg)

    @property
    def ok(self) -> bool:
        return not self.errors


def is_iso8601(value) -> bool:
    if not isinstance(value, str):
        return False
    try:
        # Python's fromisoformat wants +00:00 not Z pre-3.11; normalise defensively
        # so this validator behaves the same on older Python in CI as it does here.
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def parse_iso8601(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def is_valid_url(value) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def validate_meta(meta: dict, errs: ValidationErrors):
    for field in ["feed_version", "generated_at"]:
        if field not in meta:
            errs.error(f"meta.{field} is required")
    if "generated_at" in meta and not is_iso8601(meta["generated_at"]):
        errs.error(f"meta.generated_at is not valid ISO-8601: {meta.get('generated_at')!r}")
    if "next_expected_update" in meta and meta["next_expected_update"] is not None:
        if not is_iso8601(meta["next_expected_update"]):
            errs.error(f"meta.next_expected_update is not valid ISO-8601: {meta['next_expected_update']!r}")
    if "supported_languages" in meta:
        languages = meta.get("supported_languages")
        if not isinstance(languages, list) or set(languages) != VALID_EXTRACTION_LANGUAGES:
            errs.error("meta.supported_languages must contain en/fr/pt/ar/sw")
    if "location_registry_version" in meta and meta.get("location_registry_version") != "2.0":
        errs.error("meta.location_registry_version must be 2.0")
    if "investment_taxonomy_version" in meta and meta.get("investment_taxonomy_version") != "1.0":
        errs.error("meta.investment_taxonomy_version must be 1.0")
    if "investment_classifier_version" in meta and meta.get("investment_classifier_version") != "1.0":
        errs.error("meta.investment_classifier_version must be 1.0")
    if "dfi_source_pack_version" in meta and meta.get("dfi_source_pack_version") != "1.0":
        errs.error("meta.dfi_source_pack_version must be 1.0")
    if "enterprise_adapter_version" in meta and meta.get("enterprise_adapter_version") not in {"1.0", "1.1"}:
        errs.error("meta.enterprise_adapter_version must be 1.0 or 1.1")
    for key in ("ngo_source_pack_version", "ngo_taxonomy_version"):
        if key in meta and meta.get(key) != "1.0":
            errs.error(f"meta.{key} must be 1.0")
    if "ngo_classifier_version" in meta and meta.get("ngo_classifier_version") not in {"1.0", "1.1"}:
        errs.error("meta.ngo_classifier_version must be 1.0 or 1.1")
    for key in ("official_vacancy_quality_version", "government_source_pack_version", "government_schema_version", "kenya_public_institutions_version", "multinational_source_pack_version", "multinational_adapter_version"):
        if key in meta and meta.get(key) != "1.0" and not (key == "official_vacancy_quality_version" and meta.get(key) == "1.1"):
            errs.error(f"meta.{key} has an unsupported version")
    if "africa_access_certification_version" in meta and meta.get("africa_access_certification_version") != "1.0":
        errs.error("meta.africa_access_certification_version must be 1.0")
    if "government_deduplication_version" in meta and meta.get("government_deduplication_version") != "3.0":
        errs.error("meta.government_deduplication_version must be 3.0")
    if "eligibility_evidence_version" in meta and meta.get("eligibility_evidence_version") != "2.0":
        errs.error("meta.eligibility_evidence_version must be 2.0")


def validate_opportunity(
    opp: dict, index: int, seen_ids: set, taxonomy: dict | None,
    role_taxonomy: dict | None, errs: ValidationErrors,
):
    label = f"opportunities[{index}] (id={opp.get('id', '?')!r})"

    for field in REQUIRED_OPPORTUNITY_FIELDS:
        if field not in opp or opp[field] in (None, ""):
            errs.error(f"{label}: missing required field '{field}'")

    opp_id = opp.get("id")
    if opp_id:
        if not re.match(r"^[a-zA-Z0-9_.-]+$", opp_id):
            errs.error(f"{label}: id contains characters that risk breaking stability across regenerations")
        if opp_id in seen_ids:
            errs.error(f"{label}: duplicate id '{opp_id}' - ids must be stable AND unique")
        seen_ids.add(opp_id)

    opp_type = opp.get("opportunity_type")
    if opp_type is not None and opp_type not in VALID_OPPORTUNITY_TYPES:
        errs.error(f"{label}: invalid opportunity_type '{opp_type}' (expected one of {sorted(VALID_OPPORTUNITY_TYPES)})")

    org = opp.get("organisation", {})
    if isinstance(org, dict):
        if "name" not in org or not org["name"]:
            errs.error(f"{label}: organisation.name is required")
        if org.get("type") is not None and org.get("type") not in VALID_ORG_TYPES:
            errs.error(f"{label}: invalid organisation.type '{org.get('type')}'")
        org_id = org.get("id")
        if org_id is not None and (not isinstance(org_id, str) or not ID_OR_NULL_RE.match(org_id)):
            errs.error(f"{label}: organisation.id must be a lowercase stable identifier or null")
        if "verified" in org and not isinstance(org.get("verified"), bool):
            errs.error(f"{label}: organisation.verified must be boolean")
        if "registry_managed" in org and not isinstance(org.get("registry_managed"), bool):
            errs.error(f"{label}: organisation.registry_managed must be boolean")
        type_detail = org.get("type_detail")
        valid_org_types = set((role_taxonomy or {}).get("organisation_type_values", VALID_ORG_TYPES))
        if type_detail is not None and type_detail not in valid_org_types:
            errs.error(f"{label}: invalid organisation.type_detail '{type_detail}'")
    else:
        errs.error(f"{label}: organisation must be an object")

    work_mode = opp.get("work_mode")
    if work_mode is not None and work_mode not in VALID_WORK_MODES:
        errs.error(f"{label}: invalid work_mode '{work_mode}'")

    seniority = opp.get("seniority")
    if seniority is not None and seniority not in VALID_SENIORITY:
        errs.error(f"{label}: invalid seniority '{seniority}'")

    location = opp.get("location", {})
    if isinstance(location, dict):
        scope = location.get("scope")
        if scope is not None and scope not in VALID_LOCATION_SCOPE:
            errs.error(f"{label}: invalid location.scope '{scope}'")
        country_code = location.get("country_code")
        if country_code is not None and (not isinstance(country_code, str) or not ISO2_RE.match(country_code)):
            errs.error(f"{label}: location.country_code must be an uppercase ISO-2 code or null")
        country_iso3 = location.get("country_iso3")
        if country_iso3 is not None and (not isinstance(country_iso3, str) or not ISO3_RE.match(country_iso3)):
            errs.error(f"{label}: location.country_iso3 must be an uppercase ISO-3 code or null")
        for field_name in ("city", "country_canonical", "region_canonical", "admin_area", "matched_location_alias"):
            value = location.get(field_name)
            if value is not None and not isinstance(value, str):
                errs.error(f"{label}: location.{field_name} must be a string or null")
        coordinates = location.get("coordinates")
        if coordinates is not None:
            if not isinstance(coordinates, dict):
                errs.error(f"{label}: location.coordinates must be an object or null")
            else:
                lat, lon = coordinates.get("lat"), coordinates.get("lon")
                if not isinstance(lat, (int, float)) or isinstance(lat, bool) or not -90 <= lat <= 90:
                    errs.error(f"{label}: location.coordinates.lat must be between -90 and 90")
                if not isinstance(lon, (int, float)) or isinstance(lon, bool) or not -180 <= lon <= 180:
                    errs.error(f"{label}: location.coordinates.lon must be between -180 and 180")
        evidence = location.get("normalisation_evidence")
        if evidence is not None and (not isinstance(evidence, list) or any(not isinstance(item, str) for item in evidence)):
            errs.error(f"{label}: location.normalisation_evidence must be a list of strings")
        location_language = location.get("location_language")
        if location_language is not None and location_language not in VALID_EXTRACTION_LANGUAGES:
            errs.error(f"{label}: location.location_language must be one of {sorted(VALID_EXTRACTION_LANGUAGES)}")
        if "is_african" in location and not isinstance(location.get("is_african"), bool):
            errs.error(f"{label}: location.is_african must be boolean")
        normalisation_confidence = location.get("normalisation_confidence")
        if normalisation_confidence is not None and (
            not isinstance(normalisation_confidence, (int, float))
            or isinstance(normalisation_confidence, bool)
            or normalisation_confidence < 0
            or normalisation_confidence > 1
        ):
            errs.error(f"{label}: location.normalisation_confidence must be between 0 and 1")
    else:
        errs.error(f"{label}: location must be an object")

    deadline_confidence = opp.get("deadline_confidence", "unknown")
    if deadline_confidence not in VALID_DEADLINE_CONFIDENCE:
        errs.error(f"{label}: invalid deadline_confidence '{deadline_confidence}'")

    posted_at = opp.get("posted_at")
    deadline = opp.get("deadline")
    for field_name, value in [("posted_at", posted_at), ("deadline", deadline)]:
        if value is not None and not is_iso8601(value):
            errs.error(f"{label}: {field_name} is not valid ISO-8601: {value!r}")

    if posted_at and deadline and is_iso8601(posted_at) and is_iso8601(deadline):
        if parse_iso8601(deadline) < parse_iso8601(posted_at):
            errs.error(f"{label}: deadline ({deadline}) is before posted_at ({posted_at})")

    institution_profile = opp.get("institution_profile")
    if institution_profile is not None:
        if not isinstance(institution_profile, dict):
            errs.error(f"{label}: institution_profile must be an object")
        else:
            if not isinstance(institution_profile.get("is_dfi_or_multilateral"), bool):
                errs.error(f"{label}: institution_profile.is_dfi_or_multilateral must be boolean")
            institution_type = institution_profile.get("institution_type")
            valid_org_types = set((role_taxonomy or {}).get("organisation_type_values", VALID_ORG_TYPES))
            if institution_type not in valid_org_types:
                errs.error(f"{label}: invalid institution_profile.institution_type '{institution_type}'")
            registry_id = institution_profile.get("registry_id")
            if registry_id is not None and (not isinstance(registry_id, str) or not ID_OR_NULL_RE.match(registry_id)):
                errs.error(f"{label}: institution_profile.registry_id must be a stable identifier or null")
            source_pack = institution_profile.get("source_pack")
            if source_pack is not None and not isinstance(source_pack, str):
                errs.error(f"{label}: institution_profile.source_pack must be a string or null")
            if not isinstance(institution_profile.get("phase7_priority_institution"), bool):
                errs.error(f"{label}: institution_profile.phase7_priority_institution must be boolean")
            if institution_profile.get("phase7_priority_institution") and source_pack != "phase7_dfi_multilateral":
                errs.error(f"{label}: Phase 7 priority institutions must use source_pack 'phase7_dfi_multilateral'")
            if institution_profile.get("is_dfi_or_multilateral") and institution_type not in {
                "dfi", "development_bank", "multilateral", "investment_firm",
                "asset_manager", "private_equity", "venture_capital",
            }:
                errs.error(f"{label}: institution_profile.is_dfi_or_multilateral conflicts with institution_type '{institution_type}'")

    ngo_profile = opp.get("ngo_profile")
    if ngo_profile is not None:
        if not isinstance(ngo_profile, dict):
            errs.error(f"{label}: ngo_profile must be an object")
        else:
            for field in ("is_ngo_or_un", "phase8_priority_organisation", "is_programme_role"):
                if not isinstance(ngo_profile.get(field), bool):
                    errs.error(f"{label}: ngo_profile.{field} must be boolean")
            valid_classes = set((role_taxonomy or {}).get("ngo_classification_values", []))
            valid_tracks = set((role_taxonomy or {}).get("ngo_track_values", []))
            if valid_classes and ngo_profile.get("classification") not in valid_classes:
                errs.error(f"{label}: invalid ngo_profile.classification '{ngo_profile.get('classification')}'")
            track = ngo_profile.get("track")
            if track is not None and valid_tracks and track not in valid_tracks:
                errs.error(f"{label}: invalid ngo_profile.track '{track}'")
            canonical = ngo_profile.get("canonical_specialisation")
            if canonical is not None and taxonomy is not None:
                valid_specialisations = {row.get("id") for row in taxonomy.get("specialisations", [])}
                if canonical not in valid_specialisations:
                    errs.error(f"{label}: ngo_profile canonical specialisation is not valid")
            confidence = ngo_profile.get("confidence")
            if not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not 0 <= confidence <= 1:
                errs.error(f"{label}: ngo_profile.confidence must be between 0 and 1")
            source_pack = ngo_profile.get("source_pack")
            if source_pack is not None and not isinstance(source_pack, str):
                errs.error(f"{label}: ngo_profile.source_pack must be string or null")
            if ngo_profile.get("phase8_priority_organisation") and source_pack != "phase8_ngo_un_development":
                errs.error(f"{label}: Phase 8 priority organisations must use the Phase 8 source pack")

    government_profile = opp.get("government_profile")
    if government_profile is not None:
        if not isinstance(government_profile, dict):
            errs.error(f"{label}: government_profile must be an object")
        else:
            for field in ("is_government_or_public_service", "phase9_priority_portal", "internal_only"):
                if not isinstance(government_profile.get(field), bool):
                    errs.error(f"{label}: government_profile.{field} must be boolean")
            if government_profile.get("phase9_priority_portal") and government_profile.get("source_pack") != "phase9_government_wave1":
                errs.error(f"{label}: Phase 9 priority portal must use source_pack 'phase9_government_wave1'")
            positions = government_profile.get("number_of_positions")
            if positions is not None and (not isinstance(positions, int) or isinstance(positions, bool) or positions < 1):
                errs.error(f"{label}: government_profile.number_of_positions must be a positive integer or null")
            nationalities = government_profile.get("eligible_nationalities")
            if not isinstance(nationalities, list) or any(not isinstance(v, str) for v in nationalities):
                errs.error(f"{label}: government_profile.eligible_nationalities must be a list of strings")
            for field in ("phase10_kenya_public_institution",):
                if field in government_profile and not isinstance(government_profile.get(field), bool):
                    errs.error(f"{label}: government_profile.{field} must be boolean")

    public_profile = opp.get("public_institution_profile")
    if public_profile is not None:
        if not isinstance(public_profile, dict):
            errs.error(f"{label}: public_institution_profile must be an object")
        else:
            if not isinstance(public_profile.get("is_kenya_public_institution"), bool):
                errs.error(f"{label}: public_institution_profile.is_kenya_public_institution must be boolean")
            category = public_profile.get("category")
            valid_categories = {
                "central_bank", "revenue_authority", "capital_markets_regulator",
                "insurance_regulator", "pensions_regulator", "competition_authority",
                "investment_promotion_agency", "national_development_bank",
                "sovereign_infrastructure_fund", "public_university", "judicial_service",
                "parliamentary_service", "ports", "railways", "electricity_utility",
                "water_utility", "state_owned_enterprise",
            }
            if category is not None and category not in valid_categories:
                errs.error(f"{label}: invalid public_institution_profile.category '{category}'")
            if public_profile.get("is_kenya_public_institution"):
                if public_profile.get("source_pack") != "phase10_kenya_public_institutions":
                    errs.error(f"{label}: Kenya public institution must use Phase 10 source pack")
                if public_profile.get("country_code") != "KE":
                    errs.error(f"{label}: Kenya public institution must use country_code 'KE'")

    multinational_profile = opp.get("multinational_profile")
    if multinational_profile is not None:
        if not isinstance(multinational_profile, dict):
            errs.error(f"{label}: multinational_profile must be an object")
        else:
            for field in ("is_multinational", "phase11_priority_employer"):
                if not isinstance(multinational_profile.get(field), bool):
                    errs.error(f"{label}: multinational_profile.{field} must be boolean")
            sector = multinational_profile.get("sector")
            valid_sectors = {
                "automotive", "aviation", "banking", "consulting", "energy",
                "fintech", "fmcg", "hospitality", "industrials", "insurance",
                "logistics", "medical_devices", "payments", "pharmaceuticals",
                "professional_services", "technology", "telecommunications",
            }
            if sector is not None and sector not in valid_sectors:
                errs.error(f"{label}: invalid multinational_profile.sector '{sector}'")
            cities = multinational_profile.get("african_city_footprint")
            if not isinstance(cities, list) or any(not isinstance(item, str) for item in cities):
                errs.error(f"{label}: multinational_profile.african_city_footprint must be a list of strings")
            if multinational_profile.get("phase11_priority_employer") and multinational_profile.get("source_pack") != "phase11_multinationals":
                errs.error(f"{label}: Phase 11 priority employer must use phase11_multinationals source pack")

    africa_profile = opp.get("africa_relevance")
    if africa_profile is not None:
        if not isinstance(africa_profile, dict):
            errs.error(f"{label}: africa_relevance must be an object")
        else:
            if africa_profile.get("status") not in VALID_AFRICA_RELEVANCE_STATUSES:
                errs.error(f"{label}: invalid africa_relevance.status '{africa_profile.get('status')}'")
            if africa_profile.get("certification_level") not in VALID_CERTIFICATION_LEVELS:
                errs.error(f"{label}: invalid africa_relevance.certification_level")
            if not isinstance(africa_profile.get("default_visible"), bool):
                errs.error(f"{label}: africa_relevance.default_visible must be boolean")
            confidence = africa_profile.get("confidence")
            if not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not 0 <= confidence <= 1:
                errs.error(f"{label}: africa_relevance.confidence must be between 0 and 1")
            evidence = africa_profile.get("evidence")
            if not isinstance(evidence, list) or any(not isinstance(item, str) for item in evidence):
                errs.error(f"{label}: africa_relevance.evidence must be a list of strings")

    access_profile = opp.get("african_applicant_access")
    if access_profile is not None:
        if not isinstance(access_profile, dict):
            errs.error(f"{label}: african_applicant_access must be an object")
        else:
            if access_profile.get("status") not in VALID_AFRICAN_APPLICANT_ACCESS_STATUSES:
                errs.error(f"{label}: invalid african_applicant_access.status '{access_profile.get('status')}'")
            if access_profile.get("certification_level") not in VALID_CERTIFICATION_LEVELS:
                errs.error(f"{label}: invalid african_applicant_access.certification_level")
            if access_profile.get("evidence_strength") not in VALID_EVIDENCE_STRENGTHS:
                errs.error(f"{label}: invalid african_applicant_access.evidence_strength")
            confidence = access_profile.get("confidence")
            if not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not 0 <= confidence <= 1:
                errs.error(f"{label}: african_applicant_access.confidence must be between 0 and 1")
            for field_name in ("evidence", "eligible_nationalities"):
                value = access_profile.get(field_name)
                if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
                    errs.error(f"{label}: african_applicant_access.{field_name} must be a list of strings")

    source = opp.get("source", {})
    investment_profile = opp.get("investment_profile")
    if investment_profile is not None:
        if not isinstance(investment_profile, dict):
            errs.error(f"{label}: investment_profile must be an object")
        else:
            valid_classes = set((role_taxonomy or {}).get("investment_classification_values", []))
            valid_dfi = set((role_taxonomy or {}).get("dfi_relevance_values", []))
            valid_tracks = set((role_taxonomy or {}).get("investment_track_values", []))
            classification = investment_profile.get("classification")
            if valid_classes and classification not in valid_classes:
                errs.error(f"{label}: invalid investment_profile.classification '{classification}'")
            dfi_relevance = investment_profile.get("dfi_relevance")
            if valid_dfi and dfi_relevance not in valid_dfi:
                errs.error(f"{label}: invalid investment_profile.dfi_relevance '{dfi_relevance}'")
            track = investment_profile.get("track")
            if track is not None and valid_tracks and track not in valid_tracks:
                errs.error(f"{label}: invalid investment_profile.track '{track}'")
            canonical = investment_profile.get("canonical_specialisation")
            if canonical is not None and taxonomy is not None:
                valid_specialisations = {row.get("id") for row in taxonomy.get("specialisations", [])}
                if canonical not in valid_specialisations:
                    errs.error(f"{label}: investment_profile.canonical_specialisation '{canonical}' is not canonical")
            for field_name in ("confidence", "dfi_confidence"):
                value = investment_profile.get(field_name)
                if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0 or value > 1:
                    errs.error(f"{label}: investment_profile.{field_name} must be between 0 and 1")
            if not isinstance(investment_profile.get("is_investment_role"), bool):
                errs.error(f"{label}: investment_profile.is_investment_role must be boolean")
            for field_name in ("evidence", "negative_evidence"):
                value = investment_profile.get(field_name, [])
                if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
                    errs.error(f"{label}: investment_profile.{field_name} must be a list of strings")
            if investment_profile.get("is_investment_role") and opp.get("role_family") != "investment":
                errs.error(f"{label}: investment roles must use role_family 'investment'")

    if isinstance(source, dict):
        if "name" not in source or not source["name"]:
            errs.error(f"{label}: source.name is required")
        if "url" not in source or not is_valid_url(source.get("url")):
            errs.error(f"{label}: source.url is missing or not a valid http(s) URL")
        confidence = source.get("confidence")
        if confidence not in VALID_SOURCE_CONFIDENCE:
            errs.error(f"{label}: invalid or missing source.confidence '{confidence}'")
    else:
        errs.error(f"{label}: source must be an object")

    apply_url = opp.get("apply_url")
    if apply_url is None:
        errs.warn(f"{label}: no apply_url - the app will show 'no application link available'")
    elif not is_valid_url(apply_url):
        errs.error(f"{label}: apply_url is not a valid http(s) URL: {apply_url!r}")

    flags = opp.get("flags", [])
    if not isinstance(flags, list):
        errs.error(f"{label}: flags must be a list")
    else:
        for flag in flags:
            if flag not in VALID_FLAGS:
                errs.error(f"{label}: unknown flag '{flag}' (expected one of {sorted(VALID_FLAGS)})")

    # recommendations doc §24: "sample listings not marked official"
    is_sample = "sample" in flags
    if is_sample and isinstance(source, dict) and source.get("confidence") == "official":
        errs.error(f"{label}: flagged 'sample' but source.confidence is 'official' - sample data must never claim official confidence")

    if taxonomy is not None:
        # v3: categories field holds specialisation ids (backward-compatible
        # field name - see refresh_feed.py's FeedBuilder.map_category, which
        # is now an alias for map_specialisation).
        valid_specialisations = {s["id"] for s in taxonomy.get("specialisations", [])}
        valid_industries = {i["id"] for i in taxonomy.get("industries", [])}
        valid_skills = {s["id"] for s in taxonomy.get("skills", [])}
        for cat in opp.get("categories", []):
            if cat not in valid_specialisations:
                errs.warn(f"{label}: category '{cat}' is not in taxonomy.json - either add it there or map it to an existing id")
        for spec in opp.get("specialisations", []):
            if spec not in valid_specialisations:
                errs.warn(f"{label}: specialisation '{spec}' is not in taxonomy.json")
        industry = opp.get("industry")
        if industry is not None and industry not in valid_industries:
            errs.warn(f"{label}: industry '{industry}' is not in taxonomy.json industries")
        for skill in opp.get("skills_required", []) + opp.get("skills_preferred", []):
            if skill not in valid_skills:
                errs.warn(f"{label}: skill '{skill}' is not in taxonomy.json - either add it there or map it to an existing id")

    # Phase 2 additive fields. Every field remains optional for backward
    # compatibility with v3.0 snapshots, but is strict when present.
    valid_role_families = {row["id"] for row in (role_taxonomy or {}).get("role_families", [])}
    valid_themes = set((role_taxonomy or {}).get("thematic_sector_values", []))
    role_family = opp.get("role_family")
    if role_family is not None and valid_role_families and role_family not in valid_role_families:
        errs.error(f"{label}: role_family '{role_family}' is not in role_taxonomy.json")
    role_subfamily = opp.get("role_subfamily")
    if role_subfamily is not None and taxonomy is not None:
        valid_specialisations = {s["id"] for s in taxonomy.get("specialisations", [])}
        if role_subfamily not in valid_specialisations:
            errs.error(f"{label}: role_subfamily '{role_subfamily}' is not a canonical specialisation")
    thematic_sectors = opp.get("thematic_sectors", [])
    if thematic_sectors is not None and not isinstance(thematic_sectors, list):
        errs.error(f"{label}: thematic_sectors must be a list")
    elif valid_themes:
        for theme in thematic_sectors or []:
            if theme not in valid_themes:
                errs.error(f"{label}: thematic sector '{theme}' is not in role_taxonomy.json")

    eligibility = opp.get("eligibility")
    if eligibility is not None:
        if not isinstance(eligibility, dict):
            errs.error(f"{label}: eligibility must be an object")
        else:
            status = eligibility.get("status")
            if status not in VALID_ELIGIBILITY_STATUSES:
                errs.error(f"{label}: invalid eligibility.status '{status}'")
            confidence = eligibility.get("confidence")
            if (
                not isinstance(confidence, (int, float))
                or isinstance(confidence, bool)
                or confidence < 0
                or confidence > 1
            ):
                errs.error(f"{label}: eligibility.confidence must be between 0 and 1")
            citizenship_required = eligibility.get("citizenship_required")
            if citizenship_required is not None and not isinstance(citizenship_required, bool):
                errs.error(f"{label}: eligibility.citizenship_required must be boolean or null")
            work_auth = eligibility.get("work_authorisation_required")
            if work_auth is not None and not isinstance(work_auth, bool):
                errs.error(f"{label}: eligibility.work_authorisation_required must be boolean or null")
            for field_name in ("eligible_nationalities", "evidence"):
                value = eligibility.get(field_name, [])
                if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
                    errs.error(f"{label}: eligibility.{field_name} must be a list of strings")
            evidence_strength = eligibility.get("evidence_strength")
            if evidence_strength is not None and evidence_strength not in VALID_EVIDENCE_STRENGTHS:
                errs.error(f"{label}: eligibility.evidence_strength is invalid")
            detected_language = eligibility.get("detected_language")
            if detected_language is not None and detected_language not in VALID_EXTRACTION_LANGUAGES:
                errs.error(f"{label}: eligibility.detected_language must be one of {sorted(VALID_EXTRACTION_LANGUAGES)}")

    if isinstance(source, dict):
        source_id = source.get("id")
        if source_id is not None and (not isinstance(source_id, str) or not ID_OR_NULL_RE.match(source_id)):
            errs.error(f"{label}: source.id must be a lowercase stable identifier or null")
        if "registry_managed" in source and not isinstance(source.get("registry_managed"), bool):
            errs.error(f"{label}: source.registry_managed must be boolean")
        if source.get("kind") is not None and not isinstance(source.get("kind"), str):
            errs.error(f"{label}: source.kind must be a string or null")

    # v3 field validation (spec §4.1) - all nullable, only checked when present.
    contract_type = opp.get("contract_type")
    if contract_type is not None and contract_type not in VALID_CONTRACT_TYPES:
        errs.error(f"{label}: invalid contract_type '{contract_type}' (expected one of {sorted(VALID_CONTRACT_TYPES)})")

    education_required = opp.get("education_required")
    if education_required is not None and education_required not in VALID_EDUCATION_LEVELS:
        errs.error(f"{label}: invalid education_required '{education_required}' (expected one of {sorted(VALID_EDUCATION_LEVELS)})")

    years_min = opp.get("years_experience_min")
    years_max = opp.get("years_experience_max")
    for field_name, value in [("years_experience_min", years_min), ("years_experience_max", years_max)]:
        if value is not None and (not isinstance(value, int) or value < 0 or value > 50):
            errs.error(f"{label}: {field_name} must be an integer between 0 and 50, got {value!r}")
    if years_min is not None and years_max is not None and isinstance(years_min, int) and isinstance(years_max, int):
        if years_min > years_max:
            errs.error(f"{label}: years_experience_min ({years_min}) is greater than years_experience_max ({years_max})")

    education_field = opp.get("education_field", [])
    if education_field is not None and not isinstance(education_field, list):
        errs.error(f"{label}: education_field must be a list")

    languages_required = opp.get("languages_required", [])
    if languages_required is not None and not isinstance(languages_required, list):
        errs.error(f"{label}: languages_required must be a list")


def validate_feed(
    feed: dict, taxonomy: dict | None, role_taxonomy: dict | None = None
) -> ValidationErrors:
    errs = ValidationErrors()

    if "meta" not in feed:
        errs.error("top-level 'meta' object is required")
    else:
        validate_meta(feed["meta"], errs)

    opportunities = feed.get("opportunities")
    if not isinstance(opportunities, list):
        errs.error("top-level 'opportunities' must be a list")
        return errs

    if len(opportunities) == 0:
        errs.warn("opportunities list is empty - the app will fall back to cache or bundled seed data")

    seen_ids: set = set()
    for i, opp in enumerate(opportunities):
        validate_opportunity(opp, i, seen_ids, taxonomy, role_taxonomy, errs)

    declared_count = feed.get("meta", {}).get("opportunity_count")
    if declared_count is not None and declared_count != len(opportunities):
        errs.warn(f"meta.opportunity_count ({declared_count}) does not match actual count ({len(opportunities)})")

    return errs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("feed_path", help="Path to feed.json")
    parser.add_argument("--taxonomy", help="Path to taxonomy.json (optional - enables category/skill checks)")
    parser.add_argument("--role-taxonomy", help="Path to config/role_taxonomy.json (optional - enables Phase 2 checks)")
    parser.add_argument(
        "--fail-on-warnings",
        action="store_true",
        help="Exit non-zero when warnings exist; used by CI to enforce a clean published taxonomy.",
    )
    args = parser.parse_args()

    with open(args.feed_path, encoding="utf-8") as f:
        feed = json.load(f)

    taxonomy = None
    if args.taxonomy:
        with open(args.taxonomy, encoding="utf-8") as f:
            taxonomy = json.load(f)

    role_taxonomy = None
    if args.role_taxonomy:
        with open(args.role_taxonomy, encoding="utf-8") as f:
            role_taxonomy = json.load(f)

    result = validate_feed(feed, taxonomy, role_taxonomy)

    for w in result.warnings:
        print(f"WARN  {w}")
    for e in result.errors:
        print(f"ERROR {e}")

    print()
    print(f"{len(result.errors)} error(s), {len(result.warnings)} warning(s)")

    if not result.ok or (args.fail_on_warnings and result.warnings):
        sys.exit(1)


if __name__ == "__main__":
    main()
