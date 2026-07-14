"""Phase 6 investment and DFI taxonomy/classification tests."""
from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
REPO = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

from classifiers.investment import InvestmentClassifier  # noqa: E402
from phase2_enrichment import Phase2Enricher  # noqa: E402
from reporting import build_investment_coverage_report  # noqa: E402
from validate_feed import validate_feed  # noqa: E402
from verify_published_output import verify_feed, verify_site  # noqa: E402


def _load(path: str):
    return json.loads((REPO / path).read_text(encoding="utf-8"))


def _classifier() -> InvestmentClassifier:
    return InvestmentClassifier(_load("config/investment_taxonomy.json"))


def _enricher() -> Phase2Enricher:
    return Phase2Enricher(
        _load("config/organisations.json"),
        _load("config/african_locations.json"),
        _load("config/role_taxonomy.json"),
        _load("config/source_registry.json"),
        _load("config/investment_taxonomy.json"),
    )


def _opportunity(title: str, org_type: str = "private", summary: str = "", specialisations=None):
    return {
        "id": "phase6-test",
        "title": title,
        "opportunity_type": "job",
        "organisation": {"name": "Example", "type": "private", "type_detail": org_type, "verified": True},
        "location": {
            "raw": "Nairobi, Kenya", "country": "Kenya", "region": None,
            "is_remote_from_kenya": False, "scope": "national", "relocation_country": None,
        },
        "source": {"name": "Example", "url": "https://example.org/jobs/1", "confidence": "official"},
        "apply_url": "https://example.org/jobs/1",
        "summary": summary,
        "specialisations": specialisations or [],
        "categories": specialisations or [],
        "flags": [],
        "deadline_confidence": "unknown",
    }


def test_investment_taxonomy_has_26_reviewed_tracks_and_unique_canonical_specialisations():
    taxonomy = _load("config/investment_taxonomy.json")
    tracks = taxonomy["tracks"]
    assert len(tracks) == 26
    assert len({row["id"] for row in tracks}) == 26
    assert len({row["canonical_specialisation"] for row in tracks}) == 26
    assert {"project_finance", "infrastructure_finance", "climate_finance", "private_equity", "venture_capital", "syndications"} <= {row["id"] for row in tracks}


def test_reviewed_99_case_regression_corpus_is_exact():
    corpus = _load("config/investment_test_cases.json")
    assert corpus["case_count"] == len(corpus["cases"]) == 99
    classifier = _classifier()
    for case in corpus["cases"]:
        result = classifier.classify({
            "title": case["title"],
            "summary": case.get("summary"),
            "specialisations": case.get("specialisations", []),
            "organisation": {"type_detail": case.get("organisation_type", "private")},
        })
        assert result.classification == case["expected_classification"], case["title"]
        assert result.track == case.get("expected_track"), case["title"]


def test_specific_track_beats_generic_investment_title_phrase():
    result = _classifier().classify(_opportunity("Financial Institutions Investment Officer"))
    assert result.track == "financial_institutions"
    assert result.classification == "core_investment"


def test_accounting_title_is_not_promoted_by_investment_company_description():
    result = _classifier().classify(_opportunity(
        "Financial Accountant", summary="Join a leading investment and portfolio management company."
    ))
    assert result.classification == "not_investment"
    assert result.is_investment_role is False
    assert result.negative_evidence


def test_support_role_at_dfi_is_institutional_not_investment():
    result = _classifier().classify(_opportunity("Software Engineer", org_type="dfi", summary="Support investment systems."))
    assert result.classification == "institutional_support"
    assert result.dfi_relevance == "institutional_role"
    assert result.is_investment_role is False


def test_direct_investment_role_at_dfi_has_direct_dfi_relevance():
    result = _classifier().classify(_opportunity("Investment Officer, Infrastructure", org_type="dfi"))
    assert result.is_investment_role is True
    assert result.dfi_relevance == "direct_investment"
    assert result.dfi_confidence >= 0.9


def test_multilingual_titles_are_classified():
    classifier = _classifier()
    assert classifier.classify(_opportunity("Responsable Financement de Projets")).track == "project_finance"
    assert classifier.classify(_opportunity("Gestor de Investimentos")).track == "investment_operations"
    assert classifier.classify(_opportunity("محلل استثمار")).track == "investment_analysis"


def test_enricher_promotes_investment_role_family_without_mutating_legacy_specialisations():
    opportunity = _opportunity("Project Finance Manager", specialisations=["general_finance"])
    enriched = _enricher().enrich(opportunity)
    assert enriched["role_family"] == "investment"
    assert enriched["role_subfamily"] == "project_finance"
    assert enriched["specialisations"] == ["general_finance"]
    assert enriched["investment_profile"]["track"] == "project_finance"


def test_packaged_feed_has_phase6_profile_on_every_record():
    feed = _load("feed.json")
    assert feed["meta"]["feed_version"] == "3.8"
    assert feed["meta"]["investment_taxonomy_version"] == "1.0"
    assert feed["meta"]["investment_classifier_version"] == "1.0"
    required = {
        "classification", "track", "canonical_specialisation", "confidence",
        "evidence", "negative_evidence", "dfi_relevance", "dfi_confidence",
        "is_investment_role",
    }
    for opportunity in feed["opportunities"]:
        assert required <= set(opportunity["investment_profile"])


def test_phase6_validator_rejects_invalid_track_and_inconsistent_role_family():
    feed = _load("feed.json")
    opportunity = dict(feed["opportunities"][0])
    opportunity["investment_profile"] = dict(opportunity["investment_profile"])
    opportunity["investment_profile"]["track"] = "invented_track"
    opportunity["investment_profile"]["is_investment_role"] = True
    opportunity["role_family"] = "technology"
    candidate = {"meta": dict(feed["meta"], opportunity_count=1), "opportunities": [opportunity]}
    result = validate_feed(candidate, _load("taxonomy.json"), _load("config/role_taxonomy.json"))
    assert any("investment_profile.track" in error for error in result.errors)
    assert any("investment roles must use role_family" in error for error in result.errors)


def test_phase6_investment_report_matches_feed():
    feed = _load("feed.json")
    report = build_investment_coverage_report(feed)
    expected = sum(1 for row in feed["opportunities"] if row["investment_profile"]["is_investment_role"])
    assert report["summary"]["investment_role_count"] == expected
    assert report["summary"]["opportunity_count"] == len(feed["opportunities"])


def test_phase6_publication_guard_and_site_markers():
    feed = _load("feed.json")
    assert verify_feed(
        feed, "3.8", True, None, require_phase4=True, require_phase5=True, require_phase6=True
    ) == []
    html = (REPO / "docs/index.html").read_text(encoding="utf-8")
    assert verify_site(html, feed, require_phase3=True, require_phase6=True) == []


def test_workflow_publishes_and_guards_phase6_outputs():
    workflow = (REPO / ".github/workflows/refresh-feed.yml").read_text(encoding="utf-8")
    assert "--expected-version 3.8" in workflow
    assert "--require-phase6" in workflow
    assert "--require-phase6-site" in workflow
    assert "reports/investment_coverage_report.json" in workflow
    template = (REPO / "scripts/site/template.html").read_text(encoding="utf-8")
    assert "investmentClassPill" in template
    assert "investmentTrackPill" in template


def test_new_investment_specialisations_are_fully_mapped():
    taxonomy = _load("taxonomy.json")
    roles = _load("config/role_taxonomy.json")
    investment = _load("config/investment_taxonomy.json")
    valid = {row["id"] for row in taxonomy["specialisations"]}
    canonical = {row["canonical_specialisation"] for row in investment["tracks"]}
    assert canonical <= valid
    assert canonical <= set(roles["specialisation_role_family_map"])
