"""Phase 5 public-source expansion, deduplication, and coverage-gate tests."""
from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
REPO = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

from collectors.registry import collector_manifest, default_collector_specs  # noqa: E402
from coverage_gates import evaluate_coverage_gates  # noqa: E402
from pipeline.deduplicate import canonical_url, deduplicate_opportunities  # noqa: E402
from registry import adapter_boards, load_organisation_registry  # noqa: E402
from verify_published_output import verify_feed  # noqa: E402


def _load(path: str):
    return json.loads((REPO / path).read_text(encoding="utf-8"))


def _opportunity(opp_id: str, source: str, confidence: str, official: bool, city="Nairobi") -> dict:
    return {
        "id": opp_id,
        "title": "Investment Analyst",
        "organisation": {"name": "Example Capital", "verified": True},
        "location": {"country_code": "KE", "country": "Kenya", "city": city},
        "source": {"name": source, "confidence": confidence, "kind": "employer_ats" if official else "institutional_aggregator"},
        "apply_url": "https://example.org/jobs/123?utm_source=test" if official else "https://reliefweb.int/node/123",
        "raw_description_url": "https://example.org/jobs/123" if official else "https://reliefweb.int/node/123",
        "apply_is_official": official,
        "summary": "Support investment analysis and portfolio management across East Africa. " * 3,
        "role_family": "investment",
    }


def test_phase5_registry_adds_recruitee_and_five_verified_boards():
    registry = load_organisation_registry(REPO / "config/organisations.json")
    boards = adapter_boards(registry, "recruitee")
    assert len(boards) == 5
    assert {row["subdomain"] for row in boards} >= {"triplejump", "msf", "medecinssansfrontiereswaca"}


def test_phase5_collector_registry_contains_13_sources():
    keys = [spec.key for spec in default_collector_specs()]
    assert len(keys) >= 17
    assert {"recruitee", "untalent", "reliefweb", "adzuna"} <= set(keys)
    manifest = collector_manifest()
    assert next(row for row in manifest if row["key"] == "untalent")["required_env"] == ["UNTALENT_FEED_URL"]
    assert next(row for row in manifest if row["key"] == "reliefweb")["configured"] is True


def test_official_record_replaces_aggregator_duplicate():
    aggregator = _opportunity("reliefweb-123", "ReliefWeb", "aggregated", False)
    official = _opportunity("greenhouse-example-123", "Example Capital", "official", True)
    output, report = deduplicate_opportunities([aggregator, official])
    assert len(output) == 1
    assert output[0]["id"] == "greenhouse-example-123"
    assert report["removed_count"] == 1
    assert report["official_replacements"] == 1


def test_semantically_similar_roles_in_different_cities_are_not_deduplicated():
    nairobi = _opportunity("a", "Employer", "official", True, city="Nairobi")
    lagos = _opportunity("b", "Employer", "official", True, city="Lagos")
    lagos["apply_url"] = "https://example.org/jobs/456"
    lagos["raw_description_url"] = lagos["apply_url"]
    output, report = deduplicate_opportunities([nairobi, lagos])
    assert len(output) == 2
    assert report["removed_count"] == 0


def test_canonical_url_removes_tracking_parameters():
    assert canonical_url("http://www.example.org/jobs/1/?utm_source=x&ref=y&a=2") == "https://example.org/jobs/1?a=2"


def test_packaged_feed_passes_regression_coverage_gates():
    report = evaluate_coverage_gates(_load("feed.json"), _load("config/coverage_gates.json"))
    assert report["errors"] == []
    assert report["status"] == "passed"
    assert report["warnings"]


def test_phase5_publication_metadata_and_guard():
    feed = _load("feed.json")
    assert feed["meta"]["feed_version"] == "3.8"
    assert feed["meta"]["source_expansion_version"] == "1.0"
    assert feed["meta"]["deduplication_version"] == "2.0"
    assert verify_feed(feed, "3.8", True, None, require_phase4=True, require_phase5=True) == []


def test_adzuna_priority_search_portfolio_contains_core_lanes():
    searches = _load("config/adzuna_queries.json")["searches"]
    queries = {row["query"] for row in searches}
    assert {None, "investment", "project finance", "climate finance", "international development", "NGO", "public sector"} <= queries


def test_workflow_publishes_phase5_reports_and_optional_untalent_config():
    workflow = (REPO / ".github/workflows/refresh-feed.yml").read_text(encoding="utf-8")
    assert "UNTALENT_FEED_URL" in workflow
    assert "reports/deduplication_report.json" in workflow
    assert "reports/coverage_gate_report.json" in workflow
    assert "--require-phase5" in workflow
    assert "scripts/coverage_gates.py" in workflow


def test_generic_unknown_employers_are_not_semantically_deduplicated():
    first = _opportunity("unknown-a", "Adzuna", "aggregated", False)
    second = _opportunity("unknown-b", "Adzuna", "aggregated", False)
    for row, url in ((first, "https://example.org/jobs/a"), (second, "https://example.org/jobs/b")):
        row["organisation"] = {"name": "Unknown Employer", "verified": False}
        row["apply_url"] = url
        row["raw_description_url"] = url
    output, report = deduplicate_opportunities([first, second])
    assert len(output) == 2
    assert report["removed_count"] == 0
