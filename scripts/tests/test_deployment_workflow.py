"""Deployment-path and publication guard tests."""
from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
REPO = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

from verify_published_output import verify_feed, verify_site  # noqa: E402


def _feed() -> dict:
    return json.loads((REPO / "feed.json").read_text(encoding="utf-8"))


def test_workflow_runs_publish_commands_from_repository_root():
    workflow = (REPO / ".github/workflows/refresh-feed.yml").read_text(encoding="utf-8")
    assert "working-directory: scripts" not in workflow
    assert "python3 scripts/refresh_feed.py" in workflow
    assert "--out feed.json" in workflow
    assert "--coverage-report reports/coverage_report.json" in workflow
    assert "--source-health reports/source_health.json" in workflow
    assert "--government-coverage-report reports/government_coverage_report.json" in workflow
    assert "python3 scripts/site/build_site.py --feed feed.json --out docs/index.html" in workflow


def test_workflow_has_freshness_and_phase2_publication_guard():
    workflow = (REPO / ".github/workflows/refresh-feed.yml").read_text(encoding="utf-8")
    assert "scripts/verify_published_output.py" in workflow
    assert "--expected-version 3.8" in workflow
    assert "--require-phase2" in workflow
    assert "--require-phase9" in workflow
    assert "--require-phase9-site" in workflow
    assert "--max-age-minutes 30" in workflow
    assert "--site docs/index.html" in workflow


def test_packaged_root_feed_passes_phase2_publication_structure_guard():
    assert verify_feed(_feed(), "3.8", require_phase2=True, max_age_minutes=None) == []


def test_publication_guard_detects_old_root_version():
    feed = _feed()
    feed["meta"]["feed_version"] = "2.0"
    errors = verify_feed(feed, "3.8", require_phase2=True, max_age_minutes=None)
    assert any("expected '3.8'" in error for error in errors)


def test_publication_guard_detects_missing_phase2_data():
    feed = _feed()
    del feed["opportunities"][0]["eligibility"]
    errors = verify_feed(feed, "3.8", require_phase2=True, max_age_minutes=None)
    assert any("missing Phase 2 fields" in error for error in errors)


def test_site_guard_matches_generated_site_to_feed():
    feed = _feed()
    html = (REPO / "docs/index.html").read_text(encoding="utf-8")
    assert verify_site(html, feed) == []
