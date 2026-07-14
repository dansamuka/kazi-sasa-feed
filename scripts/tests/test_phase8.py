from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
REPO = SCRIPTS.parent
FIXTURES = Path(__file__).parent / "fixtures"
sys.path.insert(0, str(SCRIPTS))

from classifiers.ngo import NGOClassifier  # noqa: E402
from collectors.pageup import collect_pageup_target  # noqa: E402
from collectors.registry import collector_manifest  # noqa: E402
from phase2_enrichment import Phase2Enricher, legacy_projection  # noqa: E402
from refresh_feed import FEED_VERSION, FeedBuilder  # noqa: E402
from reporting import build_ngo_coverage_report  # noqa: E402
from verify_published_output import verify_feed, verify_site  # noqa: E402


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


class Response:
    def __init__(self, text): self.text = text
    def raise_for_status(self): return None


class Session:
    def __init__(self, html): self.html = html; self.calls = []
    def get(self, url, **kwargs): self.calls.append(url); return Response(self.html)


def builder(enriched=False):
    sources = load(REPO / "config/source_registry.json")
    enricher = None
    if enriched:
        enricher = Phase2Enricher(
            load(REPO / "config/organisations.json"),
            load(REPO / "config/african_locations.json"),
            load(REPO / "config/role_taxonomy.json"),
            sources,
            load(REPO / "config/investment_taxonomy.json"),
            load(REPO / "config/ngo_taxonomy.json"),
        )
    return FeedBuilder(load(REPO / "taxonomy.json"), sources, enricher=enricher)


def test_phase8_registry_has_priority_organisations_and_adapters():
    registry = load(REPO / "config/organisations.json")
    phase8 = [o for o in registry["organisations"] if o.get("source_pack") == "phase8_ngo_un_development"]
    assert len(phase8) >= 30
    adapters = {s["adapter"] for o in phase8 for s in o["sources"]}
    assert {"greenhouse", "recruitee", "oracle_cx", "successfactors", "pageup", "official_html"} <= adapters
    assert len(registry["organisations"]) >= 78


def test_pageup_is_registered_collector():
    manifest = {row["key"]: row for row in collector_manifest()}
    assert manifest["pageup"]["source_kind"] == "institution_official"


def test_pageup_fixture_extracts_official_job():
    html = (FIXTURES / "official_jobs.html").read_text(encoding="utf-8")
    b = builder()
    target = {
        "organisation_id": "unicef", "name": "UNICEF", "type": "multilateral",
        "organisation_type": "un_agency", "career_site_url": "https://jobs.unicef.org/",
        "default_specialisations": ["programme_management"], "verified": True,
    }
    assert collect_pageup_target(b, target, session=Session(html)) == 1
    assert b.opportunities[0]["source"]["name"] == "PageUp-hosted institutional board"
    assert b.opportunities[0]["apply_is_official"] is True


def test_reviewed_ngo_classifier_corpus():
    classifier = NGOClassifier(load(REPO / "config/ngo_taxonomy.json"))
    cases = load(REPO / "config/ngo_test_cases.json")["cases"]
    assert len(cases) >= 28
    for case in cases:
        result = classifier.classify({
            "title": case["title"],
            "organisation": {"type_detail": case["organisation_type"]},
            "specialisations": case.get("specialisations", []),
            "categories": case.get("specialisations", []),
        })
        assert result.classification == case["expected_classification"], case
        assert result.track == case["expected_track"], case
        assert result.is_programme_role is case["expected_programme_role"], case


def test_ngo_employer_does_not_turn_software_role_into_programme_role():
    b = builder(enriched=True)
    b.add({
        "id": "fixture-unicef-software", "title": "Software Engineer", "opportunity_type": "job",
        "organisation": {"name": "UNICEF", "type": "multilateral", "verified": True},
        "location": {"raw": "Nairobi, Kenya", "country": "Kenya", "scope": "local"},
        "categories": ["software_engineering"], "specialisations": ["software_engineering"],
        "industry": "technology", "source": {"name": "PageUp-hosted institutional board", "url": "https://jobs.unicef.org/", "confidence": "official"},
        "apply_url": "https://jobs.unicef.org/job/1", "apply_is_official": True, "flags": [],
    })
    profile = b.opportunities[0]["ngo_profile"]
    assert profile["is_ngo_or_un"] is True
    assert profile["classification"] == "institutional_support"
    assert profile["is_programme_role"] is False


def test_ngo_role_can_be_identified_outside_ngo_employer():
    result = NGOClassifier(load(REPO / "config/ngo_taxonomy.json")).classify({
        "title": "Monitoring and Evaluation Officer",
        "organisation": {"type_detail": "private"},
        "specialisations": ["monitoring_evaluation"],
    })
    assert result.track == "monitoring_evaluation_learning"
    assert result.is_programme_role is True
    assert result.is_ngo_or_un is False


def test_packaged_feed_has_phase8_profile_and_version():
    feed = load(REPO / "feed.json")
    assert FEED_VERSION == feed["meta"]["feed_version"] == "3.8"
    assert all("ngo_profile" in row for row in feed["opportunities"])
    assert all("ngo_profile" not in legacy_projection(row) for row in feed["opportunities"])


def test_phase8_coverage_report():
    report = build_ngo_coverage_report(load(REPO / "feed.json"))
    assert report["report_version"] == "1.0"
    assert report["summary"]["ngo_or_un_opportunity_count"] >= 1
    assert "by_track" in report["coverage"]


def test_phase8_publication_guard_and_site_markers():
    feed = load(REPO / "feed.json")
    assert verify_feed(feed, "3.8", True, None, require_phase4=True, require_phase5=True, require_phase6=True, require_phase7=True, require_phase8=True) == []
    html = (REPO / "docs/index.html").read_text(encoding="utf-8")
    assert verify_site(html, feed, require_phase3=True, require_phase6=True, require_phase7=True, require_phase8=True) == []
