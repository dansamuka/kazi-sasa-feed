"""Generic Greenhouse job-board collector.

Greenhouse hosts publicly-accessible per-company job boards. Each company
using Greenhouse has a `board_token` (the slug in their board URL, e.g.
`https://boards.greenhouse.io/oneacrefund` -> `oneacrefund`). The endpoint

    GET https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true

is unauthenticated, not rate-limited, returns clean JSON, and is documented
at https://developers.greenhouse.io/job-board.html. One collector serves any
number of companies through a config file listing their board tokens.

Field shape (confirmed against Greenhouse's own docs):
{
  "jobs": [
    {
      "id": 127817,
      "title": "Vault Designer",
      "updated_at": "2016-01-14T10:55:28-05:00",
      "location": {"name": "Nairobi, Kenya"},
      "absolute_url": "https://boards.greenhouse.io/vaulttec/jobs/127817",
      "content": "<p>Full HTML description...</p>",       # only with ?content=true
      "departments": [{"id": ..., "name": "Engineering"}],  # only with ?content=true
      "offices":     [{"id": ..., "name": "Kenya - Nairobi"}]  # only with ?content=true
    }, ...
  ],
  "meta": {"total": 1}
}

NOT execution-tested against the live API from this sandbox - network access
to boards-api.greenhouse.io isn't available here. First real run is on
GitHub Actions; test with workflow_dispatch and watch the logs.
"""
from __future__ import annotations

import sys
from typing import Iterable

from ._common import (
    html_to_text, infer_seniority, infer_work_mode,
    is_relevant_opportunity, now_iso, parse_location, classify_industry,
    extract_years_experience, extract_education_requirement, extract_contract_type, extract_deadline,
)


def _classify_org_type(company_config: dict) -> str:
    """Company's `type` from greenhouse_boards.json wins; otherwise unverified.
    SCHEMA.md's allowed org types: employer, ngo, multilateral, private, unverified.
    """
    return company_config.get("type", "unverified")


def collect_greenhouse_board(builder, company: dict, session=None) -> int:
    """Fetch one company's board and add matching opportunities to the builder.

    Returns the number of opportunities added (before Africa filtering, so a
    company whose entire board is US-based will legitimately return 0).
    """
    import requests

    token = company["board_token"]
    company_name = company["name"]

    url = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs"
    params = {"content": "true"}

    session = session or requests
    try:
        resp = session.get(url, params=params, timeout=30)
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001 - loud failure per-source, not silent
        print(f"WARN greenhouse[{token}]: fetch failed - {exc}", file=sys.stderr)
        return 0

    payload = resp.json()
    jobs = payload.get("jobs", [])
    added = 0

    for job in jobs:
        gh_id = job.get("id")
        title = job.get("title")
        if gh_id is None or not title:
            continue

        raw_location = (job.get("location") or {}).get("name")
        location = parse_location(raw_location)
        content_html = job.get("content")

        if not is_relevant_opportunity(location, content_html):
            continue

        summary = html_to_text(content_html)

        departments = job.get("departments") or []
        raw_categories = [d.get("name", "") for d in departments if d.get("name")]
        categories = builder.map_specialisations(raw_categories, source_key=f"greenhouse:{token}")

        apply_url = job.get("absolute_url") or f"https://boards.greenhouse.io/{token}/jobs/{gh_id}"

        years_min, years_max = extract_years_experience(content_html)
        education_level, education_fields = extract_education_requirement(content_html)
        deadline, deadline_confidence = extract_deadline(content_html)

        builder.add({
            "id": f"greenhouse-{token}-{gh_id}",
            "title": title,
            "opportunity_type": "internship" if "intern" in title.lower() else "job",
            "organisation": {
                "name": company_name,
                "type": _classify_org_type(company),
                # verified=True: we've hand-added them to greenhouse_boards.json,
                # they haven't just self-declared on some aggregator page.
                "verified": True,
            },
            "location": location,
            "work_mode": infer_work_mode(raw_location),
            "seniority": infer_seniority(title),
            "categories": categories,
            "specialisations": categories,
            "industry": builder.industry_for_specialisations(categories) or classify_industry(title, content_html),
            "skills_required": [],
            "skills_preferred": [],
            "posted_at": job.get("updated_at"),  # Greenhouse doesn't expose posted_at separately
            "deadline": deadline,
            "deadline_confidence": deadline_confidence,
            "years_experience_min": years_min,
            "years_experience_max": years_max,
            "education_required": education_level,
            "education_field": education_fields,
            "contract_type": extract_contract_type(title, content_html),
            "source": {
                "name": company_name,
                "url": f"https://boards.greenhouse.io/{token}",
                # This is the org's own ATS-hosted board - as close to "official"
                # as it gets short of the org.com/careers page itself.
                "confidence": builder.confidence_for_domain("greenhouse.io"),
                "last_seen_at": now_iso(),
            },
            "apply_url": apply_url,
            # apply_url points at the employer's own Greenhouse-hosted apply flow,
            # not a third-party repost. Safe to mark official (spec §14).
            "apply_is_official": True,
            "flags": [],
            "eligibility_notes": None,
            "summary": summary,
            "raw_description_url": apply_url,
        })
        added += 1

    return added


def collect_greenhouse(builder, boards: Iterable[dict], session=None) -> int:
    """Loop over a list of Greenhouse company configs; return total added."""
    total = 0
    for company in boards:
        total += collect_greenhouse_board(builder, company, session=session)
    return total
