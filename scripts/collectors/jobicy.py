"""Jobicy (jobicy.com) remote jobs collector.

Endpoint: GET https://jobicy.com/api/v2/remote-jobs
Docs: https://github.com/Jobicy/remote-jobs-api (official, Jobicy-run)

Confirmed genuinely free, no API key. Usage terms (from Jobicy's own docs):
link back to Jobicy, don't redistribute to Jooble/Google Jobs/LinkedIn -
neither affects us. Jobicy intentionally delays publication by 6h on their
side, and asks that the feed not be polled more than "a few times a day" -
respect that; this collector is meant to run alongside the rest of the
pipeline (currently 3x/day), not on a tighter schedule.

`count` param caps at 50 per request with no documented pagination offset,
so a single call is what's available - this collector does not attempt
multi-page pagination (unlike Himalayas, which documents offset-based
paging). Re-check Jobicy's docs if deeper coverage is ever needed; as of
writing there's no documented way to get past the most recent 50.

Confirmed response field shape (from Jobicy's own GitHub docs):
{
  "jobCount": 20,
  "jobs": [
    {
      "id": 12345, "url": "https://jobicy.com/jobs/sr-marketing-specialist",
      "jobTitle": "Senior Marketing Specialist", "companyName": "ABC",
      "companyLogo": "...", "jobIndustry": "Marketing & Sales",
      "jobType": "full-time", "jobGeo": "USA", "jobLevel": "Senior",
      "jobExcerpt": "...", "jobDescription": "<p>...</p>",
      "pubDate": "2017-04-13T16:11:04",
      "annualSalaryMin": "85000", "annualSalaryMax": "95000", "salaryCurrency": "USD",
    }, ...
  ]
}

Global remote-jobs board, not Africa-specific - `jobGeo` is Jobicy's own
region tag (their docs note "Most of the jobs are for people from the
Americas... and Europe/EMEA" - a useful heads-up that coverage here will
likely be thin, same honest framing as Adzuna's South-Africa-only scope).
Routed through parse_location() same as Remotive, since jobGeo is free text
("USA", "Worldwide", "EMEA", etc.), not a structured restriction list.

NOT execution-tested against the live API from this sandbox.
"""
from __future__ import annotations

import sys
from typing import Any

from normalizers.text import as_text, as_text_list

from ._common import (
    classify_industry, extract_contract_type, extract_deadline, extract_education_requirement,
    extract_years_experience, html_to_text,
    infer_seniority, infer_work_mode, is_relevant_opportunity,
    now_iso, parse_location,
)

_JOB_TYPE_MAP = {
    "full-time": "permanent",
    "part-time": "part_time",
    "contract": "contract",
    "freelance": "consultant",
    "internship": "unknown",
}

_LEVEL_MAP = {
    "entry level": "entry",
    "junior": "entry",
    "mid level": "mid",
    "senior level": "senior",
    "expert level": "senior",
    "manager": "leadership",
    "director": "leadership",
}


def _jobicy_seniority(job_level: Any, title: str) -> str | None:
    job_level_text = as_text(job_level, separator=" ")
    if job_level_text:
        mapped = _LEVEL_MAP.get(job_level_text.strip().lower())
        if mapped:
            return mapped
    return infer_seniority(title)


def _first_mapped_industry(builder, terms: list[str]) -> str | None:
    for term in terms:
        mapped = builder.map_industry(term)
        if mapped:
            return mapped
    return None


def collect_jobicy(builder, count: int = 50, tag: str | None = None, session=None) -> int:
    import requests
    client = session or requests

    params = {"count": count}
    if tag:
        params["tag"] = tag

    try:
        resp = client.get("https://jobicy.com/api/v2/remote-jobs", params=params, timeout=30)
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        print(f"WARN jobicy: fetch failed - {exc}", file=sys.stderr)
        return 0

    payload = resp.json()
    jobs = payload.get("jobs", []) if isinstance(payload, dict) else []
    if isinstance(jobs, dict):
        jobs = jobs.get("items") or jobs.get("data") or []
    if not isinstance(jobs, list):
        jobs = []
    added = 0

    for job in jobs:
        if not isinstance(job, dict):
            continue
        job_id = job.get("id")
        title = as_text(job.get("jobTitle"), separator=" / ")
        if job_id is None or not title:
            continue

        description_html = as_text(job.get("jobDescription") or job.get("jobExcerpt"), separator="\n")
        job_geo = as_text(job.get("jobGeo"))
        location = parse_location(job_geo)

        if not is_relevant_opportunity(location, description_html):
            continue

        company_name = as_text(job.get("companyName"), separator=" / ") or "Unknown company"
        industry_terms = as_text_list(job.get("jobIndustry"))
        categories = builder.map_specialisations(industry_terms, source_key="jobicy") if industry_terms else []
        industry_raw = as_text(industry_terms)

        job_type_raw = as_text(job.get("jobType"), separator=" ").lower()
        opportunity_type = "internship" if "intern" in job_type_raw or "intern" in title.lower() else "job"
        contract_type = _JOB_TYPE_MAP.get(job_type_raw) or extract_contract_type(title, description_html)

        years_min, years_max = extract_years_experience(description_html)
        education_level, education_fields = extract_education_requirement(description_html)
        deadline, deadline_confidence = extract_deadline(description_html)

        salary_min = as_text(job.get("annualSalaryMin"), separator="")
        salary_max = as_text(job.get("annualSalaryMax"), separator="")
        currency = as_text(job.get("salaryCurrency"), separator="")
        compensation = None
        if salary_min and salary_max and currency:
            try:
                compensation = {
                    "min": int(salary_min), "max": int(salary_max),
                    "currency": currency, "period": "year", "disclosed": True,
                }
            except (TypeError, ValueError):
                compensation = None  # Jobicy salary fields are strings in the docs' example - guard against non-numeric junk

        apply_url = as_text(job.get("url"), separator="") or None

        builder.add({
            "id": f"jobicy-{job_id}",
            "title": title,
            "opportunity_type": opportunity_type,
            "organisation": {
                "name": company_name,
                "type": "unverified",
                "verified": False,
            },
            "location": location,
            "work_mode": infer_work_mode(job_geo) or "remote_global",
            "seniority": _jobicy_seniority(job.get("jobLevel"), title),
            "categories": categories,
            "specialisations": categories,
            "industry": builder.industry_for_specialisations(categories) or _first_mapped_industry(builder, industry_terms) or classify_industry(title, description_html),
            "skills_required": [],
            "skills_preferred": [],
            "posted_at": as_text(job.get("pubDate"), separator="") or None,
            "deadline": deadline,
            "deadline_confidence": deadline_confidence,
            "years_experience_min": years_min,
            "years_experience_max": years_max,
            "education_required": education_level,
            "education_field": education_fields,
            "contract_type": contract_type,
            "source": {
                "name": "Jobicy",
                "url": "https://jobicy.com",
                "confidence": builder.confidence_for_domain("jobicy.com"),
                "last_seen_at": now_iso(),
            },
            "apply_url": apply_url,
            "apply_is_official": False,
            "flags": [],
            "eligibility_notes": None,
            "summary": html_to_text(description_html),
            "raw_description_url": apply_url,
            **({"compensation": compensation} if compensation else {}),
        })
        added += 1

    return added
