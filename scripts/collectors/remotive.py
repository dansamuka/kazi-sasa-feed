"""Remotive (remotive.com) remote jobs collector.

Endpoint: GET https://remotive.com/api/remote-jobs
Docs: https://github.com/remotive-com/remote-jobs-api (official, Remotive-run)

Confirmed genuinely free, no API key. Usage terms (from Remotive's own docs):
must link back to Remotive and credit it as the source; must not republish
Remotive jobs to competing aggregators (Jooble, Neuvoo, Google Jobs, LinkedIn
Jobs) - neither restriction affects us, since we're building our own app, not
a redistribution service. Jobs are intentionally delayed 24h on Remotive's
side before appearing via the API, so there's no benefit to polling more than
once a day.

Confirmed response field shape (from Remotive's own GitHub docs):
{
  "job-count": N,
  "jobs": [
    {
      "id": 123, "url": "https://remotive.com/remote-jobs/product/lead-developer-123",
      "title": "Lead Developer", "company_name": "Remotive", "company_logo": "...",
      "category": "Software Development",
      "job_type": "full_time" | "contract" | "part_time" | "freelance" | "internship" (often blank),
      "publication_date": "2020-02-15T10:23:26",
      "candidate_required_location": "...",  # geographical restriction, if any
      "salary": "...", "description": "<p>...</p>", "tags": [...],
    }, ...
  ]
}

Global remote-jobs board, not Africa-specific - every result goes through the
same shared is_relevant_opportunity() filtering
used for Greenhouse/Lever/Ashby/Pinpoint/Himalayas, applied to
candidate_required_location via parse_location() (free text, no structured
restriction list the way Himalayas has).

NOT execution-tested against the live API from this sandbox.
"""
from __future__ import annotations

import sys

from ._common import (
    classify_industry, extract_contract_type, extract_deadline, extract_education_requirement,
    extract_years_experience, html_to_text,
    infer_seniority, infer_work_mode, is_relevant_opportunity,
    now_iso, parse_location,
)

_JOB_TYPE_MAP = {
    "full_time": "permanent",
    "part_time": "part_time",
    "contract": "contract",
    "freelance": "consultant",
    "internship": "unknown",  # handled via opportunity_type instead
}


def collect_remotive(builder, category: str | None = None, session=None) -> int:
    import requests
    client = session or requests

    params = {}
    if category:
        params["category"] = category

    try:
        resp = client.get("https://remotive.com/api/remote-jobs", params=params, timeout=30)
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        print(f"WARN remotive: fetch failed - {exc}", file=sys.stderr)
        return 0

    payload = resp.json()
    jobs = payload.get("jobs", [])
    added = 0

    for job in jobs:
        job_id = job.get("id")
        title = job.get("title")
        if job_id is None or not title:
            continue

        description_html = job.get("description") or ""
        candidate_location = job.get("candidate_required_location")
        location = parse_location(candidate_location)

        if not is_relevant_opportunity(location, description_html):
            continue

        company_name = job.get("company_name") or "Unknown company"
        category_name = job.get("category") or ""
        categories = builder.map_specialisations([category_name], source_key="remotive") if category_name else []

        job_type_raw = (job.get("job_type") or "").lower()
        opportunity_type = "internship" if "intern" in job_type_raw or "intern" in title.lower() else "job"
        contract_type = _JOB_TYPE_MAP.get(job_type_raw) or extract_contract_type(title, description_html)

        years_min, years_max = extract_years_experience(description_html)
        education_level, education_fields = extract_education_requirement(description_html)
        deadline, deadline_confidence = extract_deadline(description_html)

        apply_url = job.get("url")

        builder.add({
            "id": f"remotive-{job_id}",
            "title": title,
            "opportunity_type": opportunity_type,
            "organisation": {
                "name": company_name,
                "type": "unverified",  # Remotive aggregates from many employers; can't independently verify org type
                "verified": False,
            },
            "location": location,
            "work_mode": infer_work_mode(candidate_location) or "remote_global",
            "seniority": infer_seniority(title),
            "categories": categories,
            "specialisations": categories,
            "industry": classify_industry(title, description_html),
            "skills_required": [],
            "skills_preferred": [],
            "posted_at": job.get("publication_date"),
            "deadline": deadline,
            "deadline_confidence": deadline_confidence,
            "years_experience_min": years_min,
            "years_experience_max": years_max,
            "education_required": education_level,
            "education_field": education_fields,
            "contract_type": contract_type,
            "source": {
                "name": "Remotive",
                "url": "https://remotive.com",
                "confidence": builder.confidence_for_domain("remotive.com"),
                "last_seen_at": now_iso(),
            },
            "apply_url": apply_url,
            "apply_is_official": False,  # Remotive is an aggregator, not the employer's own channel
            "flags": [],
            "eligibility_notes": None,
            "summary": html_to_text(description_html),
            "raw_description_url": apply_url,
        })
        added += 1

    return added
