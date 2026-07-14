"""Phase 3 collector framework, Jobicy resilience, and web-filter tests."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import requests

SCRIPTS = Path(__file__).resolve().parents[1]
REPO = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

from collectors.base import CollectorContext, CollectorSpec  # noqa: E402
from collectors.jobicy import collect_jobicy  # noqa: E402
from collectors.registry import collector_manifest, default_collector_specs  # noqa: E402
from normalizers.text import as_text, as_text_list  # noqa: E402
from pipeline.collect import CollectorRunner  # noqa: E402
from pipeline.http import HttpClient  # noqa: E402
from refresh_feed import FeedBuilder  # noqa: E402
from reporting import build_source_health_report  # noqa: E402
from verify_published_output import verify_site  # noqa: E402


_SITE_SPEC = importlib.util.spec_from_file_location("kazi_sasa_site_builder", SCRIPTS / "site" / "build_site.py")
_SITE_MODULE = importlib.util.module_from_spec(_SITE_SPEC)
assert _SITE_SPEC.loader is not None
_SITE_SPEC.loader.exec_module(_SITE_MODULE)
slim_opportunity = _SITE_MODULE.slim_opportunity


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class DummyBuilder:
    def __init__(self):
        self.opportunities = []



def _feed_builder() -> FeedBuilder:
    taxonomy = json.loads((REPO / "taxonomy.json").read_text(encoding="utf-8"))
    sources = json.loads((REPO / "sources.json").read_text(encoding="utf-8"))
    return FeedBuilder(taxonomy, sources)


def test_text_normalizer_handles_strings_lists_objects_and_duplicates():
    value = ["Worldwide", {"name": "Africa"}, ["Worldwide", 3], None]
    assert as_text_list(value) == ["Worldwide", "Africa", "3"]
    assert as_text(value) == "Worldwide, Africa, 3"


def test_jobicy_accepts_list_and_object_fields(monkeypatch):
    payload = {
        "jobs": [{
            "id": 9001,
            "jobTitle": ["Investment", "Analyst"],
            "companyName": {"name": "Pan-Africa Capital"},
            "jobGeo": ["Remote", "Africa"],
            "jobIndustry": ["Data Engineering"],
            "jobType": ["full-time"],
            "jobLevel": ["Mid level"],
            "pubDate": ["2026-07-12T10:00:00Z"],
            "jobDescription": ["<p>Open to applicants across Africa.</p>", "<p>3 years of experience.</p>"],
            "url": ["https://jobicy.com/jobs/9001"],
        }]
    }
    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: FakeResponse(payload))
    builder = _feed_builder()
    assert collect_jobicy(builder) == 1
    opportunity = builder.opportunities[0]
    assert opportunity["title"] == "Investment / Analyst"
    assert opportunity["organisation"]["name"] == "Pan-Africa Capital"
    assert opportunity["location"]["is_remote_from_kenya"] is True
    assert opportunity["contract_type"] == "permanent"
    assert opportunity["posted_at"] == "2026-07-12T10:00:00Z"


def test_collector_registry_has_unique_expected_keys_and_metadata():
    specs = default_collector_specs()
    keys = [spec.key for spec in specs]
    assert keys == [
        "reliefweb", "untalent", "cornerstone", "successfactors", "oracle_cx", "pageup", "official_html",
        "public_institution_html", "workday", "smartrecruiters", "workable", "multinational_html",
        "government_html", "government_pdf", "government_circular", "adzuna", "greenhouse", "ashby", "lever", "pinpoint", "recruitee",
        "himalayas", "remotive", "jobicy", "remoteok", "arbeitnow",
    ]
    assert len(keys) == len(set(keys))
    manifest = collector_manifest()
    assert all(row["source_kind"] and row["schedule_class"] for row in manifest)
    assert next(row for row in manifest if row["key"] == "reliefweb")["required_env"] == ["RELIEFWEB_APPNAME"]


def test_collector_runner_skips_missing_env_and_continues_after_error(tmp_path):
    builder = DummyBuilder()

    def succeeds(context, config):
        context.builder.opportunities.append({"id": "ok"})
        return 1

    def fails(context, config):
        raise RuntimeError("fixture failure")

    specs = [
        CollectorSpec("missing", succeeds, required_env=("API_TOKEN",)),
        CollectorSpec("broken", fails),
        CollectorSpec("healthy", succeeds),
    ]
    summary = CollectorRunner(specs).run(CollectorContext(builder, tmp_path, "config/organisations.json", env={}))
    assert summary.statuses["missing"]["status"] == "skipped_missing_config"
    assert summary.statuses["broken"]["status"] == "error"
    assert summary.statuses["healthy"]["status"] == "collected"
    assert summary.per_source_counts["healthy"] == 1
    assert builder.opportunities == [{"id": "ok"}]


def test_collector_runner_reports_configured_targets(tmp_path):
    builder = DummyBuilder()

    def collect(context, config):
        for item in config:
            context.builder.opportunities.append(item)
        return len(config)

    spec = CollectorSpec("configured", collect, resolve_config=lambda context: [{"id": "1"}, {"id": "2"}])
    summary = CollectorRunner([spec]).run(CollectorContext(builder, tmp_path, "organisations.json", env={}))
    assert summary.configured_counts["configured"] == 2
    assert summary.statuses["configured"]["configured_targets"] == 2
    assert summary.statuses["configured"]["added_delta"] == 2


def test_source_health_report_preserves_phase3_runtime_metadata():
    report = build_source_health_report(
        {"example": 2},
        {"example": {"status": "collected", "duration_ms": 15, "source_kind": "employer_ats", "schedule_class": "daily", "added_delta": 2}},
        {"example": 3},
    )
    assert report["report_version"] == "2.0"
    row = report["sources"][0]
    assert row["duration_ms"] == 15
    assert row["source_kind"] == "employer_ats"
    assert row["configured_targets"] == 3


def test_slim_site_payload_exposes_requested_filter_fields():
    opportunity = json.loads((REPO / "feed.json").read_text(encoding="utf-8"))["opportunities"][0]
    slim = slim_opportunity(opportunity)
    assert {"country", "city", "role_family", "org_type", "eligibility", "eligibility_confidence"} <= set(slim)


def test_template_and_javascript_include_all_requested_filters():
    template = (REPO / "scripts/site/template.html").read_text(encoding="utf-8")
    app = (REPO / "scripts/site/app.js").read_text(encoding="utf-8")
    for identifier in ("countryPill", "cityPill", "roleFamilyPill", "orgTypePill", "eligibilityPill"):
        assert f'id="{identifier}"' in template
        assert identifier in app
    for state_key in ("country", "city", "roleFamily", "orgType", "eligibility"):
        assert f"{state_key}: new Set()" in app


def test_site_javascript_is_syntactically_valid():
    result = subprocess.run(["node", "--check", str(REPO / "scripts/site/app.js")], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_refresh_feed_uses_registry_runner_not_manual_collector_loop():
    script = (REPO / "scripts/refresh_feed.py").read_text(encoding="utf-8")
    assert "default_collector_specs()" in script
    assert "CollectorRunner(specs).run(context)" in script
    assert "--only-source" in script
    assert "from collectors.jobicy import collect_jobicy" not in script


def test_packaged_opportunity_ids_remain_unchanged():
    import hashlib

    feed = json.loads((Path(__file__).parent / "fixtures" / "legacy_packaged_feed.json").read_text(encoding="utf-8"))
    ids = [row["id"] for row in feed["opportunities"]]
    assert len(ids) == 204
    assert len(ids) == len(set(ids))
    digest = hashlib.sha256(json.dumps(ids, separators=(",", ":")).encode()).hexdigest()
    assert digest == "ba79e6c44627ddcaea771aa368a249f58bcfee806e2cc44329346baad32d4e76"


def test_phase3_publication_guard_requires_new_filters():
    feed = json.loads((REPO / "feed.json").read_text(encoding="utf-8"))
    html = (REPO / "docs/index.html").read_text(encoding="utf-8")
    # The packaged site is regenerated during the implementation validation.
    if "countryPill" in html:
        assert verify_site(html, feed, require_phase3=True) == []
    assert any("Phase 3" in error for error in verify_site("<html></html>", feed, require_phase3=True))


def test_workflow_publishes_manifest_and_guards_phase3_site():
    workflow = (REPO / ".github/workflows/refresh-feed.yml").read_text(encoding="utf-8")
    assert "--collector-manifest reports/collector_manifest.json" in workflow
    assert "reports/collector_manifest.json" in workflow
    assert "--require-phase3-site" in workflow


def test_collector_runner_rolls_back_partial_records_on_failure(tmp_path):
    builder = DummyBuilder()

    def partial_failure(context, config):
        context.builder.opportunities.append({"id": "partial"})
        raise RuntimeError("failed after adding")

    summary = CollectorRunner([CollectorSpec("partial", partial_failure)]).run(
        CollectorContext(builder, tmp_path, "organisations.json", env={})
    )
    assert builder.opportunities == []
    assert summary.statuses["partial"]["rolled_back_partial"] == 1


class FakeHttpSession:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []
        self.closed = False

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        response = FakeResponse(self.payload)
        response.status_code = 200
        response.headers = {"Content-Type": "application/json"}
        return response

    def close(self):
        self.closed = True


def test_shared_http_client_caches_json_and_applies_source_timeout(tmp_path):
    session = FakeHttpSession({"jobs": [{"id": 1}]})
    client = HttpClient(cache_dir=tmp_path / "cache", session=session)
    client.set_policy("fixture", timeout_seconds=17, min_interval_seconds=0, cache_ttl_seconds=60)
    first = client.get("https://example.test/jobs", params={"page": 1}, timeout=99)
    second = client.get("https://example.test/jobs", params={"page": 1}, timeout=99)
    assert first.json() == second.json()
    assert len(session.calls) == 1
    assert session.calls[0][1]["timeout"] == 17
    assert client.stats["network_requests"] == 1
    assert client.stats["cache_hits"] == 1
    client.close()
    assert session.closed is True


def test_runner_applies_collector_http_policy(tmp_path):
    class PolicyRecorder:
        def __init__(self):
            self.calls = []

        def set_policy(self, *args, **kwargs):
            self.calls.append((args, kwargs))

    http = PolicyRecorder()
    builder = DummyBuilder()

    def collect(context, config):
        context.builder.opportunities.append({"id": "x"})
        return 1

    spec = CollectorSpec(
        "policy", collect, timeout_seconds=41, min_interval_seconds=0.7,
        cache_ttl_seconds=1234, freshness_hours=20,
    )
    CollectorRunner([spec]).run(CollectorContext(builder, tmp_path, "organisations.json", env={}, http=http))
    assert http.calls == [(('policy',), {
        'timeout_seconds': 41,
        'min_interval_seconds': 0.7,
        'cache_ttl_seconds': 1234,
    })]


def test_collector_manifest_exposes_http_and_freshness_policy():
    manifest = collector_manifest()
    assert all({"freshness_hours", "timeout_seconds", "min_interval_seconds", "cache_ttl_seconds"} <= set(row) for row in manifest)
    jobicy = next(row for row in manifest if row["key"] == "jobicy")
    assert jobicy["cache_ttl_seconds"] == 7200
    assert jobicy["min_interval_seconds"] == 0.5


def test_workflow_publishes_structured_collector_error_log():
    workflow = (REPO / ".github/workflows/refresh-feed.yml").read_text(encoding="utf-8")
    assert "--collector-errors reports/collector_errors.json" in workflow
    assert "reports/collector_errors.json" in workflow
