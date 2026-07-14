from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
REPO = SCRIPTS.parent
FIXTURES = Path(__file__).parent / "fixtures"
sys.path.insert(0, str(SCRIPTS))

from collectors.cornerstone import collect_cornerstone_target  # noqa: E402
from collectors.official_html import collect_official_html_target  # noqa: E402
from collectors.oracle_cx import collect_oracle_cx_target  # noqa: E402
from collectors.successfactors import collect_successfactors_target  # noqa: E402
from collectors.registry import collector_manifest  # noqa: E402
from phase2_enrichment import Phase2Enricher, legacy_projection  # noqa: E402
from refresh_feed import FEED_VERSION, FeedBuilder  # noqa: E402
from reporting import build_dfi_coverage_report  # noqa: E402
from verify_published_output import verify_feed, verify_site  # noqa: E402


class Response:
    def __init__(self, *, text="", payload=None):
        self.text = text
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class OfficialSession:
    def __init__(self, html: str):
        self.html = html
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(("GET", url))
        return Response(text=self.html)


class OracleApiSession:
    def __init__(self, payload: dict):
        self.payload = payload
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        return Response(payload=self.payload)


class CornerstoneSession:
    def __init__(self, home: str, jobs: dict):
        self.home = home
        self.jobs = jobs
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(("GET", url))
        return Response(text=self.home)

    def post(self, url, **kwargs):
        self.calls.append(("POST", url))
        return Response(payload=self.jobs)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def builder(enriched: bool = False) -> FeedBuilder:
    taxonomy = load_json(REPO / "taxonomy.json")
    sources = load_json(REPO / "config/source_registry.json")
    enricher = None
    if enriched:
        enricher = Phase2Enricher(
            load_json(REPO / "config/organisations.json"),
            load_json(REPO / "config/african_locations.json"),
            load_json(REPO / "config/role_taxonomy.json"),
            sources,
            load_json(REPO / "config/investment_taxonomy.json"),
        )
    return FeedBuilder(taxonomy, sources, enricher=enricher)


def target(adapter: str, **overrides) -> dict:
    row = {
        "organisation_id": "world-bank-group",
        "name": "World Bank Group",
        "type": "multilateral",
        "organisation_type": "multilateral",
        "default_specialisations": ["project_finance"],
        "listing_url": "https://institution.example/jobs",
        "career_site_url": "https://institution.example/jobs",
        "identifier": "fixture",
        "verified": True,
    }
    row.update(overrides)
    return row



def test_official_html_does_not_publish_generic_careers_landing_page():
    b = builder()
    html = '<html><body><a href="/careers/about"><h2>Careers</h2></a></body></html>'
    t = target("official_html", link_patterns=[r"/careers/"])
    count = collect_official_html_target(b, t, session=OfficialSession(html))
    assert count == 0
    assert b.opportunities == []

def test_phase7_registry_has_priority_institutions_and_adapters():
    registry = load_json(REPO / "config/organisations.json")
    phase7 = [row for row in registry["organisations"] if row.get("source_pack") == "phase7_dfi_multilateral"]
    assert len(phase7) >= 25
    adapters = {source["adapter"] for row in phase7 for source in row["sources"]}
    assert {"cornerstone", "successfactors", "oracle_cx", "official_html"} <= adapters
    assert len(registry["organisations"]) >= 51


def test_collector_manifest_has_four_phase7_adapters():
    manifest = {row["key"]: row for row in collector_manifest()}
    for key in ("cornerstone", "successfactors", "oracle_cx", "official_html"):
        assert key in manifest
        assert manifest[key]["source_kind"] == "institution_official"


def test_official_html_jsonld_fixture():
    b = builder()
    html = (FIXTURES / "official_jobs.html").read_text(encoding="utf-8")
    count = collect_official_html_target(b, target("official_html"), session=OfficialSession(html))
    assert count == 1
    row = b.opportunities[0]
    assert row["apply_is_official"] is True
    assert row["title"] == "Investment Officer - Infrastructure"
    assert row["source"]["name"] == "DFI and multilateral official career page"


def test_successfactors_fixture_uses_distinct_source_name():
    b = builder()
    html = (FIXTURES / "official_jobs.html").read_text(encoding="utf-8")
    count = collect_successfactors_target(b, target("successfactors"), session=OfficialSession(html))
    assert count == 1
    assert b.opportunities[0]["source"]["name"] == "SuccessFactors-hosted institutional board"


def test_oracle_cx_fixture_uses_distinct_source_name():
    b = builder()
    html = (FIXTURES / "official_jobs.html").read_text(encoding="utf-8")
    count = collect_oracle_cx_target(b, target("oracle_cx"), session=OfficialSession(html))
    assert count == 1
    assert b.opportunities[0]["source"]["name"] == "Oracle Candidate Experience institutional board"


def test_oracle_cx_public_requisition_api_fixture():
    b = builder()
    payload = load_json(FIXTURES / "oracle_cx_jobs.json")
    session = OracleApiSession(payload)
    count = collect_oracle_cx_target(
        b,
        target("oracle_cx", site_number="CX_1001"),
        session=session,
    )
    assert count == 1
    row = b.opportunities[0]
    assert row["title"] == "Climate Investment Specialist"
    assert row["id"].startswith("oracle-cx-world-bank-group-")
    assert "hcmRestApi/resources/latest/recruitingCEJobRequisitions" in session.calls[0][1]


def test_cornerstone_public_search_fixture():
    b = builder()
    home = (FIXTURES / "cornerstone_home.html").read_text(encoding="utf-8")
    jobs = load_json(FIXTURES / "cornerstone_jobs.json")
    session = CornerstoneSession(home, jobs)
    count = collect_cornerstone_target(
        b,
        target("cornerstone", company="worldbankgroup", site_id=1, page_id=1),
        session=session,
    )
    assert count == 1
    row = b.opportunities[0]
    assert row["title"] == "Senior Investment Officer"
    assert row["source"]["name"] == "Cornerstone-hosted institutional board"
    assert any(method == "POST" for method, _ in session.calls)


def test_phase7_institution_profile_is_separate_from_role_classification():
    b = builder(enriched=True)
    b.add({
        "id": "fixture-software-at-wbg",
        "title": "Software Engineer",
        "opportunity_type": "job",
        "organisation": {"name": "World Bank Group", "type": "multilateral", "verified": True},
        "location": {"raw": "Nairobi, Kenya", "country": "Kenya", "scope": "local"},
        "categories": ["software_engineering"],
        "specialisations": ["software_engineering"],
        "industry": "technology",
        "source": {"name": "Cornerstone-hosted institutional board", "url": "https://institution.example", "confidence": "official"},
        "apply_url": "https://institution.example/software",
        "apply_is_official": True,
        "flags": [],
    })
    row = b.opportunities[0]
    assert row["institution_profile"]["is_dfi_or_multilateral"] is True
    assert row["institution_profile"]["phase7_priority_institution"] is True
    assert row["investment_profile"]["is_investment_role"] is False
    assert row["investment_profile"]["dfi_relevance"] == "institutional_role"


def test_dfi_coverage_report():
    feed = load_json(REPO / "seed.json")
    report = build_dfi_coverage_report(feed)
    assert report["report_version"] == "1.0"
    assert report["summary"]["dfi_or_multilateral_opportunity_count"] >= 0
    assert "by_institution" in report["coverage"]


def test_phase7_publication_guard_and_site_markers():
    feed = load_json(REPO / "feed.json")
    assert FEED_VERSION == "3.8"
    assert verify_feed(
        feed, "3.8", True, None,
        require_phase4=True, require_phase5=True, require_phase6=True, require_phase7=True,
    ) == []
    site = 'dfiInstitutionPill dfiRelevancePill "is_dfi_or_multilateral" "phase7_priority_institution" "institution_type"'
    assert verify_site(site, {"meta": {}}, require_phase7=True) == []


def test_packaged_phase7_migration_preserves_legacy_projection_shape():
    feed = load_json(FIXTURES / "legacy_packaged_feed.json")
    assert len(feed["opportunities"]) == 204
    assert all("institution_profile" in row for row in feed["opportunities"])
    # Presence of the profile must not alter the established Android projection.
    assert "institution_profile" not in legacy_projection(feed["opportunities"][0])
