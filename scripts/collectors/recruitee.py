"""Public Recruitee Careers Site API collector.

Endpoint documented by Recruitee:
    GET https://{subdomain}.recruitee.com/api/offers/

The endpoint returns published jobs for a company's public careers site and
requires no employer API token. Response fields vary slightly by careers-site
version and enabled translations, so the parser deliberately accepts the
common variants while refusing malformed records.
"""
from __future__ import annotations

import re
import sys
from typing import Iterable

from normalizers.text import as_text, as_text_list
from normalizers.temporal import normalise_datetime
from ._common import (
    classify_industry,
    extract_contract_type,
    extract_deadline,
    extract_education_requirement,
    extract_years_experience,
    html_to_text,
    infer_seniority,
    infer_work_mode,
    is_relevant_opportunity,
    now_iso,
    parse_location,
)


def _first(mapping: dict, *keys, default=None):
    for key in keys:
        value = mapping.get(key)
        if value not in (None, "", [], {}):
            return value
    return default


def _offers(payload) -> list[dict]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("offers", "jobs", "data", "results"):
        value = payload.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
        if isinstance(value, dict):
            for nested in ("offers", "jobs", "data", "results"):
                rows = value.get(nested)
                if isinstance(rows, list):
                    return [row for row in rows if isinstance(row, dict)]
    return []


def _location_text(job: dict) -> str | None:
    locations = _first(job, "locations", "location", "job_location", "office")
    values: list[str] = []
    for value in as_text_list(locations):
        if value and value not in values:
            values.append(value)
    for key in ("city", "state", "country", "country_name"):
        value = as_text(job.get(key))
        if value and value not in values:
            values.append(value)
    return ", ".join(values) or None


def _stable_id(job: dict, subdomain: str, title: str) -> str:
    raw = _first(job, "id", "offer_id", "slug", "offer_slug", "uuid")
    if raw not in (None, ""):
        return f"recruitee-{subdomain}-{raw}"
    url = as_text(_first(job, "careers_url", "url", "offer_url", "apply_url"))
    if url:
        tail = url.rstrip("/").split("/")[-1]
        if tail:
            return f"recruitee-{subdomain}-{tail}"
    slug = re.sub(r"[^a-z0-9]+", "-", title.casefold()).strip("-")[:64]
    return f"recruitee-{subdomain}-{slug or 'job'}"


def _employment_type(job: dict, title: str, description: str) -> str:
    raw = as_text(_first(job, "employment_type", "employmentType", "contract_type", "type"))
    return extract_contract_type(title, " ".join(part for part in (raw, description) if part))


def collect_recruitee_board(builder, company: dict, session=None) -> int:
    import requests

    subdomain = company["subdomain"]
    company_name = company["name"]
    client = session or requests
    url = f"https://{subdomain}.recruitee.com/api/offers/"

    try:
        response = client.get(url, headers={"Accept": "application/json"}, timeout=30)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:  # noqa: BLE001
        print(f"WARN recruitee[{subdomain}]: fetch failed - {exc}", file=sys.stderr)
        return 0

    added = 0
    for job in _offers(payload):
        title = as_text(_first(job, "title", "name", "job_title"))
        if not title:
            continue
        if str(job.get("status", "")).casefold() in {"closed", "archived", "draft", "unpublished"}:
            continue

        description_html = as_text(_first(job, "description", "description_html", "descriptionHtml", "job_description")) or ""
        requirements_html = as_text(_first(job, "requirements", "requirements_html", "requirementsHtml")) or ""
        full_text = "\n".join(part for part in (description_html, requirements_html) if part)
        summary = html_to_text(full_text)
        raw_location = _location_text(job)
        location = parse_location(raw_location)
        if not is_relevant_opportunity(location, full_text):
            continue

        departments = as_text_list(_first(job, "department", "departments", "category", "categories", default=[]))
        tags = as_text_list(job.get("tags"))
        raw_categories = departments + [value for value in tags if value not in departments]
        categories = builder.map_specialisations(raw_categories, source_key=f"recruitee:{subdomain}")

        job_url = as_text(_first(job, "careers_url", "url", "offer_url", "job_url"))
        apply_url = as_text(_first(job, "apply_url", "application_url", "careers_apply_url")) or job_url
        if not job_url:
            slug = as_text(_first(job, "slug", "offer_slug"))
            job_url = f"https://{subdomain}.recruitee.com/o/{slug}" if slug else f"https://{subdomain}.recruitee.com/"
        if not apply_url:
            apply_url = job_url

        years_min, years_max = extract_years_experience(full_text)
        education_level, education_fields = extract_education_requirement(full_text)
        deadline, deadline_confidence = extract_deadline(full_text)
        structured_deadline = normalise_datetime(_first(job, "closing_date", "deadline", "expires_at"), end_of_day=True)
        deadline = structured_deadline or deadline
        if deadline and deadline_confidence == "unknown":
            deadline_confidence = "explicit"

        workplace = as_text(_first(job, "workplace", "workplace_type", "work_model", "remote"))
        work_mode = infer_work_mode(" ".join(part for part in (raw_location, workplace, title) if part))

        builder.add({
            "id": _stable_id(job, subdomain, title),
            "title": title,
            "opportunity_type": "internship" if "intern" in title.casefold() else "job",
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
            "industry": builder.industry_for_specialisations(categories) or classify_industry(title, full_text),
            "skills_required": [],
            "skills_preferred": [],
            "posted_at": normalise_datetime(_first(job, "published_at", "publishedAt", "created_at", "createdAt")),
            "deadline": deadline,
            "deadline_confidence": deadline_confidence,
            "years_experience_min": years_min,
            "years_experience_max": years_max,
            "education_required": education_level,
            "education_field": education_fields,
            "contract_type": _employment_type(job, title, full_text),
            "source": {
                "name": company_name,
                "url": f"https://{subdomain}.recruitee.com/",
                "confidence": builder.confidence_for_domain("recruitee.com"),
                "last_seen_at": now_iso(),
            },
            "apply_url": apply_url,
            "apply_is_official": True,
            "flags": [],
            "eligibility_notes": None,
            "summary": summary,
            "raw_description_url": job_url,
        })
        added += 1
    return added


def collect_recruitee(builder, boards: Iterable[dict], session=None) -> int:
    return sum(collect_recruitee_board(builder, company, session=session) for company in boards)
