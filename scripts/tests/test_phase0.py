"""Phase 0 governance, mapping, reporting and mobility-regression tests."""
from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
REPO = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

from collectors._common import (  # noqa: E402
    has_role_specific_mobility_signal,
    is_relevant_opportunity,
    parse_location,
)
from refresh_feed import FEED_VERSION, FeedBuilder  # noqa: E402
from reporting import build_coverage_report  # noqa: E402
from validate_sources import validate_sources  # noqa: E402


def _builder() -> FeedBuilder:
    taxonomy = json.loads((REPO / "taxonomy.json").read_text(encoding="utf-8"))
    sources = json.loads((REPO / "sources.json").read_text(encoding="utf-8"))
    return FeedBuilder(taxonomy, sources)


def test_feed_builder_defaults_to_current_additive_schema():
    assert _builder().build()["meta"]["feed_version"] == FEED_VERSION == "3.8"


def test_labels_are_valid_aliases():
    assert _builder().map_specialisation("Data Engineering") == "data_engineering"


def test_source_specific_taxonomy_mapping():
    assert _builder().map_specialisation("2317 Marketing - PMM", "greenhouse:stripe") == "general_marketing"


def test_ignored_broad_source_category_is_dropped():
    assert _builder().map_specialisation("Manufacturing Jobs", "adzuna") is None


def test_unknown_specialisation_never_leaks_raw_value():
    assert _builder().map_specialisation("Opaque Internal Department", "greenhouse:example") is None


def test_generic_company_sponsorship_boilerplate_is_not_role_specific():
    text = "Our company supports immigration and visa sponsorship for employees across the business."
    assert has_role_specific_mobility_signal(text) is False
    assert is_relevant_opportunity(parse_location("New York, United States"), text) is False


def test_role_specific_sponsorship_can_preserve_a_real_mobility_role():
    text = "Visa sponsorship is available for this position for international candidates."
    assert has_role_specific_mobility_signal(text) is True
    assert is_relevant_opportunity(parse_location("London, United Kingdom"), text) is True


def test_sources_registry_is_clean():
    sources = json.loads((REPO / "sources.json").read_text(encoding="utf-8"))
    assert validate_sources(sources) == []


def test_sources_registry_rejects_duplicate_domain():
    data = {
        "sources": [
            {"name": "A", "domain": "example.com", "default_confidence": "official"},
            {"name": "B", "domain": "example.com", "default_confidence": "aggregated"},
        ],
        "default_for_unknown_source": "unverified",
    }
    assert any("domain 'example.com'" in error for error in validate_sources(data))


def test_coverage_report_counts_completeness():
    feed = _builder().build()
    feed["opportunities"] = [{
        "id": "x",
        "opportunity_type": "job",
        "organisation": {"name": "Org", "type": "private"},
        "location": {"country": "Kenya", "scope": "national"},
        "source": {"name": "Source", "confidence": "official"},
        "industry": "technology",
        "specialisations": ["data_engineering"],
        "work_mode": "hybrid",
        "apply_is_official": True,
        "contract_type": "permanent",
    }]
    report = build_coverage_report(feed)
    assert report["summary"]["opportunity_count"] == 1
    assert report["data_completeness"]["country"]["percent"] == 100.0
