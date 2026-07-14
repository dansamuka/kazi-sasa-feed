"""Regression coverage for the collapsible mobile filter controls."""
from pathlib import Path
import subprocess

REPO = Path(__file__).resolve().parents[2]


def test_filter_toggle_is_present_and_accessible():
    template = (REPO / "scripts/site/template.html").read_text(encoding="utf-8")
    assert 'id="filterToggle"' in template
    assert 'aria-controls="pillRow"' in template
    assert 'id="activeFilterCount"' in template
    assert 'id="filterToggleLabel"' in template


def test_mobile_filters_start_collapsed_and_search_is_not_sticky():
    template = (REPO / "scripts/site/template.html").read_text(encoding="utf-8")
    assert 'search-hero mobile-filters-collapsed' in template
    assert '@media (max-width: 760px)' in template
    assert '.search-hero.mobile-filters-collapsed:not(.filters-open) .li-pill-row' in template
    mobile_block = template.split('@media (max-width: 760px)', 1)[1].split('@media (max-width: 420px)', 1)[0]
    assert 'position: static;' in mobile_block
    assert 'max-height: min(52vh, 430px);' in mobile_block


def test_filter_toggle_logic_supports_desktop_and_mobile():
    app = (REPO / "scripts/site/app.js").read_text(encoding="utf-8")
    for marker in (
        "MOBILE_FILTER_QUERY",
        "function activeFilterCount()",
        "function setFiltersOpen(open)",
        "function setupFilterToggle()",
        "setFiltersOpen(!MOBILE_FILTER_QUERY.matches)",
        "setupFilterToggle();",
    ):
        assert marker in app


def test_built_site_contains_mobile_filter_controls():
    html = (REPO / "docs/index.html").read_text(encoding="utf-8")
    assert 'id="filterToggle"' in html
    assert 'function setupFilterToggle()' in html
    assert 'mobile-filters-collapsed' in html


def test_site_javascript_remains_syntactically_valid():
    result = subprocess.run(
        ["node", "--check", str(REPO / "scripts/site/app.js")],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_workflow_rebuilds_site_before_offline_tests():
    workflow = (REPO / ".github/workflows/refresh-feed.yml").read_text(encoding="utf-8")
    build_marker = "- name: Rebuild test site from current live feed"
    test_marker = "- name: Run offline tests"
    assert build_marker in workflow
    assert workflow.index(build_marker) < workflow.index(test_marker)
    assert "python3 scripts/site/build_site.py --feed feed.json --out docs/index.html" in workflow
