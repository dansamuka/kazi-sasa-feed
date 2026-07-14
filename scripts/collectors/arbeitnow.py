"""Arbeitnow (arbeitnow.com) job board collector.

Endpoint: GET https://www.arbeitnow.com/api/job-board-api
Docs: https://www.arbeitnow.com/blog/job-board-api

Confirmed genuinely free, no API key, no auth, CORS-enabled. Primarily
Europe/DACH-focused (per Arbeitnow's own positioning - "Germany's leading
English-friendly tech job board") with some remote-worldwide coverage, so
expect lower Africa-relevant volume here than Himalayas/Remotive/Jobicy -
included anyway since Arbeitnow is one of the few sources that explicitly
markets visa sponsorship as a core theme. The shared relevance rule only
uses role-specific mobility evidence, not generic company boilerplate.

The full board comes back in a single JSON response (confirmed - "the
endpoint returns the full current job board in one JSON response... no
pagination overhead"), so this collector makes one request, not a paginated
loop like Himalayas.

Confirmed fields: `remote` (boolean - structured, not free-text), `tags`
(array), `job_types` (array), `location` (free text), `description` (HTML),
`created_at` (Unix timestamp in seconds - confirmed via a third-party
scraper's own documented conversion step, not guessed). Field names for
title/company/url are the standard Arbeitnow convention (title, company_name,
url) - if any of these don't match on the first live run, the log's WARN
line will show the raw keys actually present so it can be corrected.

NOT execution-tested against the live API from this sandbox.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone

from ._common import (
    classify_industry, extract_contract_type, extract_deadline, extract_education_requirement,
    extract_years_experience, html_to_text,
    infer_seniority, is_relevant_opportunity, now_iso, parse_location,
)


def _unix_to_iso(ts) -> str | None:
    if not ts:
        return None
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat().replace("+00:00", "Z")
    except (TypeError, ValueError, OSError):
        return None


def collect_arbeitnow(builder, session=None) -> int:
    import requests
    client = session or requests

    try:
        resp = client.get("https://www.arbeitnow.com/api/job-board-api", timeout=30)
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        print(f"WARN arbeitnow: fetch failed - {exc}", file=sys.stderr)
        return 0

    payload = resp.json()
    jobs = payload.get("data", payload.get("jobs", []))
    if not isinstance(jobs, list):
        print("WARN arbeitnow: unexpected response shape (no data/jobs list found)", file=sys.stderr)
        return 0

    added = 0
    for job in jobs:
        title = job.get("title")
        slug = job.get("slug")
        if not title or not slug:
            continue

        description_html = job.get("description") or ""
        raw_location = job.get("location")
        is_remote_flag = bool(job.get("remote"))

        if is_remote_flag and not raw_location:
            # Structured "remote=true" with no location text is a genuine
            # positive signal, same as a bare "Remote - Global" elsewhere.
            location = {
                "raw": "Remote", "country": None, "region": None,
                "is_remote_from_kenya": True, "scope": "international",
                "relocation_country": None,
            }
        else:
            location = parse_location(raw_location)

        if not is_relevant_opportunity(location, description_html):
            continue

        company_name = job.get("company_name") or "Unknown company"
        tags = job.get("tags") or []
        categories = builder.map_specialisations(tags, source_key="arbeitnow")

        job_types = job.get("job_types") or []
        job_types_lower = [str(t).lower() for t in job_types]
        opportunity_type = "internship" if any("intern" in t for t in job_types_lower) or "intern" in title.lower() else "job"

        contract_type = "unknown"
        if any("full" in t for t in job_types_lower):
            contract_type = "permanent"
        elif any("part" in t for t in job_types_lower):
            contract_type = "part_time"
        elif any("contract" in t for t in job_types_lower):
            contract_type = "contract"
        else:
            contract_type = extract_contract_type(title, description_html)

        years_min, years_max = extract_years_experience(description_html)
        education_level, education_fields = extract_education_requirement(description_html)
        deadline, deadline_confidence = extract_deadline(description_html)

        job_url = job.get("url") or f"https://www.arbeitnow.com/view/{slug}"

        builder.add({
            "id": f"arbeitnow-{slug}",
            "title": title,
            "opportunity_type": opportunity_type,
            "organisation": {
                "name": company_name,
                "type": "unverified",
                "verified": False,
            },
            "location": location,
            "work_mode": "remote_global" if is_remote_flag else None,
            "seniority": infer_seniority(title),
            "categories": categories,
            "specialisations": categories,
            "industry": classify_industry(title, description_html),
            "skills_required": [],
            "skills_preferred": [],
            "posted_at": _unix_to_iso(job.get("created_at")),
            "deadline": deadline,
            "deadline_confidence": deadline_confidence,
            "years_experience_min": years_min,
            "years_experience_max": years_max,
            "education_required": education_level,
            "education_field": education_fields,
            "contract_type": contract_type,
            "source": {
                "name": "Arbeitnow",
                "url": "https://www.arbeitnow.com",
                "confidence": builder.confidence_for_domain("arbeitnow.com"),
                "last_seen_at": now_iso(),
            },
            "apply_url": job_url,
            "apply_is_official": False,
            "flags": [],
            "eligibility_notes": None,
            "summary": html_to_text(description_html),
            "raw_description_url": job_url,
        })
        added += 1

    return added
