"""Regression tests for live GitHub Actions run #24 failures."""
from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
REPO = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

from coverage_gates import evaluate_coverage_gates, is_explicit_location_neutral  # noqa: E402
from refresh_feed import FeedBuilder  # noqa: E402


def _builder() -> FeedBuilder:
    return FeedBuilder(
        json.loads((REPO / "taxonomy.json").read_text(encoding="utf-8")),
        json.loads((REPO / "sources.json").read_text(encoding="utf-8")),
    )


def _row(index: int, *, country: str | None = "KE", neutral: bool = False) -> dict:
    location = {"country_code": country, "region_canonical": "East Africa" if country else None}
    row = {
        "id": f"row-{index}",
        "source": {"name": "Example"},
        "location": location,
        "apply_is_official": True,
    }
    if neutral:
        row.update({
            "work_mode": "remote_global",
            "location": {"country_code": None, "raw": "Remote, EMEA", "scope": "international"},
            "eligibility": {"evidence": ["remote_regional_or_africa"]},
        })
    return row


def _gate_config(limit: int = 10) -> dict:
    return {
        "regression_gates": {
            "minimum_by_region": {},
            "max_unresolved_location_percent": limit,
            "max_single_country_percent": 100,
            "max_single_source_percent": 100,
            "minimum_official_apply_records": 0,
        },
        "phase5_targets": {"minimum_by_region": {}},
    }


def test_explicit_remote_emea_role_is_location_neutral_not_unknown():
    row = _row(1, country=None, neutral=True)
    assert is_explicit_location_neutral(row) is True


def test_location_neutral_roles_do_not_trip_unknown_location_gate():
    rows = [_row(i) for i in range(87)]
    rows += [_row(100 + i, country=None, neutral=True) for i in range(12)]
    rows += [_row(999, country=None, neutral=False)]
    report = evaluate_coverage_gates({"meta": {}, "opportunities": rows}, _gate_config())
    assert report["errors"] == []
    assert report["metrics"]["location_neutral_records"] == 12
    assert report["metrics"]["unresolved_location_records"] == 1
    assert report["metrics"]["unresolved_location_percent"] == 1.0


def test_genuinely_unresolved_locations_still_fail_gate():
    rows = [_row(i) for i in range(89)] + [_row(100 + i, country=None) for i in range(11)]
    report = evaluate_coverage_gates({"meta": {}, "opportunities": rows}, _gate_config())
    assert any("unresolved-location share" in error for error in report["errors"])


def test_run24_himalayas_terms_are_mapped_or_intentionally_ignored(capsys):
    terms = [
        "Corporate-Development", "Strategy", "Business-Development", "M&A-Advisory",
        "Executive-Leadership", "Operations-Associate", "Project-Coordinator",
        "Operations-Management", "Project-Management", "Business-Operations",
        "Supply-Chain-Management", "Sourcing", "OPS-SC", "UX-Design", "UI-Design",
        "Senior-UX-Design", "Digital-Design", "Marketing-Design", "Media-Buying",
        "Digital-Advertising", "Creative-Production", "Paid-Social", "Graphic-Design",
        "Case-Management", "Care-Coordination", "Patient-Advocacy", "Healthcare",
        "Medical-Case-Management", "Enterprise-Architecture", "Solution-Architecture",
        "IT-Architecture", "Technical-Architecture", "Project-Leadership",
        "Banking-Technical-Consultant", "SAP-Consulting", "Banking",
        "Information-Technology-And-Services", "Technical-Consulting",
        "&-Customer-Success", "Hospital-&-Health-Care", "French-Customer-Service",
        "Healthcare-Customer-Support", "Bilingual-Customer-Support",
    ]
    mapped = _builder().map_specialisations(terms, source_key="himalayas", limit=100)
    assert {"corporate_finance", "investment_banking", "programme_management", "ux_ui_design", "health_administration", "technical_assistance"} <= set(mapped)
    assert "unmapped" not in capsys.readouterr().err


def test_run24_remotive_and_jobicy_terms_map_cleanly(capsys):
    b = _builder()
    assert b.map_specialisations(["Writing", "Customer Service", "Software Development"], source_key="remotive") == ["content_marketing", "customer_success", "general_engineering"]
    assert b.map_specialisation("HR & Recruiting", source_key="jobicy") == "talent_acquisition"
    assert "unmapped" not in capsys.readouterr().err
