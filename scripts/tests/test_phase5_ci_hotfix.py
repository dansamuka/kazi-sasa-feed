"""Regression tests for live GitHub Actions run #23 failures."""
from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
REPO = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

from collectors.adzuna import collect_adzuna  # noqa: E402
from collectors.jobicy import collect_jobicy  # noqa: E402
from collectors.recruitee import collect_recruitee_board  # noqa: E402
from normalizers.temporal import normalise_datetime  # noqa: E402
from refresh_feed import FeedBuilder  # noqa: E402
from validate_feed import validate_feed  # noqa: E402


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, payload):
        self.payload = payload

    def get(self, *args, **kwargs):
        return FakeResponse(self.payload)


def builder() -> FeedBuilder:
    taxonomy = json.loads((REPO / "taxonomy.json").read_text(encoding="utf-8"))
    sources = json.loads((REPO / "sources.json").read_text(encoding="utf-8"))
    return FeedBuilder(taxonomy, sources)


def test_recruitee_sql_style_utc_timestamp_is_normalised():
    assert normalise_datetime("2026-07-06 07:30:06 UTC") == "2026-07-06T07:30:06Z"


def test_recruitee_live_timestamp_shape_passes_feed_validation():
    payload = {
        "offers": [{
            "id": 2667266,
            "title": "Medical Coordinator",
            "description": "Support health programmes across Africa.",
            "locations": [{"name": "Nairobi, Kenya"}],
            "published_at": "2026-07-06 07:30:06 UTC",
            "careers_url": "https://msf.recruitee.com/o/medical-coordinator",
            "status": "published",
        }]
    }
    b = builder()
    assert collect_recruitee_board(
        b,
        {"subdomain": "msf", "name": "Médecins Sans Frontières", "type": "ngo"},
        session=FakeSession(payload),
    ) == 1
    assert b.opportunities[0]["posted_at"] == "2026-07-06T07:30:06Z"
    feed = b.build()
    result = validate_feed(feed, b.taxonomy)
    assert result.errors == []


def test_impossible_deadline_is_dropped_without_dropping_adzuna_job():
    payload = {
        "results": [{
            "id": "5768865147",
            "title": "Finance Manager",
            "description": "Closing date: 29 April 2026. Lead finance operations.",
            "company": {"display_name": "Example Employer"},
            "location": {"display_name": "Cape Town, South Africa", "area": ["South Africa", "Western Cape", "Cape Town"]},
            "category": {"label": "Accounting & Finance Jobs"},
            "created": "2026-06-19T04:37:03Z",
            "redirect_url": "https://www.adzuna.co.za/job/5768865147",
        }]
    }
    b = builder()
    assert collect_adzuna(b, "id", "key", max_pages=1, session=FakeSession(payload)) == 1
    opp = b.opportunities[0]
    assert opp["posted_at"] == "2026-06-19T04:37:03Z"
    assert opp["deadline"] is None
    assert opp["deadline_confidence"] == "unknown"
    assert opp["data_quality"]["deadline_dropped"] == "before_posted_at"
    result = validate_feed(b.build(), b.taxonomy)
    assert result.errors == []


def test_jobicy_html_escaped_categories_map_cleanly(capsys):
    payload = {
        "jobs": [
            {
                "id": 1,
                "jobTitle": "Compliance Counsel",
                "companyName": "Example",
                "jobGeo": "Worldwide",
                "jobIndustry": "Legal &amp; Compliance",
                "jobType": "full-time",
                "pubDate": "2026-07-01T10:00:00Z",
                "jobDescription": "Support compliance across global operations.",
                "url": "https://jobicy.com/jobs/1",
            },
            {
                "id": 2,
                "jobTitle": "Finance Analyst",
                "companyName": "Example",
                "jobGeo": "Worldwide",
                "jobIndustry": "Finance &amp; Accounting",
                "jobType": "full-time",
                "pubDate": "2026-07-01T10:00:00Z",
                "jobDescription": "Support finance across global operations.",
                "url": "https://jobicy.com/jobs/2",
            },
            {
                "id": 3,
                "jobTitle": "Product Operations Manager",
                "companyName": "Example",
                "jobGeo": "Worldwide",
                "jobIndustry": "Product &amp; Operations",
                "jobType": "full-time",
                "pubDate": "2026-07-01T10:00:00Z",
                "jobDescription": "Support product operations worldwide.",
                "url": "https://jobicy.com/jobs/3",
            },
        ]
    }
    b = builder()
    assert collect_jobicy(b, session=FakeSession(payload)) == 3
    by_id = {row["id"]: row for row in b.opportunities}
    assert by_id["jobicy-1"]["specialisations"] == ["compliance"]
    assert by_id["jobicy-2"]["specialisations"] == ["general_finance"]
    assert by_id["jobicy-3"]["specialisations"] == ["product_management"]
    stderr = capsys.readouterr().err
    assert "unmapped" not in stderr
    assert "not in taxonomy" not in stderr


def test_remoteok_live_tags_are_mapped_or_intentionally_ignored(capsys):
    b = builder()
    mapped = b.map_specialisations(["dev", "photoshop", "digital nomad", "education"], source_key="remoteok")
    assert mapped == ["general_engineering", "graphic_design"]
    stderr = capsys.readouterr().err
    assert "unmapped" not in stderr
