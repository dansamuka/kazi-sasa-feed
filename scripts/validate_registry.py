#!/usr/bin/env python3
"""Validate the Phase 1/2 registries and their cross-file references."""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from registry import ADAPTER_FIELD, load_json
from validate_sources import validate_sources

ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
ROLE_ID_RE = re.compile(r"^[a-z0-9]+(?:[_-][a-z0-9]+)*$")
VALID_LEGACY_ORG_TYPES = {"private", "ngo", "multilateral", "employer", "unverified"}
VALID_CONFIDENCE = {"official", "aggregated", "community", "unverified"}


def _duplicates(values: list[str]) -> set[str]:
    counts = Counter(values)
    return {value for value, count in counts.items() if count > 1}


def validate_all(root: Path) -> list[str]:
    errors: list[str] = []
    config = root / "config"
    organisations = load_json(config / "organisations.json")
    sources = load_json(config / "source_registry.json")
    portals = load_json(config / "public_portals.json")
    locations = load_json(config / "african_locations.json")
    roles = load_json(config / "role_taxonomy.json")
    policies = load_json(config / "source_policies.json")
    investment = load_json(config / "investment_taxonomy.json")
    ngo = load_json(config / "ngo_taxonomy.json")
    taxonomy = load_json(root / "taxonomy.json")
    kenya_public = load_json(config / "kenya_public_institutions.json")
    multinationals = load_json(config / "multinational_targets.json")

    if organisations.get("registry_version") != "4.0":
        errors.append("organisations.json registry_version must be 4.0")

    # Locations first, because other registries reference country codes.
    if locations.get("registry_version") != "2.0":
        errors.append("african_locations.json registry_version must be 2.0")
    if set(locations.get("supported_languages", [])) != {"en", "fr", "pt", "ar", "sw"}:
        errors.append("african_locations.json supported_languages must contain en/fr/pt/ar/sw")
    if not isinstance(locations.get("region_aliases"), dict) or not locations.get("region_aliases"):
        errors.append("african_locations.json region_aliases must be a non-empty object")

    countries = locations.get("countries")
    if not isinstance(countries, list) or not countries:
        errors.append("african_locations.json countries must be a non-empty list")
        countries = []
    iso2_values = [str(row.get("iso2", "")) for row in countries if isinstance(row, dict)]
    iso3_values = [str(row.get("iso3", "")) for row in countries if isinstance(row, dict)]
    names = [str(row.get("name", "")).strip().lower() for row in countries if isinstance(row, dict)]
    for value in sorted(_duplicates(iso2_values)):
        errors.append(f"duplicate ISO2 country code {value!r}")
    for value in sorted(_duplicates(iso3_values)):
        errors.append(f"duplicate ISO3 country code {value!r}")
    for value in sorted(_duplicates(names)):
        errors.append(f"duplicate country name {value!r}")
    valid_country_codes = {value for value in iso2_values if len(value) == 2}
    if len(valid_country_codes) != 54:
        errors.append(f"african_locations.json must contain 54 unique ISO2 countries, found {len(valid_country_codes)}")
    for index, country in enumerate(countries):
        label = f"african_locations.countries[{index}]"
        if not isinstance(country, dict):
            errors.append(f"{label} must be an object")
            continue
        if len(str(country.get("iso2", ""))) != 2:
            errors.append(f"{label}.iso2 must be a two-character code")
        if len(str(country.get("iso3", ""))) != 3:
            errors.append(f"{label}.iso3 must be a three-character code")
        if not country.get("name") or not country.get("region"):
            errors.append(f"{label} requires name and region")
        city_rows = country.get("cities", [])
        if not isinstance(city_rows, list) or not city_rows:
            errors.append(f"{label}.cities must be a non-empty list in Phase 4")
            city_rows = []
        city_names = [str(city.get("name", "")).strip().lower() for city in city_rows if isinstance(city, dict)]
        for city in sorted(_duplicates(city_names)):
            errors.append(f"{label} has duplicate city {city!r}")
        for city_index, city in enumerate(city_rows):
            city_label = f"{label}.cities[{city_index}]"
            if not isinstance(city, dict) or not city.get("name"):
                errors.append(f"{city_label}.name is required")
                continue
            if not isinstance(city.get("aliases", []), list):
                errors.append(f"{city_label}.aliases must be a list")
            coordinates = city.get("coordinates")
            if coordinates is not None:
                if not isinstance(coordinates, dict):
                    errors.append(f"{city_label}.coordinates must be an object or null")
                else:
                    lat, lon = coordinates.get("lat"), coordinates.get("lon")
                    if not isinstance(lat, (int, float)) or not -90 <= lat <= 90:
                        errors.append(f"{city_label}.coordinates.lat is invalid")
                    if not isinstance(lon, (int, float)) or not -180 <= lon <= 180:
                        errors.append(f"{city_label}.coordinates.lon is invalid")
        admin_rows = country.get("admin_areas", [])
        if not isinstance(admin_rows, list):
            errors.append(f"{label}.admin_areas must be a list")

    role_families = roles.get("role_families")
    if not isinstance(role_families, list) or not role_families:
        errors.append("role_taxonomy.json role_families must be a non-empty list")
        role_families = []
    role_ids = [str(row.get("id", "")) for row in role_families if isinstance(row, dict)]
    for value in sorted(_duplicates(role_ids)):
        errors.append(f"duplicate role-family id {value!r}")
    valid_role_ids = set(role_ids)
    valid_org_types = set(roles.get("organisation_type_values", []))
    if not valid_org_types:
        errors.append("role_taxonomy.json organisation_type_values must be non-empty")
    valid_eligibility_statuses = set(roles.get("eligibility_status_values", []))
    if not valid_eligibility_statuses:
        errors.append("role_taxonomy.json eligibility_status_values must be non-empty")
    valid_themes = set(roles.get("thematic_sector_values", []))
    if not valid_themes:
        errors.append("role_taxonomy.json thematic_sector_values must be non-empty")
    for index, role in enumerate(role_families):
        label = f"role_taxonomy.role_families[{index}]"
        if not ROLE_ID_RE.match(str(role.get("id", ""))):
            errors.append(f"{label}.id must be kebab/snake-safe lowercase identifier")
        if not role.get("label"):
            errors.append(f"{label}.label is required")

    valid_industries = {row["id"] for row in taxonomy.get("industries", [])}
    valid_specialisations = {row["id"] for row in taxonomy.get("specialisations", [])}
    industry_role_map = roles.get("industry_role_family_map", {})
    specialisation_role_map = roles.get("specialisation_role_family_map", {})
    thematic_map = roles.get("thematic_sector_map", {})
    if set(industry_role_map) != valid_industries:
        errors.append("role_taxonomy industry_role_family_map must cover every legacy industry exactly")
    if set(specialisation_role_map) != valid_specialisations:
        errors.append("role_taxonomy specialisation_role_family_map must cover every legacy specialisation exactly")
    for key, family in {**industry_role_map, **specialisation_role_map}.items():
        if family not in valid_role_ids:
            errors.append(f"role taxonomy mapping {key!r} references unknown role family {family!r}")
    allowed_theme_keys = valid_industries | valid_specialisations
    for key, values in thematic_map.items():
        if key not in allowed_theme_keys:
            errors.append(f"thematic_sector_map has unknown taxonomy key {key!r}")
        if not isinstance(values, list) or any(value not in valid_themes for value in values):
            errors.append(f"thematic_sector_map[{key!r}] contains an invalid thematic sector")

    # Phase 6 investment and DFI taxonomy.
    if investment.get("taxonomy_version") != "1.0":
        errors.append("investment_taxonomy.json taxonomy_version must be 1.0")
    if investment.get("classifier_version") != "1.0":
        errors.append("investment_taxonomy.json classifier_version must be 1.0")
    investment_tracks = investment.get("tracks")
    if not isinstance(investment_tracks, list) or not investment_tracks:
        errors.append("investment_taxonomy.json tracks must be a non-empty list")
        investment_tracks = []
    track_ids = [str(row.get("id", "")) for row in investment_tracks if isinstance(row, dict)]
    for value in sorted(_duplicates(track_ids)):
        errors.append(f"duplicate investment track id {value!r}")
    if set(roles.get("investment_track_values", [])) != set(track_ids):
        errors.append("role_taxonomy investment_track_values must exactly match investment_taxonomy tracks")
    if set(roles.get("investment_classification_values", [])) != set(investment.get("classification_values", [])):
        errors.append("role_taxonomy investment_classification_values must match investment taxonomy")
    if set(roles.get("dfi_relevance_values", [])) != set(investment.get("dfi_relevance_values", [])):
        errors.append("role_taxonomy dfi_relevance_values must match investment taxonomy")
    canonical_tracks: set[str] = set()
    for index, track in enumerate(investment_tracks):
        label = f"investment_taxonomy.tracks[{index}]"
        if not isinstance(track, dict) or not ROLE_ID_RE.match(str(track.get("id", ""))):
            errors.append(f"{label}.id is invalid")
            continue
        if not track.get("label"):
            errors.append(f"{label}.label is required")
        if track.get("classification") not in set(investment.get("classification_values", [])):
            errors.append(f"{label}.classification is invalid")
        canonical = track.get("canonical_specialisation")
        if canonical not in valid_specialisations:
            errors.append(f"{label}.canonical_specialisation references unknown specialisation {canonical!r}")
        elif canonical in canonical_tracks:
            errors.append(f"duplicate investment canonical_specialisation {canonical!r}")
        canonical_tracks.add(canonical)
        if not isinstance(track.get("title_phrases"), list) or not track.get("title_phrases"):
            errors.append(f"{label}.title_phrases must be a non-empty list")
        if not isinstance(track.get("context_phrases", []), list):
            errors.append(f"{label}.context_phrases must be a list")

    # Phase 8 NGO/UN taxonomy.
    if ngo.get("taxonomy_version") != "1.0":
        errors.append("ngo_taxonomy.json taxonomy_version must be 1.0")
    if ngo.get("classifier_version") not in {"1.0", "1.1"}:
        errors.append("ngo_taxonomy.json classifier_version must be 1.0 or 1.1")
    ngo_tracks = ngo.get("tracks")
    if not isinstance(ngo_tracks, list) or not ngo_tracks:
        errors.append("ngo_taxonomy.json tracks must be a non-empty list")
        ngo_tracks = []
    ngo_track_ids = [str(row.get("id", "")) for row in ngo_tracks if isinstance(row, dict)]
    if set(roles.get("ngo_track_values", [])) != set(ngo_track_ids):
        errors.append("role_taxonomy ngo_track_values must exactly match ngo_taxonomy tracks")
    if set(roles.get("ngo_classification_values", [])) != set(ngo.get("classification_values", [])):
        errors.append("role_taxonomy ngo_classification_values must match ngo taxonomy")
    for index, track in enumerate(ngo_tracks):
        label = f"ngo_taxonomy.tracks[{index}]"
        if not isinstance(track, dict) or not ROLE_ID_RE.match(str(track.get("id", ""))):
            errors.append(f"{label}.id is invalid")
            continue
        if track.get("canonical_specialisation") not in valid_specialisations:
            errors.append(f"{label}.canonical_specialisation references unknown taxonomy value")
        if track.get("role_family") not in valid_role_ids:
            errors.append(f"{label}.role_family references unknown role family")
        if track.get("classification") not in set(ngo.get("classification_values", [])):
            errors.append(f"{label}.classification is invalid")
        if not isinstance(track.get("title_phrases"), list) or not track.get("title_phrases"):
            errors.append(f"{label}.title_phrases must be a non-empty list")

    # Organisation registry.
    org_rows = organisations.get("organisations")
    if not isinstance(org_rows, list) or not org_rows:
        errors.append("organisations.json organisations must be a non-empty list")
        org_rows = []
    org_ids = [str(row.get("id", "")) for row in org_rows if isinstance(row, dict)]
    org_names = [str(row.get("name", "")).strip().lower() for row in org_rows if isinstance(row, dict)]
    for value in sorted(_duplicates(org_ids)):
        errors.append(f"duplicate organisation id {value!r}")
    for value in sorted(_duplicates(org_names)):
        errors.append(f"duplicate organisation name {value!r}")

    connections: list[str] = []
    for index, organisation in enumerate(org_rows):
        label = f"organisations[{index}]"
        if not isinstance(organisation, dict):
            errors.append(f"{label} must be an object")
            continue
        org_id = str(organisation.get("id", ""))
        if not ID_RE.match(org_id):
            errors.append(f"{label}.id is invalid: {org_id!r}")
        if not organisation.get("name"):
            errors.append(f"{label}.name is required")
        if organisation.get("organisation_type") not in valid_org_types:
            errors.append(f"{label}.organisation_type is invalid")
        for family in organisation.get("career_families", []):
            if family not in valid_role_ids:
                errors.append(f"{label}.career_families references unknown role family {family!r}")
        for code in organisation.get("countries", []):
            if code not in valid_country_codes:
                errors.append(f"{label}.countries references unknown African ISO2 code {code!r}")
        if not isinstance(organisation.get("sources"), list) or not organisation.get("sources"):
            errors.append(f"{label}.sources must be a non-empty list")
            continue
        for source_index, source in enumerate(organisation["sources"]):
            source_label = f"{label}.sources[{source_index}]"
            adapter = source.get("adapter")
            identifier = str(source.get("identifier", "")).strip()
            if adapter not in ADAPTER_FIELD:
                errors.append(f"{source_label}.adapter unsupported: {adapter!r}")
            if not identifier:
                errors.append(f"{source_label}.identifier is required")
            if source.get("legacy_type") not in VALID_LEGACY_ORG_TYPES:
                errors.append(f"{source_label}.legacy_type is invalid")
            config_values = source.get("config") or {}
            defaults = config_values.get("default_specialisations", [])
            if not isinstance(defaults, list):
                errors.append(f"{source_label}.config.default_specialisations must be a list")
            else:
                for default in defaults:
                    if default not in valid_specialisations:
                        errors.append(
                            f"{source_label}.config.default_specialisations references unknown specialisation {default!r}"
                        )
            connections.append(f"{adapter}:{identifier.lower()}")
    for connection in sorted(_duplicates(connections)):
        errors.append(f"duplicate ATS connection {connection!r}")

    # Source registry preserves source governance but adds stable IDs and metadata.
    errors.extend(f"source_registry: {error}" for error in validate_sources(sources))
    source_rows = sources.get("sources", [])
    source_ids = [str(row.get("id", "")) for row in source_rows if isinstance(row, dict)]
    for value in sorted(_duplicates(source_ids)):
        errors.append(f"duplicate source id {value!r}")
    for index, source in enumerate(source_rows):
        label = f"source_registry.sources[{index}]"
        if not ID_RE.match(str(source.get("id", ""))):
            errors.append(f"{label}.id is invalid")
        if source.get("default_confidence") not in VALID_CONFIDENCE:
            errors.append(f"{label}.default_confidence is invalid")
        collector = source.get("collector")
        if collector is not None and not isinstance(collector, str):
            errors.append(f"{label}.collector must be a string or null")

    # Public portals may be empty in Phase 1, but planned targets must be valid.
    valid_portal_adapters = set(portals.get("valid_adapter_types", []))
    for section in ("portals", "planned_targets"):
        rows = portals.get(section, [])
        if not isinstance(rows, list):
            errors.append(f"public_portals.{section} must be a list")
            continue
        ids = [str(row.get("id", "")) for row in rows if isinstance(row, dict)]
        for value in sorted(_duplicates(ids)):
            errors.append(f"public_portals.{section} duplicate id {value!r}")
        for index, portal in enumerate(rows):
            label = f"public_portals.{section}[{index}]"
            if not ID_RE.match(str(portal.get("id", ""))):
                errors.append(f"{label}.id is invalid")
            if portal.get("country_code") not in valid_country_codes:
                errors.append(f"{label}.country_code is invalid")
            if portal.get("adapter") not in valid_portal_adapters:
                errors.append(f"{label}.adapter is invalid")

    registry_policy = (policies.get("registry") or {})
    for required in (
        "organisations_authoritative",
        "legacy_ats_configs_generated",
        "source_registry_authoritative",
        "legacy_sources_json_generated",
    ):
        if registry_policy.get(required) is not True:
            errors.append(f"source_policies.registry.{required} must be true")


    schema_policy = policies.get("schema_evolution") or {}
    for required in (
        "phase2_additive_only",
        "preserve_legacy_fields",
        "android_unknown_keys_are_ignored",
        "phase2_fields_optional_for_older_snapshots",
        "phase4_additive_only",
        "phase4_fields_optional_for_older_snapshots",
        "phase5_additive_only",
        "phase5_fields_optional_for_older_snapshots",
        "phase6_additive_only",
        "phase6_fields_optional_for_older_snapshots",
        "phase7_additive_only",
        "phase7_fields_optional_for_older_snapshots",
        "phase8_additive_only",
        "phase8_fields_optional_for_older_snapshots",
        "phase9_additive_only",
        "phase9_fields_optional_for_older_snapshots",
        "phase10_kenya_additive_only",
        "phase10_kenya_fields_optional_for_older_snapshots",
        "phase11_additive_only",
        "phase11_fields_optional_for_older_snapshots",
    ):
        if schema_policy.get(required) is not True:
            errors.append(f"source_policies.schema_evolution.{required} must be true")
    if schema_policy.get("current_feed_version") != "3.8":
        errors.append("source_policies.schema_evolution.current_feed_version must be 3.8")

    expansion_policy = policies.get("source_expansion") or {}
    for required in (
        "recruitee_public_api", "reliefweb_all_africa", "untalent_json_or_rss",
        "adzuna_priority_search_portfolio", "official_source_precedence",
        "cross_source_semantic_deduplication", "regional_regression_gates",
    ):
        if expansion_policy.get(required) is not True:
            errors.append(f"source_policies.source_expansion.{required} must be true")

    coverage_path = config / "coverage_gates.json"
    if not coverage_path.exists():
        errors.append("coverage_gates.json is required in Phase 5")
    else:
        coverage = load_json(coverage_path)
        if coverage.get("gate_version") != "1.0":
            errors.append("coverage_gates.json gate_version must be 1.0")
        valid_regions = {country.get("region") for country in countries if isinstance(country, dict)}
        for section in ("regression_gates", "phase5_targets"):
            minimums = (coverage.get(section) or {}).get("minimum_by_region") or {}
            for region, minimum in minimums.items():
                if region not in valid_regions:
                    errors.append(f"coverage_gates.{section} references unknown region {region!r}")
                if not isinstance(minimum, int) or minimum < 0:
                    errors.append(f"coverage_gates.{section}.{region} must be a non-negative integer")

    location_policy = policies.get("location_normalisation") or {}
    for required in ("registry_authoritative", "unicode_preserving_matching", "confidence_and_evidence_required", "do_not_guess_without_evidence"):
        if location_policy.get(required) is not True:
            errors.append(f"source_policies.location_normalisation.{required} must be true")
    if set(location_policy.get("supported_languages", [])) != {"en", "fr", "pt", "ar", "sw"}:
        errors.append("source_policies.location_normalisation.supported_languages must contain en/fr/pt/ar/sw")

    investment_policy = policies.get("investment_classification") or {}
    for required in (
        "taxonomy_authoritative", "title_evidence_outweighs_description",
        "institution_type_is_context_not_role_proof",
        "accounting_and_control_false_positive_guard",
        "multilingual_title_phrases", "reviewed_regression_corpus_required",
    ):
        if investment_policy.get(required) is not True:
            errors.append(f"source_policies.investment_classification.{required} must be true")

    dfi_policy = policies.get("dfi_source_pack") or {}
    for required in (
        "registry_backed_priority_institutions", "official_sources_only",
        "enterprise_adapters_public_career_sites_only",
        "institution_type_is_separate_from_role_classification",
        "source_health_required", "official_apply_links_preferred",
    ):
        if dfi_policy.get(required) is not True:
            errors.append(f"source_policies.dfi_source_pack.{required} must be true")

    phase9_portals = portals.get("portals", []) if isinstance(portals.get("portals", []), list) else []
    if len(phase9_portals) != 5:
        errors.append(f"Phase 9 requires five Wave 1 portal records, found {len(phase9_portals)}")
    enabled_phase9 = [row for row in phase9_portals if row.get("enabled")]
    if len(enabled_phase9) < 3:
        errors.append("Phase 9 requires at least three enabled official portals")
    for portal in phase9_portals:
        if not portal.get("enabled") and not portal.get("disabled_reason"):
            errors.append(f"disabled public portal {portal.get('id')!r} requires disabled_reason")
        if portal.get("enabled") and not portal.get("listing_url"):
            errors.append(f"enabled public portal {portal.get('id')!r} requires listing_url")

    phase7_orgs = [row for row in org_rows if row.get("source_pack") == "phase7_dfi_multilateral"]
    if len(phase7_orgs) < 25:
        errors.append(f"Phase 7 requires at least 25 priority DFI/multilateral institutions, found {len(phase7_orgs)}")
    phase7_adapters = {source.get("adapter") for row in phase7_orgs for source in row.get("sources", [])}
    for required_adapter in ("cornerstone", "successfactors", "oracle_cx", "official_html"):
        if required_adapter not in phase7_adapters:
            errors.append(f"Phase 7 priority registry requires adapter {required_adapter!r}")


    # Kenya-only public-institution expansion.
    if kenya_public.get("registry_version") != "1.0":
        errors.append("kenya_public_institutions.json registry_version must be 1.0")
    public_rows = kenya_public.get("institutions", [])
    required_public_categories = set(kenya_public.get("required_categories", []))
    expected_public_categories = {
        "central_bank", "revenue_authority", "capital_markets_regulator",
        "insurance_regulator", "pensions_regulator", "competition_authority",
        "investment_promotion_agency", "national_development_bank",
        "sovereign_infrastructure_fund", "public_university", "judicial_service",
        "parliamentary_service", "ports", "railways", "electricity_utility",
        "water_utility", "state_owned_enterprise",
    }
    if required_public_categories != expected_public_categories:
        errors.append("kenya_public_institutions.required_categories must cover every requested Kenya category")
    if len(public_rows) != 60:
        errors.append(f"Kenya public-institution registry must contain 60 institutions, found {len(public_rows)}")
    public_ids = []
    for index, row in enumerate(public_rows):
        label = f"kenya_public_institutions.institutions[{index}]"
        org_id = str(row.get("organisation_id", ""))
        public_ids.append(org_id)
        if org_id not in set(org_ids):
            errors.append(f"{label}.organisation_id does not exist in organisations.json")
            continue
        org = next((candidate for candidate in org_rows if candidate.get("id") == org_id), {})
        if org.get("source_pack") != "phase10_kenya_public_institutions":
            errors.append(f"{label} organisation must use phase10_kenya_public_institutions source pack")
        if org.get("public_institution_category") != row.get("category"):
            errors.append(f"{label}.category must match organisation public_institution_category")
        if row.get("category") not in expected_public_categories:
            errors.append(f"{label}.category is invalid")
        if row.get("enabled") and not row.get("career_url"):
            errors.append(f"{label} enabled record requires career_url")
        if not row.get("enabled") and not row.get("disabled_reason"):
            errors.append(f"{label} disabled record requires disabled_reason")
    for duplicate in sorted(_duplicates(public_ids)):
        errors.append(f"duplicate Kenya public-institution organisation_id {duplicate!r}")
    if {row.get("category") for row in public_rows} != expected_public_categories:
        errors.append("Kenya public-institution records do not represent every requested category")

    # Phase 11 multinational target registry.
    if multinationals.get("registry_version") != "1.0":
        errors.append("multinational_targets.json registry_version must be 1.0")
    multinational_rows = multinationals.get("employers", [])
    if multinationals.get("target_count") != 100 or len(multinational_rows) != 100:
        errors.append(f"Phase 11 requires exactly 100 multinational targets, found {len(multinational_rows)}")
    multinational_ids = []
    valid_multinational_sectors = set(multinationals.get("sectors", []))
    allowed_multinational_adapters = {"workday", "smartrecruiters", "workable", "multinational_html"}
    for index, row in enumerate(multinational_rows):
        label = f"multinational_targets.employers[{index}]"
        org_id = str(row.get("organisation_id", ""))
        multinational_ids.append(org_id)
        if org_id not in set(org_ids):
            errors.append(f"{label}.organisation_id does not exist in organisations.json")
            continue
        org = next((candidate for candidate in org_rows if candidate.get("id") == org_id), {})
        if org.get("organisation_type") != "multinational":
            errors.append(f"{label} organisation_type must be multinational")
        if org.get("source_pack") != "phase11_multinationals":
            errors.append(f"{label} organisation must use phase11_multinationals source pack")
        if org.get("multinational_sector") != row.get("sector"):
            errors.append(f"{label}.sector must match organisation multinational_sector")
        if row.get("sector") not in valid_multinational_sectors:
            errors.append(f"{label}.sector is invalid")
        if row.get("adapter") not in allowed_multinational_adapters:
            errors.append(f"{label}.adapter is invalid")
        if not isinstance(row.get("cities", []), list) or not row.get("cities"):
            errors.append(f"{label}.cities must be a non-empty list")
        if row.get("enabled") and not row.get("career_identifier"):
            errors.append(f"{label} enabled record requires career_identifier")
        if not row.get("enabled") and not row.get("disabled_reason"):
            errors.append(f"{label} disabled record requires disabled_reason")
    for duplicate in sorted(_duplicates(multinational_ids)):
        errors.append(f"duplicate multinational organisation_id {duplicate!r}")
    if len([row for row in multinational_rows if row.get("enabled")]) < 35:
        errors.append("Phase 11 requires at least 35 enabled multinational targets")

    kenya_policy = policies.get("kenya_public_institutions") or {}
    for required in ("registry_authoritative", "kenya_only", "official_sources_only", "citizenship_context_is_not_role_classification", "required_category_coverage"):
        if kenya_policy.get(required) is not True:
            errors.append(f"source_policies.kenya_public_institutions.{required} must be true")
    multinational_policy = policies.get("multinational_source_pack") or {}
    for required in ("official_sources_only", "employer_context_is_not_role_proof", "workday_public_search", "smartrecruiters_public_postings", "workable_public_postings", "city_coverage_reporting", "disabled_sources_must_have_reason"):
        if multinational_policy.get(required) is not True:
            errors.append(f"source_policies.multinational_source_pack.{required} must be true")
    if multinational_policy.get("target_employer_count") != 100:
        errors.append("source_policies.multinational_source_pack.target_employer_count must be 100")

    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=None)
    args = parser.parse_args()
    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parent.parent
    errors = validate_all(root)
    for error in errors:
        print(f"ERROR {error}")
    if errors:
        print(f"{len(errors)} registry error(s)")
        raise SystemExit(1)
    print("0 registry errors")


if __name__ == "__main__":
    main()
