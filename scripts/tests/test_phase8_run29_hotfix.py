from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
REPO = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

from collectors.official_common import extract_page_location, opportunity_from_page  # noqa: E402
from coverage_gates import (  # noqa: E402
    evaluate_coverage_gates,
    is_official_location_pending,
)
from refresh_feed import FeedBuilder  # noqa: E402


def load(path: str):
    return json.loads((REPO / path).read_text(encoding="utf-8"))


def builder():
    return FeedBuilder(load("taxonomy.json"), load("config/source_registry.json"))


def target():
    return {
        "organisation_id": "unicef",
        "name": "UNICEF",
        "type": "multilateral",
        "organisation_type": "un_agency",
        "listing_url": "https://jobs.example.org/search",
        "default_specialisations": ["programme_management"],
        "verified": True,
    }


def gate_config():
    return {
        "regression_gates": {
            "minimum_by_region": {},
            "max_unresolved_location_percent": 10,
            "max_official_location_pending_percent": 25,
            "max_single_country_percent": 100,
            "max_single_source_percent": 100,
            "minimum_official_apply_records": 0,
        },
        "phase5_targets": {},
    }


def official_row(*, row_id: str, apply_url: str, location=None):
    return {
        "id": row_id,
        "title": "Programme Officer",
        "organisation": {"name": "UNICEF", "verified": True},
        "location": location or {"raw": None, "country_code": None},
        "source": {
            "name": "PageUp-hosted institutional board",
            "url": "https://jobs.example.org/search",
            "confidence": "official",
            "kind": "institution_official",
        },
        "apply_url": apply_url,
        "raw_description_url": apply_url,
        "apply_is_official": True,
        "summary": "Manage a country programme and partner delivery.",
    }


def test_run29_location_label_extraction_from_definition_list():
    html = """
    <html><body><h1>Programme Officer</h1>
      <dl><dt>Duty station</dt><dd>Nairobi, Kenya</dd></dl>
    </body></html>
    """
    assert extract_page_location(html, title="Programme Officer") == "Nairobi, Kenya"


def test_run29_location_label_extraction_is_multilingual():
    html = """
    <html><body><h1>Chargé de programme</h1>
      <p>Lieu d’affectation: Abidjan, Côte d’Ivoire</p>
    </body></html>
    """
    assert extract_page_location(html, title="Chargé de programme") == "Abidjan, Côte d’Ivoire"


def test_run29_official_page_uses_labelled_detail_location():
    html = """
    <html><body><h1>Monitoring and Evaluation Officer</h1>
      <div><strong>Location:</strong><span>Kampala, Uganda</span></div>
      <p>Lead monitoring, evaluation and learning.</p>
    </body></html>
    """
    row = opportunity_from_page(
        builder(), target(), title="MEL Officer", url="https://jobs.example.org/job/123",
        page_html=html, context_text="MEL Officer", source_name="NGO and UN official career page",
        prefix="official",
    )
    assert row is not None
    assert row["location"]["country_code"] == "UG"
    assert row["location"]["city"] == "Kampala"


def test_run29_official_missing_location_is_separate_pending_bucket():
    row = official_row(row_id="official-1", apply_url="https://jobs.example.org/job/1")
    assert is_official_location_pending(row) is True
    physical = [
        official_row(
            row_id=f"physical-{i}",
            apply_url=f"https://jobs.example.org/job/p{i}",
            location={"raw": "Nairobi, Kenya", "country_code": "KE", "region_canonical": "East Africa"},
        )
        for i in range(4)
    ]
    report = evaluate_coverage_gates({"meta": {}, "opportunities": [row, *physical]}, gate_config())
    assert report["status"] == "passed"
    assert report["metrics"]["official_location_pending_records"] == 1
    assert report["metrics"]["unresolved_location_records"] == 0


def test_run29_aggregator_missing_location_remains_unresolved():
    row = official_row(row_id="agg-1", apply_url="https://aggregator.example/job/1")
    row["organisation"]["verified"] = False
    row["source"] = {
        "name": "Commercial Aggregator",
        "url": "https://aggregator.example",
        "confidence": "aggregated",
        "kind": "commercial_aggregator",
    }
    row["apply_is_official"] = False
    report = evaluate_coverage_gates({"meta": {}, "opportunities": [row]}, gate_config())
    assert report["status"] == "failed"
    assert report["metrics"]["unresolved_location_records"] == 1
    assert report["metrics"]["official_location_pending_records"] == 0


def test_run29_pending_official_locations_are_still_capped():
    rows = [official_row(row_id=f"official-{i}", apply_url=f"https://jobs.example.org/job/{i}") for i in range(3)]
    rows.extend([
        official_row(
            row_id=f"physical-{i}",
            apply_url=f"https://jobs.example.org/job/p{i}",
            location={"raw": "Nairobi, Kenya", "country_code": "KE", "region_canonical": "East Africa"},
        )
        for i in range(7)
    ])
    config = gate_config()
    config["regression_gates"]["max_official_location_pending_percent"] = 20
    report = evaluate_coverage_gates({"meta": {}, "opportunities": rows}, config)
    assert report["status"] == "failed"
    assert any("official-location-pending" in error for error in report["errors"])


def test_run29_himalayas_terms_are_mapped_or_deliberately_ignored(capsys):
    terms = [
        "Senior-Full-Stack-Engineer",
        "Senior-Full-Stack-Engineer-(TypeScript-Angular-Node)",
        "Brand-Director",
        "Brand-Creative-Director",
        "Brand-Design-Lead",
        "Brand-Design-Manager",
        "Design-Director",
        "Graphic-Design-Director",
        "Data-Engineering",
        "Data-Platform-Engineering",
        "Analytics-Engineering",
        "Tech",
        "Automotive",
        "Senior-Data-Engineer",
        "Senior-Data-Engineering",
        "Data-Senior-Engineer",
        "Data-Engineer-Senior",
        "Senior-Staff-Data-Engineer",
        "Senior-Data-Engineer-Jobs",
        "Senior-Principal-Data-Engineer",
    ]
    mapped = builder().map_specialisations(terms, source_key="himalayas", limit=100)
    captured = capsys.readouterr()
    assert "unmapped" not in captured.err
    assert {"general_engineering", "brand_management", "graphic_design", "data_engineering"} <= set(mapped)
