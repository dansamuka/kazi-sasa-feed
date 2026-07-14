"""Generic Pinpoint (pinpointhq.com) job-board collector.

Same pattern as greenhouse.py/lever.py/ashby.py: Pinpoint hosts a public,
unauthenticated per-company JSON endpoint, explicitly documented by Pinpoint
themselves for exactly this third-party-listing use case (see
https://help.pinpoint.support/en/articles/5878344-how-to-list-pinpoint-jobs-on-any-website
- "This resource can be fetched client side with no CORS issues").

Endpoint: GET https://{company-subdomain}.pinpointhq.com/postings.json
Docs: https://developers.pinpointhq.com/docs/jobs-json-endpoint

This source was added specifically because Sun King - flagged as directly
relevant to Sir's Nithio work - turned out to use Pinpoint rather than Lever
(discovered when the lever_boards.json seed guess 404'd). Worth checking any
other African climate/PAYGo/fintech company that doesn't show up on
Greenhouse/Lever/Ashby against Pinpoint before assuming it isn't on any ATS
with a public feed at all.

Field shape (confirmed against Pinpoint's own docs):
{
  "data": [
    {
      "id": "118475",
      "title": "Senior Solar Field Technician",
      "url": "https://workwithus.pinpointhq.com/jobs/118475",
      "description": "<div>...</div>",
      "key_responsibilities": "<div>...</div>",
      "skills_knowledge_expertise": "<div>...</div>",
      "benefits": "<div>...</div>",
      "location": {"name": "Nairobi, Kenya", ...},  # structure varies, treat leniently
      "employment_type": "Full Time",
      "department": "Field Operations",  # or nested under relationships depending on config
      "published_at": "2026-06-01T10:00:00Z",
      "compensation": {"visible": true, "min": 60000, "max": 90000, "currency": "USD"}
    }
  ]
}

Pinpoint's exact field layout varies somewhat by how each company configured
their careers site (custom structures, multi-language, etc.) - this collector
is deliberately defensive about missing/renamed fields rather than assuming
one fixed shape holds for every company.

NOT execution-tested against the live API from this sandbox.
"""
from __future__ import annotations

import sys
from typing import Iterable

from ._common import (
    classify_industry, extract_contract_type, extract_deadline, extract_education_requirement,
    extract_years_experience, html_to_text, infer_seniority,
    is_relevant_opportunity, now_iso, parse_location,
)


def _build_full_description(job: dict) -> str:
    """Pinpoint splits descriptions across several optional HTML fields -
    combine whatever is present rather than assuming all of them exist."""
    parts = [
        job.get("description", ""),
        job.get("key_responsibilities", ""),
        job.get("skills_knowledge_expertise", ""),
    ]
    return "\n".join(p for p in parts if p)


def _extract_location_string(job: dict) -> str | None:
    loc = job.get("location")
    if isinstance(loc, str):
        return loc
    if isinstance(loc, dict):
        return loc.get("name") or loc.get("city") or loc.get("formatted")
    return None


def _extract_department(job: dict) -> str | None:
    dept = job.get("department")
    if isinstance(dept, str):
        return dept
    if isinstance(dept, dict):
        return dept.get("name")
    return None


def collect_pinpoint_board(builder, company: dict, session=None) -> int:
    import requests

    subdomain = company["subdomain"]
    company_name = company["name"]

    url = f"https://{subdomain}.pinpointhq.com/postings.json"
    # Pinpoint's public endpoint docs note this is meant for client-side
    # fetches; a couple of these headers mirror what browsers send by
    # default and avoid some servers' bot-blocking heuristics for a bare
    # requests.get with no headers at all.
    headers = {"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"}

    session = session or requests
    try:
        resp = session.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        print(f"WARN pinpoint[{subdomain}]: fetch failed - {exc}", file=sys.stderr)
        return 0

    payload = resp.json()
    jobs = payload.get("data", [])
    added = 0

    for job in jobs:
        job_id = job.get("id")
        title = job.get("title")
        if not job_id or not title:
            continue

        raw_location = _extract_location_string(job)
        location = parse_location(raw_location)
        full_description_html = _build_full_description(job)

        if not is_relevant_opportunity(location, full_description_html):
            continue

        summary = html_to_text(full_description_html)

        department = _extract_department(job)
        categories = builder.map_specialisations([department], source_key=f"pinpoint:{subdomain}") if department else []

        employment_type = (job.get("employment_type") or "").lower()
        opportunity_type = "internship" if "intern" in title.lower() or "intern" in employment_type else "job"

        years_min, years_max = extract_years_experience(full_description_html)
        education_level, education_fields = extract_education_requirement(full_description_html)
        deadline, deadline_confidence = extract_deadline(full_description_html)

        compensation = None
        comp = job.get("compensation") or {}
        if comp.get("visible") and comp.get("min") and comp.get("max") and comp.get("currency"):
            compensation = {
                "min": int(comp["min"]),
                "max": int(comp["max"]),
                "currency": comp["currency"],
                "period": "year",
                "disclosed": True,
            }

        job_url = job.get("url") or f"https://{subdomain}.pinpointhq.com/jobs/{job_id}"

        opportunity = {
            "id": f"pinpoint-{subdomain}-{job_id}",
            "title": title,
            "opportunity_type": opportunity_type,
            "organisation": {
                "name": company_name,
                "type": company.get("type", "unverified"),
                "verified": True,
            },
            "location": location,
            "work_mode": None,  # Pinpoint doesn't expose a structured work-mode field consistently
            "seniority": infer_seniority(title),
            "categories": categories,
            "specialisations": categories,
            "industry": builder.industry_for_specialisations(categories) or classify_industry(title, full_description_html),
            "skills_required": [],
            "skills_preferred": [],
            "posted_at": job.get("published_at"),
            "deadline": deadline,
            "deadline_confidence": deadline_confidence,
            "years_experience_min": years_min,
            "years_experience_max": years_max,
            "education_required": education_level,
            "education_field": education_fields,
            "contract_type": extract_contract_type(title, full_description_html),
            "source": {
                "name": company_name,
                "url": f"https://{subdomain}.pinpointhq.com",
                "confidence": builder.confidence_for_domain("pinpointhq.com"),
                "last_seen_at": now_iso(),
            },
            "apply_url": job_url,
            "apply_is_official": True,  # employer's own Pinpoint-hosted apply flow
            "flags": [],
            "eligibility_notes": None,
            "summary": summary,
            "raw_description_url": job_url,
        }
        if compensation:
            opportunity["compensation"] = compensation

        builder.add(opportunity)
        added += 1

    return added


def collect_pinpoint(builder, boards: Iterable[dict], session=None) -> int:
    total = 0
    for company in boards:
        total += collect_pinpoint_board(builder, company, session=session)
    return total
