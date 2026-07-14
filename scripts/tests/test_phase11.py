from __future__ import annotations

import json
from pathlib import Path

from collectors.smartrecruiters import collect_smartrecruiters_target
from collectors.workable import collect_workable_target
from collectors.workday import collect_workday_target
from phase2_enrichment import Phase2Enricher
from refresh_feed import FEED_VERSION, FeedBuilder
from reporting import build_multinational_coverage_report, build_public_institution_coverage_report
from verify_published_output import verify_feed, verify_site

REPO = Path(__file__).resolve().parents[2]


def load(relative: str):
    return json.loads((REPO / relative).read_text(encoding="utf-8"))


class Response:
    def __init__(self, payload):
        self.payload = payload
        self.status_code = 200
        self.headers = {}
        self.text = json.dumps(payload)

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class Session:
    def __init__(self, *, get_payload=None, post_payload=None):
        self.get_payload = get_payload
        self.post_payload = post_payload
        self.get_calls = []
        self.post_calls = []

    def get(self, url, **kwargs):
        self.get_calls.append((url, kwargs))
        return Response(self.get_payload)

    def post(self, url, **kwargs):
        self.post_calls.append((url, kwargs))
        return Response(self.post_payload)


def builder():
    return FeedBuilder(load("taxonomy.json"), load("config/source_registry.json"))


def enricher():
    return Phase2Enricher(
        load("config/organisations.json"), load("config/african_locations.json"),
        load("config/role_taxonomy.json"), load("config/source_registry.json"),
        load("config/investment_taxonomy.json"), load("config/ngo_taxonomy.json"),
    )


def test_phase11_registry_counts_and_requested_kenya_categories():
    public = load("config/kenya_public_institutions.json")
    multinationals = load("config/multinational_targets.json")
    assert len(public["institutions"]) == 60
    assert {row["category"] for row in public["institutions"]} == set(public["required_categories"])
    assert len(multinationals["employers"]) == multinationals["target_count"] == 100
    assert len({row["organisation_id"] for row in multinationals["employers"]}) == 100
    assert sum(bool(row["enabled"]) for row in multinationals["employers"]) >= 35


def test_phase11_profiles_are_additive_and_separate_employer_from_role():
    e = enricher()
    public = e.enrich({
        "id": "fixture-public", "title": "Software Engineer",
        "organisation": {"name": "Kenya Revenue Authority", "type": "employer", "verified": True},
        "location": {"raw": "Nairobi, Kenya", "country": "Kenya", "region": "East Africa", "is_remote_from_kenya": False, "scope": "local", "relocation_country": None},
        "categories": [], "specialisations": [], "industry": "technology", "source": {"name": "Kenya public institution official careers", "url": "https://example.org/job", "confidence": "official"},
        "apply_url": "https://example.org/job", "apply_is_official": True, "deadline_confidence": "unknown",
    })
    assert public["public_institution_profile"]["is_kenya_public_institution"] is True
    assert public["public_institution_profile"]["category"] == "revenue_authority"
    assert public["multinational_profile"]["is_multinational"] is False
    assert public["role_family"] != "government_administration"

    multi = e.enrich({
        "id": "fixture-multi", "title": "Legal Counsel",
        "organisation": {"name": "Standard Chartered", "type": "private", "verified": True},
        "location": {"raw": "Nairobi, Kenya", "country": "Kenya", "region": "East Africa", "is_remote_from_kenya": False, "scope": "local", "relocation_country": None},
        "categories": ["corporate_law"], "specialisations": ["corporate_law"], "industry": "legal", "source": {"name": "Multinational employer official careers", "url": "https://example.org/legal", "confidence": "official"},
        "apply_url": "https://example.org/legal", "apply_is_official": True, "deadline_confidence": "unknown",
    })
    assert multi["multinational_profile"]["is_multinational"] is True
    assert multi["multinational_profile"]["phase11_priority_employer"] is True
    assert multi["role_family"] == "legal"
    assert multi["investment_profile"]["is_investment_role"] is False


def test_workday_public_search_fixture():
    b = builder()
    session = Session(post_payload={"total": 1, "jobPostings": [{
        "id": "WD-1", "title": "Investment Analyst", "externalPath": "/job/Nairobi/Investment-Analyst_WD-1",
        "locationsText": "Nairobi, Kenya", "postedOn": "2026-07-13", "jobReqId": "WD-1",
    }]})
    target = {"organisation_id": "standard-bank-group", "name": "Standard Bank Group", "type": "private", "career_site_url": "https://standardbank.wd3.myworkdayjobs.com/StandardBankCareers"}
    assert collect_workday_target(b, target, session=session) == 1
    assert b.opportunities[0]["title"] == "Investment Analyst"
    assert session.post_calls[0][1]["json"]["offset"] == 0


def test_smartrecruiters_public_postings_fixture():
    b = builder()
    session = Session(get_payload={"totalFound": 1, "content": [{
        "id": "SR-1", "name": "Project Finance Manager", "ref": "https://jobs.smartrecruiters.com/acme/SR-1",
        "location": {"city": "Nairobi", "country": "Kenya"}, "releasedDate": "2026-07-13T08:00:00Z",
    }]})
    target = {"organisation_id": "visa", "name": "Visa", "type": "private", "company_identifier": "Visa"}
    assert collect_smartrecruiters_target(b, target, session=session) == 1
    assert b.opportunities[0]["organisation"]["name"] == "Visa"


def test_workable_public_postings_fixture():
    b = builder()
    session = Session(get_payload={"results": [{
        "shortcode": "WK-1", "title": "Country Operations Manager", "url": "https://apply.workable.com/acme/j/WK-1/",
        "location": {"city": "Accra", "country": "Ghana"}, "published": "2026-07-13T08:00:00Z",
    }]})
    target = {"organisation_id": "glovo", "name": "Glovo", "type": "private", "account_slug": "glovo"}
    assert collect_workable_target(b, target, session=session) == 1
    assert b.opportunities[0]["location"]["country"] == "Ghana"


def test_phase11_reports_and_publication_guards():
    feed = load("feed.json")
    assert FEED_VERSION == feed["meta"]["feed_version"] == "3.8"
    assert verify_feed(
        feed, "3.8", True, None, require_phase4=True, require_phase5=True,
        require_phase6=True, require_phase7=True, require_phase8=True,
        require_phase9=True, require_phase11=True,
    ) == []
    public_report = build_public_institution_coverage_report(feed, load("config/kenya_public_institutions.json"))
    multi_report = build_multinational_coverage_report(feed, load("config/multinational_targets.json"))
    assert public_report["summary"]["configured_institution_count"] == 60
    assert multi_report["summary"]["configured_employer_count"] == 100
    html = (REPO / "docs/index.html").read_text(encoding="utf-8")
    assert verify_site(html, feed, require_phase11=True) == []
