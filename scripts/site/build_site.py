#!/usr/bin/env python3
"""Regenerates docs/index.html - a shareable, static, front-facing job board
built from the current feed.json. No build step, no backend: opens directly
in any browser, works offline once downloaded (fonts are the only external
dependency), and is small enough to email or host as a GitHub Pages site.

Distinct from the internal review tool this evolved from: this one is
branded for external sharing (the "Kazi Sasa" identity, not a bare data
table), and deliberately shows fewer raw fields - source/confidence badges
stay, but internal fields like raw ids are dropped from the slim payload.

Usage:
    python3 scripts/site/build_site.py --feed feed.json --out docs/index.html
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def slim_opportunity(o: dict) -> dict:
    return {
        "id": o.get("id"),
        "title": o.get("title"),
        "type": o.get("opportunity_type"),
        "org": (o.get("organisation") or {}).get("name"),
        "org_verified": (o.get("organisation") or {}).get("verified"),
        "org_type": (o.get("organisation") or {}).get("type_detail") or (o.get("organisation") or {}).get("type"),
        "country": (o.get("location") or {}).get("country_canonical") or (o.get("location") or {}).get("country"),
        "country_code": (o.get("location") or {}).get("country_code"),
        "city": (o.get("location") or {}).get("city"),
        "loc_raw": (o.get("location") or {}).get("raw"),
        "scope": (o.get("location") or {}).get("scope"),
        "work_mode": o.get("work_mode"),
        "seniority": o.get("seniority"),
        "industry": o.get("industry"),
        "role_family": o.get("role_family"),
        "role_subfamily": o.get("role_subfamily"),
        "thematic_sectors": o.get("thematic_sectors") or [],
        "eligibility": (o.get("eligibility") or {}).get("status"),
        "eligibility_confidence": (o.get("eligibility") or {}).get("confidence"),
        "eligibility_evidence": (o.get("eligibility") or {}).get("evidence") or [],
        "investment_classification": (o.get("investment_profile") or {}).get("classification"),
        "investment_track": (o.get("investment_profile") or {}).get("track"),
        "investment_confidence": (o.get("investment_profile") or {}).get("confidence"),
        "dfi_relevance": (o.get("investment_profile") or {}).get("dfi_relevance"),
        "is_investment_role": (o.get("investment_profile") or {}).get("is_investment_role", False),
        "is_dfi_or_multilateral": (o.get("institution_profile") or {}).get("is_dfi_or_multilateral", False),
        "institution_type": (o.get("institution_profile") or {}).get("institution_type"),
        "institution_registry_id": (o.get("institution_profile") or {}).get("registry_id"),
        "institution_source_pack": (o.get("institution_profile") or {}).get("source_pack"),
        "phase7_priority_institution": (o.get("institution_profile") or {}).get("phase7_priority_institution", False),
        "is_ngo_or_un": (o.get("ngo_profile") or {}).get("is_ngo_or_un", False),
        "ngo_organisation_group": (o.get("ngo_profile") or {}).get("organisation_group"),
        "ngo_classification": (o.get("ngo_profile") or {}).get("classification"),
        "ngo_track": (o.get("ngo_profile") or {}).get("track"),
        "ngo_confidence": (o.get("ngo_profile") or {}).get("confidence"),
        "ngo_is_programme_role": (o.get("ngo_profile") or {}).get("is_programme_role", False),
        "phase8_priority_organisation": (o.get("ngo_profile") or {}).get("phase8_priority_organisation", False),
        "is_government_or_public_service": (o.get("government_profile") or {}).get("is_government_or_public_service", False),
        "phase9_priority_portal": (o.get("government_profile") or {}).get("phase9_priority_portal", False),
        "public_service_grade": (o.get("government_profile") or {}).get("public_service_grade"),
        "salary_scale": (o.get("government_profile") or {}).get("salary_scale"),
        "advert_reference": (o.get("government_profile") or {}).get("advert_reference"),
        "number_of_positions": (o.get("government_profile") or {}).get("number_of_positions"),
        "citizenship_required": (o.get("government_profile") or {}).get("citizenship_required"),
        "application_method": (o.get("government_profile") or {}).get("application_method"),
        "is_kenya_public_institution": (o.get("public_institution_profile") or {}).get("is_kenya_public_institution", False),
        "public_institution_category": (o.get("public_institution_profile") or {}).get("category"),
        "is_multinational": (o.get("multinational_profile") or {}).get("is_multinational", False),
        "multinational_sector": (o.get("multinational_profile") or {}).get("sector"),
        "phase11_priority_employer": (o.get("multinational_profile") or {}).get("phase11_priority_employer", False),
        "african_city_footprint": (o.get("multinational_profile") or {}).get("african_city_footprint") or [],
        "years_min": o.get("years_experience_min"),
        "years_max": o.get("years_experience_max"),
        "education": o.get("education_required"),
        "contract": o.get("contract_type"),
        "posted": o.get("posted_at"),
        "deadline": o.get("deadline"),
        "source": (o.get("source") or {}).get("name"),
        "confidence": (o.get("source") or {}).get("confidence"),
        "apply_url": o.get("apply_url"),
        "summary": (o.get("summary") or "")[:260],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--feed", default="feed.json")
    parser.add_argument("--out", default="docs/index.html")
    args = parser.parse_args()

    here = Path(__file__).parent  # scripts/site/
    repo_root = here.parent.parent

    feed_path = (repo_root / args.feed).resolve()
    # Same guard class as refresh_feed.py's own out-path guard, and this
    # file's own out_path guard below - this exact bug (a workflow argument
    # combined with an already-absolute repo_root walking one directory too
    # far up) has now happened twice in this pipeline (once in
    # refresh_feed.py, once here). Fail loudly with a clear message rather
    # than a bare FileNotFoundError traceback if it happens a third time.
    if repo_root.resolve() not in feed_path.parents and feed_path != repo_root.resolve():
        raise SystemExit(f"ERROR: resolved feed path {feed_path} is outside the repo root - refusing to read from there. Check the --feed argument.")

    with open(feed_path, encoding="utf-8") as f:
        feed = json.load(f)

    slim_items = [slim_opportunity(o) for o in feed["opportunities"]]
    payload = {"__meta__": feed["meta"], "items": slim_items}

    with open(here / "template.html", encoding="utf-8") as f:
        template = f.read()
    with open(here / "app.js", encoding="utf-8") as f:
        app_js = f.read()

    html = template.replace("__FEED_DATA__", json.dumps(payload))
    html = html.replace("__APP_JS__", app_js)

    out_path = (repo_root / args.out).resolve()
    # Same guard class as refresh_feed.py's - refuse to write outside the repo.
    if repo_root.resolve() not in out_path.parents and out_path != repo_root.resolve():
        raise SystemExit(f"ERROR: resolved output path {out_path} is outside the repo root - refusing to write there.")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Wrote {len(slim_items)} opportunities to {out_path}")


if __name__ == "__main__":
    main()
