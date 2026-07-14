"""Generic Lever public Postings API collector.

Lever exposes an unauthenticated public postings endpoint for every customer
who hasn't explicitly disabled it. Format documented at
https://github.com/lever/postings-api - each company has a `site` slug (e.g.
`jobs.lever.co/sunking` -> `sunking`) and the endpoint

    GET https://api.lever.co/v0/postings/{site}?mode=json

returns a flat JSON array of posting objects. One collector, many customers,
config-file driven.

Field shape (confirmed against Lever's own docs and repo):
[
  {
    "id": "a1b2c3d4-...",           # UUID
    "text": "Account Executive",    # title
    "hostedUrl": "https://jobs.lever.co/example-co/a1b2c3d4-...",
    "applyUrl":  "https://jobs.lever.co/example-co/a1b2c3d4-.../apply",
    "categories": {
      "team": "Sales",
      "department": "Commercial",
      "location": "London",
      "allLocations": ["London", "Remote"],
      "commitment": "Full-time",
      "level": "Senior"
    },
    "descriptionPlain": "Job description in plain text ...",
    "description": "<p>Same description as HTML ...</p>",
    "createdAt": 1740000000000,       # millisecond epoch
    "workplaceType": "hybrid",        # unspecified | on-site | remote | hybrid
    "salaryRange": {"min": 60000, "max": 90000, "currency": "USD", "interval": "per-year-salary"}
  }
]

EU-hosted Lever customers use api.eu.lever.co and jobs.eu.lever.co - the
config file lets us opt individual companies into EU via `region: "eu"`.

NOT execution-tested against the live API from this sandbox.
"""
from __future__ import annotations

import sys
from typing import Iterable

from ._common import (
    html_to_text, infer_seniority, infer_work_mode,
    is_relevant_opportunity, millis_to_iso, now_iso, parse_location,
    classify_industry, extract_years_experience, extract_education_requirement,
    extract_contract_type, extract_deadline,
)


def _api_host(region: str | None) -> tuple[str, str]:
    """Returns (api_host, hosted_host)."""
    if (region or "").lower() == "eu":
        return "api.eu.lever.co", "jobs.eu.lever.co"
    return "api.lever.co", "jobs.lever.co"


def _map_commitment(commitment: str | None) -> str:
    """Lever's `categories.commitment` is free-text ("Full-time", "Intern",
    "Contract", "Fellowship"). Only `internship` and `fellowship` map to
    distinct SCHEMA.md opportunity_type values; everything else is a `job`.
    """
    if not commitment:
        return "job"
    low = commitment.lower()
    if "intern" in low:
        return "internship"
    if "fellow" in low:
        return "fellowship"
    return "job"


def _lever_seniority(categories_level: str | None, title: str | None) -> str | None:
    """Prefer the structured `categories.level` if present; fall back to title."""
    if categories_level:
        low = categories_level.lower()
        if "intern" in low or "junior" in low or "entry" in low or "graduate" in low:
            return "entry"
        if "senior" in low or "principal" in low or "staff" in low or "lead" in low:
            return "senior"
        if "director" in low or "vp" in low or "head" in low:
            return "leadership"
        if "mid" in low:
            return "mid"
    return infer_seniority(title)


def collect_lever_board(builder, company: dict, session=None) -> int:
    """Fetch one company's Lever board and add matching opportunities."""
    import requests

    site = company["site"]
    company_name = company["name"]
    region = company.get("region")
    api_host, hosted_host = _api_host(region)

    url = f"https://{api_host}/v0/postings/{site}"
    params = {"mode": "json"}

    session = session or requests
    try:
        resp = session.get(url, params=params, timeout=30)
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        print(f"WARN lever[{site}]: fetch failed - {exc}", file=sys.stderr)
        return 0

    jobs = resp.json()
    if not isinstance(jobs, list):
        print(f"WARN lever[{site}]: unexpected response shape (expected list)", file=sys.stderr)
        return 0

    added = 0
    for job in jobs:
        lever_id = job.get("id")
        title = job.get("text")
        if not lever_id or not title:
            continue

        categories = job.get("categories") or {}
        raw_location = categories.get("location")
        location = parse_location(raw_location)

        # Some Lever postings are multi-location - fall back to allLocations if
        # the primary is missing or non-informative.
        if not location.get("country") and categories.get("allLocations"):
            for loc in categories["allLocations"]:
                parsed = parse_location(loc)
                if parsed.get("country") or parsed.get("is_remote_from_kenya"):
                    location = parsed
                    break

        description_for_relevance = job.get("description") or job.get("descriptionPlain") or ""
        if not is_relevant_opportunity(location, description_for_relevance):
            continue

        summary = html_to_text(job.get("description")) or (
            (job.get("descriptionPlain") or "")[:300] + "..."
            if job.get("descriptionPlain") and len(job.get("descriptionPlain", "")) > 300
            else job.get("descriptionPlain")
        )

        raw_categories = [c for c in (categories.get("team"), categories.get("department")) if c]
        mapped_categories = builder.map_specialisations(raw_categories, source_key=f"lever:{site}")

        # Salary: only include if all four fields are present. Partial salary
        # data is often more misleading than none (a `min` with no `max` reads
        # as "starting from X" but Lever doesn't guarantee that semantic).
        compensation = None
        salary = job.get("salaryRange") or {}
        if all(k in salary for k in ("min", "max", "currency", "interval")):
            # Lever intervals: "per-year-salary" | "per-hour-wage" etc. Normalize.
            interval = salary["interval"].lower()
            if "year" in interval:
                period = "year"
            elif "month" in interval:
                period = "month"
            elif "hour" in interval:
                period = "hour"
            else:
                period = None
            if period and isinstance(salary["min"], (int, float)) and isinstance(salary["max"], (int, float)):
                compensation = {
                    "min": int(salary["min"]),
                    "max": int(salary["max"]),
                    "currency": salary["currency"],
                    "period": period,
                    "disclosed": True,
                }

        hosted_url = job.get("hostedUrl") or f"https://{hosted_host}/{site}/{lever_id}"
        apply_url = job.get("applyUrl") or f"{hosted_url}/apply"

        description_text = job.get("descriptionPlain") or job.get("description") or ""
        years_min, years_max = extract_years_experience(description_text)
        education_level, education_fields = extract_education_requirement(description_text)
        deadline, deadline_confidence = extract_deadline(description_text)

        opportunity = {
            "id": f"lever-{site}-{lever_id}",
            "title": title,
            "opportunity_type": _map_commitment(categories.get("commitment")),
            "organisation": {
                "name": company_name,
                "type": company.get("type", "unverified"),
                "verified": True,
            },
            "location": location,
            "work_mode": infer_work_mode(raw_location, job.get("workplaceType")),
            "seniority": _lever_seniority(categories.get("level"), title),
            "categories": mapped_categories,
            "specialisations": mapped_categories,
            "industry": builder.industry_for_specialisations(mapped_categories) or classify_industry(title, description_text),
            "skills_required": [],
            "skills_preferred": [],
            "posted_at": millis_to_iso(job.get("createdAt")),
            "deadline": deadline,
            "deadline_confidence": deadline_confidence,
            "years_experience_min": years_min,
            "years_experience_max": years_max,
            "education_required": education_level,
            "education_field": education_fields,
            "contract_type": extract_contract_type(title, description_text),
            "source": {
                "name": company_name,
                "url": f"https://{hosted_host}/{site}",
                "confidence": builder.confidence_for_domain("lever.co"),
                "last_seen_at": now_iso(),
            },
            "apply_url": apply_url,
            # applyUrl is the employer's own Lever-hosted apply page.
            "apply_is_official": True,
            "flags": [],
            "eligibility_notes": None,
            "summary": summary,
            "raw_description_url": hosted_url,
        }
        if compensation:
            opportunity["compensation"] = compensation

        builder.add(opportunity)
        added += 1

    return added


def collect_lever(builder, boards: Iterable[dict], session=None) -> int:
    total = 0
    for company in boards:
        total += collect_lever_board(builder, company, session=session)
    return total
