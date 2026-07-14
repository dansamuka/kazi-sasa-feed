from __future__ import annotations

import json
from pathlib import Path
import sys

SCRIPTS = Path(__file__).resolve().parents[1]
REPO = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

from migrate_phase11 import repair_and_enrich  # noqa: E402
from bootstrap_published_feed import needs_bootstrap  # noqa: E402


def _row(title: str, raw_location: str, *, org: str = "World Bank Group") -> dict:
    return {
        "id": "legacy-row-1",
        "title": title,
        "opportunity_type": "job",
        "organisation": {"name": org, "type": "multilateral", "verified": True, "id": "world-bank-group" if org == "World Bank Group" else "unicef"},
        "location": {"raw": raw_location, "country": None, "region": None, "is_remote_from_kenya": False, "scope": None, "relocation_country": None},
        "work_mode": None,
        "seniority": None,
        "categories": ["investment_operations"] if org == "World Bank Group" else ["programme_management"],
        "specialisations": ["investment_operations"] if org == "World Bank Group" else ["programme_management"],
        "industry": "financial_services" if org == "World Bank Group" else "development_humanitarian",
        "skills_required": [], "skills_preferred": [],
        "posted_at": None, "deadline": None, "deadline_confidence": "unknown",
        "years_experience_min": None, "years_experience_max": None,
        "education_required": None, "education_field": [], "languages_required": [],
        "contract_type": "unknown",
        "source": {"name": "Official", "url": "https://example.org/jobs", "confidence": "official", "kind": "institution_official", "last_seen_at": "2026-07-13T00:00:00Z"},
        "apply_url": "https://example.org/jobs/1", "apply_is_official": True,
        "flags": [], "eligibility_notes": None,
        "summary": "Job description and requirements for this vacancy.",
        "raw_description_url": "https://example.org/jobs/1",
        "institution_profile": {"source_pack": "phase7_dfi_multilateral" if org == "World Bank Group" else "phase8_ngo_un_development"},
    }


def _feed(*rows: dict) -> dict:
    return {
        "meta": {
            "feed_version": "3.6", "generated_at": "2026-07-13T11:18:41Z",
            "opportunity_count": len(rows), "source_count": 1,
            "official_vacancy_quality_version": "1.0",
        },
        "opportunities": list(rows),
    }


def test_legacy_world_bank_default_does_not_make_legal_role_investment_or_ngo():
    data, stats = repair_and_enrich(REPO, _feed(_row("Legal Analyst", "Conakry, GN")), mark_bootstrap=True)
    assert stats["published"] == 1
    row = data["opportunities"][0]
    assert "investment_operations" not in row["specialisations"]
    assert row["investment_profile"]["is_investment_role"] is False
    assert row["investment_profile"]["dfi_relevance"] == "institutional_role"
    assert row["ngo_profile"]["is_ngo_or_un"] is False
    assert row["role_family"] != "investment"


def test_clearly_non_african_legacy_official_role_is_removed():
    data, stats = repair_and_enrich(REPO, _feed(_row("Legal Analyst", "Kyiv, UA"), _row("Programme Officer", "Nairobi, KE", org="UNICEF")), mark_bootstrap=True)
    assert len(data["opportunities"]) == 1
    assert stats["non_african_official_removed"] == 1


def test_invalid_generic_detail_title_is_removed_from_legacy_feed():
    row = _row("JavaScript is disabled", "Nairobi, KE", org="UNICEF")
    data, stats = repair_and_enrich(REPO, _feed(row, _row("Programme Officer", "Nairobi, KE", org="UNICEF")), mark_bootstrap=True)
    assert len(data["opportunities"]) == 1
    assert stats["invalid_title_removed"] == 1


def test_bootstrap_metadata_is_honest_about_source_freshness():
    data, _ = repair_and_enrich(REPO, _feed(_row("Programme Officer", "Nairobi, KE", org="UNICEF")), mark_bootstrap=True)
    meta = data["meta"]
    assert meta["feed_version"] == "3.8"
    assert meta["publication_repair_version"] == "1.0"
    assert meta["bootstrap_schema_migration"] is True
    assert meta["live_refresh_completed"] is False
    assert meta["source_data_generated_at"] == "2026-07-13T11:18:41Z"
    assert meta["generated_at"] != meta["source_data_generated_at"]


def test_bootstrap_need_detection():
    assert needs_bootstrap(_feed()) is True
    current = {"meta": {"feed_version": "3.8", "official_vacancy_quality_version": "1.1", "publication_repair_version": "1.0", "africa_access_certification_version": "1.0"}, "opportunities": [{"government_profile": {}, "public_institution_profile": {}, "multinational_profile": {}, "africa_relevance": {}, "african_applicant_access": {}}]}
    assert needs_bootstrap(current) is False


def test_workflow_bootstraps_and_stages_live_refresh_safely():
    workflow = (REPO / ".github/workflows/refresh-feed.yml").read_text(encoding="utf-8")
    assert "Bootstrap current published feed to Phase 12 certification" in workflow
    assert "Commit schema bootstrap before long live refresh" in workflow
    assert "Attempt full live refresh in staging" in workflow
    assert "--out .runtime/feed.json" in workflow
    assert "retaining the validated Phase 12 last-known-good feed" in workflow
    assert "cp .runtime/feed.json feed.json" in workflow


def test_deploy_is_source_only_and_never_force_pushes_snapshot():
    bat = (REPO / "deploy.bat").read_text(encoding="utf-8")
    ps1 = (REPO / "deploy.ps1").read_text(encoding="utf-8")
    assert "Safe Source Deployment" in bat
    assert "git push origin main" in ps1
    assert "--force" not in ps1
    assert "feed.json" in ps1 and "generated-backup" in ps1
    assert "gh workflow run refresh-feed.yml" in ps1


def test_site_explains_bootstrap_fallback_instead_of_claiming_fresh_pull():
    app = (REPO / "scripts/site/app.js").read_text(encoding="utf-8")
    template = (REPO / "scripts/site/template.html").read_text(encoding="utf-8")
    assert "LAST-KNOWN-GOOD DATA" in app
    assert "source_data_generated_at" in app
    assert "schema migrated without claiming a fresh source pull" in app
    assert 'id="freshnessBanner"' in template
