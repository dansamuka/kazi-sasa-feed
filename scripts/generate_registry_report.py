#!/usr/bin/env python3
"""Generate a human/audit-friendly summary of the current registries."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from registry import load_json
from reporting import write_json
from validate_registry import validate_all
from collectors.registry import collector_manifest


def build_registry_report(root: Path) -> dict:
    config = root / "config"
    organisations = load_json(config / "organisations.json")
    sources = load_json(config / "source_registry.json")
    locations = load_json(config / "african_locations.json")
    global_countries = load_json(config / "global_country_codes.json")
    roles = load_json(config / "role_taxonomy.json")
    portals = load_json(config / "public_portals.json")
    investment = load_json(config / "investment_taxonomy.json")
    investment_cases = load_json(config / "investment_test_cases.json")
    ngo = load_json(config / "ngo_taxonomy.json")
    ngo_cases = load_json(config / "ngo_test_cases.json")
    kenya_public = load_json(config / "kenya_public_institutions.json")
    multinationals = load_json(config / "multinational_targets.json")

    org_rows = organisations["organisations"]
    connections = [source for org in org_rows for source in org.get("sources", [])]
    countries = locations["countries"]
    errors = validate_all(root)

    return {
        "report_version": "12.0",
        "phase": "Africa and Eligibility Certification Hardening",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "validation_errors": errors,
        "summary": {
            "organisation_count": len(org_rows),
            "ats_connection_count": len(connections),
            "enabled_ats_connections": sum(1 for row in connections if row.get("enabled", True)),
            "verified_ats_connections": sum(1 for row in connections if row.get("verified")),
            "source_registry_count": len(sources["sources"]),
            "african_country_count": len(countries),
            "global_country_count": len(global_countries.get("countries", [])),
            "global_african_flag_count": sum(1 for row in global_countries.get("countries", []) if row.get("is_african")),
            "registered_city_count": sum(len(country.get("cities", [])) for country in countries),
            "registered_admin_area_count": sum(len(country.get("admin_areas", [])) for country in countries),
            "city_coordinate_count": sum(1 for country in countries for city in country.get("cities", []) if city.get("coordinates")),
            "location_supported_language_count": len(locations.get("supported_languages", [])),
            "location_regression_case_count": len(load_json(config / "location_test_cases.json").get("cases", [])),
            "role_family_count": len(roles["role_families"]),
            "organisation_type_count": len(roles.get("organisation_type_values", [])),
            "thematic_sector_count": len(roles.get("thematic_sector_values", [])),
            "eligibility_status_count": len(roles.get("eligibility_status_values", [])),
            "industry_role_mapping_count": len(roles.get("industry_role_family_map", {})),
            "specialisation_role_mapping_count": len(roles.get("specialisation_role_family_map", {})),
            "public_portal_count": len(portals.get("portals", [])),
            "enabled_public_portals": sum(1 for row in portals.get("portals", []) if row.get("enabled")),
            "disabled_public_portals": sum(1 for row in portals.get("portals", []) if not row.get("enabled")),
            "public_api_collector_count": len(collector_manifest()),
            "phase7_priority_institution_count": sum(1 for row in org_rows if row.get("source_pack") == "phase7_dfi_multilateral"),
            "enterprise_institution_adapter_count": sum(1 for row in connections if row.get("adapter") in {"cornerstone", "successfactors", "oracle_cx", "official_html", "pageup"}),
            "recruitee_board_count": sum(1 for row in connections if row.get("adapter") == "recruitee"),
            "investment_track_count": len(investment.get("tracks", [])),
            "investment_regression_case_count": len(investment_cases.get("cases", [])),
            "investment_classification_count": len(investment.get("classification_values", [])),
            "dfi_relevance_value_count": len(investment.get("dfi_relevance_values", [])),
            "phase8_priority_organisation_count": sum(1 for row in org_rows if row.get("source_pack") == "phase8_ngo_un_development"),
            "ngo_track_count": len(ngo.get("tracks", [])),
            "ngo_regression_case_count": len(ngo_cases.get("cases", [])),
            "ngo_classification_count": len(ngo.get("classification_values", [])),
            "pageup_board_count": sum(1 for row in connections if row.get("adapter") == "pageup"),
            "phase9_priority_portal_count": len(portals.get("portals", [])),
            "phase9_enabled_portal_count": sum(1 for row in portals.get("portals", []) if row.get("enabled")),
            "kenya_public_institution_count": len(kenya_public.get("institutions", [])),
            "kenya_public_institution_enabled_count": sum(1 for row in kenya_public.get("institutions", []) if row.get("enabled")),
            "kenya_public_institution_category_count": len(kenya_public.get("required_categories", [])),
            "phase11_multinational_target_count": len(multinationals.get("employers", [])),
            "phase11_multinational_enabled_count": sum(1 for row in multinationals.get("employers", []) if row.get("enabled")),
            "phase11_multinational_sector_count": len(multinationals.get("sectors", [])),
            "workday_target_count": sum(1 for row in connections if row.get("adapter") == "workday"),
            "smartrecruiters_target_count": sum(1 for row in connections if row.get("adapter") == "smartrecruiters"),
            "workable_target_count": sum(1 for row in connections if row.get("adapter") == "workable"),
        },
        "coverage": {
            "connections_by_adapter": dict(sorted(Counter(row["adapter"] for row in connections).items())),
            "organisations_by_type": dict(sorted(Counter(row["organisation_type"] for row in org_rows).items())),
            "organisations_by_priority": dict(sorted(Counter(str(row["priority"]) for row in org_rows).items())),
            "source_confidence": dict(sorted(Counter(row["default_confidence"] for row in sources["sources"]).items())),
            "countries_by_region": dict(sorted(Counter(row["region"] for row in countries).items())),
            "location_supported_languages": locations.get("supported_languages", []),
            "investment_tracks": [row.get("id") for row in investment.get("tracks", [])],
            "ngo_tracks": [row.get("id") for row in ngo.get("tracks", [])],
            "government_portals_by_status": dict(sorted(Counter("enabled" if row.get("enabled") else "disabled" for row in portals.get("portals", [])).items())),
            "government_portals_by_adapter": dict(sorted(Counter(row.get("adapter") for row in portals.get("portals", [])).items())),
            "kenya_public_institutions_by_category": dict(sorted(Counter(row.get("category") for row in kenya_public.get("institutions", [])).items())),
            "multinational_targets_by_sector": dict(sorted(Counter(row.get("sector") for row in multinationals.get("employers", [])).items())),
            "multinational_targets_by_adapter": dict(sorted(Counter(row.get("adapter") for row in multinationals.get("employers", [])).items())),
            "global_countries_by_africa_flag": dict(sorted(Counter("african" if row.get("is_african") else "non_african" for row in global_countries.get("countries", [])).items())),
            "multinational_registry_city_footprint": dict(sorted(Counter(city for row in multinationals.get("employers", []) for city in row.get("cities", [])).items())),
        },
        "organisations": [
            {
                "id": org["id"],
                "name": org["name"],
                "organisation_type": org["organisation_type"],
                "career_families": org.get("career_families", []),
                "countries": org.get("countries", []),
                "adapters": [source["adapter"] for source in org.get("sources", [])],
                "enabled": org.get("enabled", True),
            }
            for org in org_rows
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="reports/registry_report.json")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    payload = build_registry_report(root)
    if payload["validation_errors"]:
        for error in payload["validation_errors"]:
            print(f"ERROR {error}")
        raise SystemExit(1)
    out = root / args.out
    write_json(out, payload)
    print(f"Wrote {out.relative_to(root)}")


if __name__ == "__main__":
    main()
