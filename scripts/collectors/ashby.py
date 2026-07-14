"""Generic Ashby job-board collector.

Same pattern as greenhouse.py/lever.py: Ashby hosts a public, unauthenticated
per-company job board API. One collector serves any number of companies via
config/ashby_boards.json.

Endpoint: GET https://api.ashbyhq.com/posting-api/job-board/{company}?includeCompensation=true
Docs: https://developers.ashbyhq.com/docs/public-job-posting-api

Field shape (confirmed against Ashby's own docs):
{
  "apiVersion": "1",
  "jobs": [
    {
      "title": "Product Manager",
      "location": "Nairobi, Kenya",
      "secondaryLocations": [...],
      "department": "Product",
      "team": "Growth",
      "isListed": true,
      "isRemote": true,
      "workplaceType": "Remote",
      "descriptionHtml": "<p>...</p>",
      "descriptionPlain": "...",
      "publishedAt": "2021-04-30T16:21:55.393+00:00",
      "employmentType": "FullTime",
      "jobUrl": "https://jobs.ashbyhq.com/example/job-id",
      "applyUrl": "https://jobs.ashbyhq.com/example/job-id/apply",
      "compensation": {
        "compensationTierSummary": "$81K - $87K",
        "compensationTiers": [...]
      }
    }
  ]
}

Note: Ashby's public API doesn't provide a stable per-job id field in all
cases - jobUrl's trailing UUID is used as the stable id component instead.

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

_EMPLOYMENT_TYPE_MAP = {
    "fulltime": "job",
    "parttime": "job",
    "intern": "internship",
    "internship": "internship",
    "contract": "job",
    "temporary": "job",
}


def _job_id_from_url(job_url: str | None, fallback_title: str) -> str:
    if job_url:
        # jobUrl ends in a UUID or slug - last path segment is stable enough.
        tail = job_url.rstrip("/").split("/")[-1]
        if tail:
            return tail
    # Extremely defensive fallback - should rarely trigger since jobUrl is
    # normally present, but never crash the whole collector over one bad record.
    return fallback_title.lower().replace(" ", "-")[:60]


def collect_ashby_board(builder, company: dict, session=None) -> int:
    import requests

    slug = company["board_slug"]
    company_name = company["name"]

    url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
    params = {"includeCompensation": "true"}

    session = session or requests
    try:
        resp = session.get(url, params=params, timeout=30)
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        print(f"WARN ashby[{slug}]: fetch failed - {exc}", file=sys.stderr)
        return 0

    payload = resp.json()
    jobs = payload.get("jobs", [])
    added = 0

    for job in jobs:
        title = job.get("title")
        if not title or job.get("isListed") is False:
            continue

        job_url = job.get("jobUrl")
        job_id = _job_id_from_url(job_url, title)

        raw_location = job.get("location")
        location = parse_location(raw_location)
        # NOTE: previously there was an override here that forced
        # is_remote_from_kenya=True whenever Ashby's own isRemote flag was
        # true and parse_location() hadn't resolved a country - the comment
        # called this "a cleaner signal", but in practice it was the opposite:
        # isRemote=true just means "not tied to one office", not "open to any
        # country", and it was actively undermining parse_location()'s
        # already-correct positive-signal requirement. Concretely, this let
        # postings like "Remote (US)" and "Remote-US" through as relevant,
        # because the old country-detection also failed to catch short "US"/
        # "UK" abbreviations (fixed separately in _common.py). Removed - trust
        # parse_location()'s own logic instead of second-guessing it here.

        description_html = job.get("descriptionHtml")
        description_plain = job.get("descriptionPlain") or ""
        full_description_text = description_plain or (description_html or "")

        # A non-African-located role is still worth keeping if it explicitly
        # offers visa/relocation sponsorship - a genuinely sponsorable role is
        # a real opportunity, unlike a bare "Remote (US)" posting that in
        # practice only hires US residents.
        if not is_relevant_opportunity(location, full_description_text):
            continue

        summary = html_to_text(description_html) or (
            (description_plain[:300] + "...") if len(description_plain) > 300 else description_plain or None
        )

        department = job.get("department") or job.get("team") or ""
        categories = builder.map_specialisations([department], source_key=f"ashby:{slug}") if department else []

        employment_type_raw = (job.get("employmentType") or "").lower()
        opportunity_type = _EMPLOYMENT_TYPE_MAP.get(employment_type_raw, "job")
        if "intern" in title.lower():
            opportunity_type = "internship"

        workplace_type = (job.get("workplaceType") or "").lower()
        work_mode = None
        if workplace_type == "remote":
            work_mode = "remote_global"
        elif workplace_type == "hybrid":
            work_mode = "hybrid"
        elif workplace_type in ("on-site", "onsite"):
            work_mode = "onsite"

        years_min, years_max = extract_years_experience(full_description_text)
        education_level, education_fields = extract_education_requirement(full_description_text)
        deadline, deadline_confidence = extract_deadline(full_description_text)

        compensation = None
        comp = job.get("compensation") or {}
        tiers = comp.get("compensationTiers") or []
        if tiers:
            # Ashby's compensation is tiered/leveled rather than a flat range;
            # take the widest min-to-max span across all disclosed tiers as a
            # reasonable single range rather than picking one tier arbitrarily.
            mins = [t.get("minValue") for t in tiers if isinstance(t.get("minValue"), (int, float))]
            maxs = [t.get("maxValue") for t in tiers if isinstance(t.get("maxValue"), (int, float))]
            currencies = {t.get("currencyCode") for t in tiers if t.get("currencyCode")}
            if mins and maxs and len(currencies) == 1:
                compensation = {
                    "min": int(min(mins)),
                    "max": int(max(maxs)),
                    "currency": next(iter(currencies)),
                    "period": "year",
                    "disclosed": True,
                }

        apply_url = job.get("applyUrl") or job_url

        opportunity = {
            "id": f"ashby-{slug}-{job_id}",
            "title": title,
            "opportunity_type": opportunity_type,
            "organisation": {
                "name": company_name,
                "type": company.get("type", "unverified"),
                "verified": True,
            },
            "location": location,
            "work_mode": work_mode,
            "seniority": infer_seniority(title),
            "categories": categories,
            "specialisations": categories,
            "industry": builder.industry_for_specialisations(categories) or classify_industry(title, full_description_text),
            "skills_required": [],
            "skills_preferred": [],
            "posted_at": job.get("publishedAt"),
            "deadline": deadline,
            "deadline_confidence": deadline_confidence,
            "years_experience_min": years_min,
            "years_experience_max": years_max,
            "education_required": education_level,
            "education_field": education_fields,
            "contract_type": extract_contract_type(title, full_description_text),
            "source": {
                "name": company_name,
                "url": f"https://jobs.ashbyhq.com/{slug}",
                "confidence": builder.confidence_for_domain("ashbyhq.com"),
                "last_seen_at": now_iso(),
            },
            "apply_url": apply_url,
            "apply_is_official": True,  # employer's own Ashby-hosted apply flow
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


def collect_ashby(builder, boards: Iterable[dict], session=None) -> int:
    total = 0
    for company in boards:
        total += collect_ashby_board(builder, company, session=session)
    return total
