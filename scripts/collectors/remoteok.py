"""RemoteOK (remoteok.com) remote jobs collector.

Endpoint: GET https://remoteok.com/api
Long-established, well-documented public JSON API - no key required.

Known quirk: the response is a JSON *array*, and the first element is a
legal/attribution notice, not a job record (RemoteOK's own long-standing
convention - has been stable for years). This collector skips any array
element that doesn't look like a real job (no `id`/`position` field) rather
than hardcoding "always skip index 0", since relying on positional
assumptions about a third party's array ordering is more fragile than
checking the actual shape of each element.

RemoteOK explicitly markets itself as covering "80% of remote jobs on the
web" and encourages salary transparency from employers - salary_min/
salary_max are present more often here than on most sources.

Confirmed field shape (stable, well-documented public API):
[
  {"legal": "..."},  # first element - not a job, skipped
  {
    "id": "...", "slug": "...", "company": "...", "company_logo": "...",
    "position": "...", "tags": ["python", "react", ...],
    "location": "...",  # free text, often "Worldwide" or a region/country
    "description": "<p>...</p>", "url": "https://remoteok.com/remote-jobs/...",
    "apply_url": "...", "date": "2023-01-01T00:00:00+00:00", "epoch": 1234567890,
    "salary_min": 50000, "salary_max": 90000,
  }, ...
]

Global, tech-skewed remote-jobs board, not Africa-specific - every result
goes through the same shared is_relevant_opportunity() filtering used
elsewhere in this pipeline, applied
to the free-text `location` field via parse_location().

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


def collect_remoteok(builder, session=None) -> int:
    import requests
    client = session or requests

    headers = {"User-Agent": "kazi-sasa-feed/1.0 (+https://github.com/dansamuka/kazi-sasa-feed)"}

    try:
        resp = client.get("https://remoteok.com/api", headers=headers, timeout=30)
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        print(f"WARN remoteok: fetch failed - {exc}", file=sys.stderr)
        return 0

    payload = resp.json()
    if not isinstance(payload, list):
        print("WARN remoteok: unexpected response shape (expected a list)", file=sys.stderr)
        return 0

    added = 0
    for entry in payload:
        # Skip the leading legal-notice element and anything else that
        # doesn't have the shape of a real job record, rather than assuming
        # it's always exactly index 0.
        job_id = entry.get("id")
        title = entry.get("position")
        if not job_id or not title:
            continue

        description_html = entry.get("description") or ""
        raw_location = entry.get("location")
        location = parse_location(raw_location)

        if not is_relevant_opportunity(location, description_html):
            continue

        company_name = entry.get("company") or "Unknown company"
        tags = entry.get("tags") or []
        categories = builder.map_specialisations(tags, source_key="remoteok")

        opportunity_type = "internship" if "intern" in title.lower() else "job"
        years_min, years_max = extract_years_experience(description_html)
        education_level, education_fields = extract_education_requirement(description_html)
        deadline, deadline_confidence = extract_deadline(description_html)

        salary_min = entry.get("salary_min")
        salary_max = entry.get("salary_max")
        compensation = None
        if salary_min and salary_max:
            try:
                compensation = {
                    "min": int(salary_min), "max": int(salary_max),
                    "currency": "USD",  # RemoteOK salaries are consistently USD-denominated
                    "period": "year", "disclosed": True,
                }
            except (TypeError, ValueError):
                compensation = None

        apply_url = entry.get("apply_url") or entry.get("url")
        posted_at = entry.get("date")  # ISO-8601 already, per the documented shape

        builder.add({
            "id": f"remoteok-{job_id}",
            "title": title,
            "opportunity_type": opportunity_type,
            "organisation": {
                "name": company_name,
                "type": "unverified",
                "verified": False,
            },
            "location": location,
            "work_mode": infer_work_mode(raw_location) or "remote_global",
            "seniority": infer_seniority(title),
            "categories": categories,
            "specialisations": categories,
            "industry": classify_industry(title, description_html),
            "skills_required": [],
            "skills_preferred": [],
            "posted_at": posted_at,
            "deadline": deadline,
            "deadline_confidence": deadline_confidence,
            "years_experience_min": years_min,
            "years_experience_max": years_max,
            "education_required": education_level,
            "education_field": education_fields,
            "contract_type": extract_contract_type(title, description_html),
            "source": {
                "name": "RemoteOK",
                "url": "https://remoteok.com",
                "confidence": builder.confidence_for_domain("remoteok.com"),
                "last_seen_at": now_iso(),
            },
            "apply_url": apply_url,
            "apply_is_official": False,
            "flags": [],
            "eligibility_notes": None,
            "summary": html_to_text(description_html),
            "raw_description_url": entry.get("url") or apply_url,
            **({"compensation": compensation} if compensation else {}),
        })
        added += 1

    return added
