"""Offline fixture tests for every collector wired into refresh_feed.py."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import requests

SCRIPTS = Path(__file__).resolve().parents[1]
REPO = SCRIPTS.parent
FIXTURES = Path(__file__).parent / "fixtures"
sys.path.insert(0, str(SCRIPTS))

from collectors.adzuna import collect_adzuna  # noqa: E402
from collectors.arbeitnow import collect_arbeitnow  # noqa: E402
from collectors.ashby import collect_ashby_board  # noqa: E402
from collectors.greenhouse import collect_greenhouse_board  # noqa: E402
from collectors.himalayas import collect_himalayas  # noqa: E402
from collectors.jobicy import collect_jobicy  # noqa: E402
from collectors.lever import collect_lever_board  # noqa: E402
from collectors.pinpoint import collect_pinpoint_board  # noqa: E402
from collectors.reliefweb import collect_reliefweb  # noqa: E402
from collectors.recruitee import collect_recruitee_board  # noqa: E402
from collectors.untalent import collect_untalent  # noqa: E402
from collectors.remotive import collect_remotive  # noqa: E402
from collectors.remoteok import collect_remoteok  # noqa: E402
from refresh_feed import FeedBuilder  # noqa: E402


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
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakeResponse(self.payload)


def fixture(name: str):
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def builder() -> FeedBuilder:
    taxonomy = json.loads((REPO / "taxonomy.json").read_text(encoding="utf-8"))
    sources = json.loads((REPO / "sources.json").read_text(encoding="utf-8"))
    return FeedBuilder(taxonomy, sources)


def assert_one_clean(b: FeedBuilder, expected_prefix: str):
    assert len(b.opportunities) == 1
    opportunity = b.opportunities[0]
    assert opportunity["id"].startswith(expected_prefix)
    assert opportunity["categories"] == opportunity["specialisations"]
    assert all(value is not None for value in opportunity["specialisations"])
    assert opportunity["apply_url"].startswith("http")


def test_greenhouse_fixture():
    b = builder()
    count = collect_greenhouse_board(
        b,
        {"board_token": "example", "name": "Example", "type": "private"},
        session=FakeSession(fixture("greenhouse")),
    )
    assert count == 1
    assert_one_clean(b, "greenhouse-example-")


def test_lever_fixture():
    b = builder()
    count = collect_lever_board(
        b,
        {"site": "example", "name": "Example", "type": "private"},
        session=FakeSession(fixture("lever")),
    )
    assert count == 1
    assert_one_clean(b, "lever-example-")


def test_ashby_fixture():
    b = builder()
    count = collect_ashby_board(
        b,
        {"board_slug": "example", "name": "Example", "type": "private"},
        session=FakeSession(fixture("ashby")),
    )
    assert count == 1
    assert_one_clean(b, "ashby-example-")


def test_recruitee_fixture():
    b = builder()
    count = collect_recruitee_board(
        b,
        {"subdomain": "example", "name": "Example", "type": "private"},
        session=FakeSession(fixture("recruitee")),
    )
    assert count == 1
    assert_one_clean(b, "recruitee-example-")
    assert b.opportunities[0]["apply_is_official"] is True
    assert b.opportunities[0]["work_mode"] == "hybrid"


def test_untalent_fixture():
    b = builder()
    count = collect_untalent(b, "https://fixture.invalid/feed.json", session=FakeSession(fixture("untalent")))
    assert count == 1
    assert_one_clean(b, "untalent-")
    assert b.opportunities[0]["apply_is_official"] is True
    assert b.opportunities[0]["organisation"]["type"] == "multilateral"


def test_pinpoint_fixture():
    b = builder()
    count = collect_pinpoint_board(
        b,
        {"subdomain": "example", "name": "Example", "type": "private"},
        session=FakeSession(fixture("pinpoint")),
    )
    assert count == 1
    assert_one_clean(b, "pinpoint-example-")


def _patch_get(monkeypatch, payload):
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: FakeResponse(payload))


def test_reliefweb_fixture(monkeypatch):
    b = builder()
    _patch_get(monkeypatch, fixture("reliefweb"))
    assert collect_reliefweb(b, appname="fixture", country_iso3="KEN", max_pages=1) == 1
    assert_one_clean(b, "reliefweb-")


def test_adzuna_fixture(monkeypatch):
    b = builder()
    _patch_get(monkeypatch, fixture("adzuna"))
    assert collect_adzuna(b, app_id="id", app_key="key", max_pages=1) == 1
    assert_one_clean(b, "adzuna-")
    assert b.opportunities[0]["specialisations"] == ["corporate_law"]


def test_himalayas_fixture(monkeypatch):
    b = builder()
    _patch_get(monkeypatch, fixture("himalayas"))
    assert collect_himalayas(b, max_pages=1) == 1
    assert_one_clean(b, "himalayas-")


def test_remotive_fixture(monkeypatch):
    b = builder()
    _patch_get(monkeypatch, fixture("remotive"))
    assert collect_remotive(b) == 1
    assert_one_clean(b, "remotive-")


def test_jobicy_fixture(monkeypatch):
    b = builder()
    _patch_get(monkeypatch, fixture("jobicy"))
    assert collect_jobicy(b) == 1
    assert_one_clean(b, "jobicy-")


def test_remoteok_fixture(monkeypatch):
    b = builder()
    _patch_get(monkeypatch, fixture("remoteok"))
    assert collect_remoteok(b) == 1
    assert_one_clean(b, "remoteok-")


def test_arbeitnow_fixture(monkeypatch):
    b = builder()
    _patch_get(monkeypatch, fixture("arbeitnow"))
    assert collect_arbeitnow(b) == 1
    assert_one_clean(b, "arbeitnow-")
