from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

from collectors.government_html import parse_government_table
from refresh_feed import FeedBuilder
from validate_feed import validate_feed

REPO = Path(__file__).resolve().parents[2]


def load(relative: str):
    return json.loads((REPO / relative).read_text(encoding="utf-8"))


def builder():
    return FeedBuilder(load("taxonomy.json"), load("config/source_registry.json"))


def kenya_portal():
    return next(
        row for row in load("config/public_portals.json")["portals"]
        if row["country_code"] == "KE"
    )


def test_psc_javascript_postback_falls_back_to_official_http_portal():
    html = '''
    <table>
      <tr><th>Advert Number</th><th>Position</th><th>Job Scale</th><th>Advert Date</th><th>Advert Close Date</th><th>Details</th></tr>
      <tr>
        <td>PSC/35/2026</td><td>Director, Planning</td><td>2</td><td>17-06-2026</td><td>03-08-2026</td>
        <td><a href="javascript:__doPostBack('DataGrid2$ctl03$LinkButton3','')">View</a></td>
      </tr>
    </table>
    '''
    b = builder()
    assert parse_government_table(b, kenya_portal(), html) == 1
    row = b.opportunities[0]
    parsed = urlparse(row["apply_url"])
    assert parsed.scheme in {"http", "https"}
    assert parsed.netloc == "psckjobs.go.ke"
    assert not row["apply_url"].casefold().startswith("javascript:")
    assert row["industry"] == "public_sector"
    result = validate_feed({"meta": {"feed_version": "3.8", "generated_at": "2026-07-14T00:00:00Z", "opportunity_count": 1}, "opportunities": [row]}, load("taxonomy.json"), load("config/role_taxonomy.json"))
    assert not any("apply_url" in error or "industry" in error for error in result.errors)


def test_psc_relative_http_detail_link_is_preserved():
    html = '''
    <table>
      <tr><th>Advert Number</th><th>Position</th><th>Details</th></tr>
      <tr><td>PSC/36/2026</td><td>Economist</td><td><a href="JobDetails.aspx?JobId=36">View</a></td></tr>
    </table>
    '''
    b = builder()
    assert parse_government_table(b, kenya_portal(), html) == 1
    assert b.opportunities[0]["apply_url"] == "https://psckjobs.go.ke/JobDetails.aspx?JobId=36"


def test_run35_healthcare_taxonomy_terms_are_controlled(capsys):
    b = builder()
    expected = {
        "Healthcare-Sales-Leadership": "general_sales",
        "Virtual-Sales-Manager": "general_sales",
        "Healthcare-Administration": "health_administration",
        "Referral-Management": "health_administration",
        "E-Referral-Specialist": "health_administration",
        "Healthcare-Coordination": "health_administration",
        "Home-Health-Services": "health_administration",
        "Home-Health-Care-Specialist": "health_administration",
        "Referral-Specialist": "health_administration",
        "Patient-Referral-Specialist": "health_administration",
        "Healthcare-Referral-Coordinator": "health_administration",
        "Home-Health-Coordinator": "health_administration",
        "Home-Health-Liaison": "health_administration",
    }
    for raw, canonical in expected.items():
        assert b.map_specialisation(raw, source_key="himalayas") == canonical
    assert b.map_specialisation("Healthcare & Medical", source_key="jobicy") is None
    assert b.map_industry("Healthcare & Medical") == "healthcare"
    assert "WARN:" not in capsys.readouterr().err
