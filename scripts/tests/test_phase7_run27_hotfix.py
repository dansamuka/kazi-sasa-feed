"""Regression tests for GitHub Actions refresh-feed run #27."""
from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
REPO = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

from phase2_enrichment import Phase2Enricher  # noqa: E402
from refresh_feed import FeedBuilder  # noqa: E402
from validate_feed import validate_feed  # noqa: E402
from validate_registry import validate_all  # noqa: E402


def load(path: str) -> dict:
    return json.loads((REPO / path).read_text(encoding="utf-8"))


def builder(*, enriched: bool = False) -> FeedBuilder:
    taxonomy = load("taxonomy.json")
    sources = load("config/source_registry.json")
    enricher = None
    if enriched:
        enricher = Phase2Enricher(
            load("config/organisations.json"),
            load("config/african_locations.json"),
            load("config/role_taxonomy.json"),
            sources,
            load("config/investment_taxonomy.json"),
        )
    return FeedBuilder(taxonomy, sources, enricher=enricher)


def test_development_finance_is_canonical_and_registry_clean():
    taxonomy = load("taxonomy.json")
    role_taxonomy = load("config/role_taxonomy.json")
    specialisations = {row["id"]: row for row in taxonomy["specialisations"]}
    assert specialisations["development_finance"]["industry"] == "financial_services"
    assert role_taxonomy["specialisation_role_family_map"]["development_finance"] == "development_programmes"
    assert set(role_taxonomy["thematic_sector_map"]["development_finance"]) == {
        "finance", "development", "public_sector"
    }
    assert validate_all(REPO) == []


def test_development_finance_default_validates_without_becoming_investment():
    b = builder(enriched=True)
    b.add({
        "id": "fixture-afdb-administration",
        "title": "Administrative Assistant",
        "opportunity_type": "job",
        "organisation": {"name": "African Development Bank", "type": "multilateral", "verified": True},
        "location": {"raw": "Abidjan, Côte d’Ivoire", "country": "Côte d’Ivoire", "scope": "local"},
        "categories": ["development_finance"],
        "specialisations": ["development_finance"],
        "industry": "financial_services",
        "source": {"name": "DFI and multilateral official career page", "url": "https://www.afdb.org", "confidence": "official"},
        "apply_url": "https://www.afdb.org/jobs/administrative-assistant",
        "apply_is_official": True,
        "flags": [],
    })
    row = b.opportunities[0]
    assert row["role_subfamily"] == "development_finance"
    assert row["role_family"] == "development_programmes"
    assert row["investment_profile"]["is_investment_role"] is False
    assert row["institution_profile"]["is_dfi_or_multilateral"] is True
    result = validate_feed(b.build(), b.taxonomy, load("config/role_taxonomy.json"))
    assert result.errors == []
    assert result.warnings == []


def test_run27_himalayas_terms_are_mapped_or_deliberately_ignored(capsys):
    terms = [
        "Senior-Data-Engineer-Positions", "Senior-Data-Analytics-Engineer",
        "Senior-Data-Management-Engineer", "Data-Engineer", "Data-Entry",
        "&-Administration", "Administrative-Support", "Data-Management",
        "Data-Entry-Associate", "Data-Entry-Agent", "Data-Entry-Clerk",
        "Data-Entry-Operator", "Data-Entry-Specialist", "Data-Entry-Executive",
        "Data-Entry-Coordinator", "Data-Entry-Jobs", "Data-Entry-&-Administrative",
        "Integrated-Designer", "Motion-Graphics-Designer", "Digital-Designer",
        "Graphic-Designer", "Social-Media-Designer",
    ]
    mapped = builder().map_specialisations(terms, source_key="himalayas", limit=100)
    assert set(mapped) == {"data_engineering", "data_entry", "graphic_design"}
    assert "unmapped" not in capsys.readouterr().err


def test_official_defaults_pass_through_canonical_mapper(capsys):
    b = builder()
    assert b.map_specialisations(["development_finance"], source_key="official_html") == ["development_finance"]
    assert "unmapped" not in capsys.readouterr().err


def test_afdb_official_collector_path_is_clean_end_to_end():
    from collectors.official_html import collect_official_html_target

    class Response:
        text = (REPO / "scripts/tests/fixtures/official_jobs.html").read_text(encoding="utf-8")
        def raise_for_status(self):
            return None

    class Session:
        def get(self, url, **kwargs):
            return Response()

    b = builder(enriched=True)
    count = collect_official_html_target(
        b,
        {
            "organisation_id": "african-development-bank",
            "name": "African Development Bank",
            "type": "multilateral",
            "organisation_type": "development_bank",
            "listing_url": "https://www.afdb.org/en/about-careers/current-vacancies",
            "identifier": "https://www.afdb.org/en/about-careers/current-vacancies",
            "default_specialisations": ["development_finance"],
            "link_patterns": [r"/jobs/"],
            "exclude_patterns": [],
            "verified": True,
        },
        session=Session(),
    )
    assert count == 1
    row = b.opportunities[0]
    assert "development_finance" in row["source_context_specialisations"]
    assert "development_finance" not in row["specialisations"]
    result = validate_feed(b.build(), b.taxonomy, load("config/role_taxonomy.json"))
    assert result.errors == []
    assert result.warnings == []
