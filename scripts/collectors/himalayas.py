"""Himalayas (himalayas.app) remote jobs collector.

Endpoint: GET https://himalayas.app/jobs/api?limit=20&offset=N
Docs: https://himalayas.app/docs/remote-jobs-api
OpenAPI spec: https://himalayas.app/docs/openapi.json

Confirmed genuinely free, no API key, no signup (verified directly against
Himalayas's own docs before building this - not taken on faith from a
third-party list). Usage terms per their docs: link back to Himalayas and
credit it as the source; don't redistribute Himalayas jobs to competing
aggregators (Jooble, Google Jobs, LinkedIn Jobs, etc.) - neither restriction
affects us, since we're building our own app, not a redistribution service.
Data is cached and refreshed every 24h on Himalayas's side, so there's no
benefit to calling this more than once a day.

Max 20 records per request; paginate via `offset`. Global remote-jobs board,
not Africa-specific, so every result goes through the same
shared is_relevant_opportunity() filtering used
for Greenhouse/Lever/Ashby/Pinpoint - Himalayas's own `locationRestrictions`
field (empty array = worldwide, populated = restricted to those countries)
maps directly onto that.

Confirmed response field shape (verified against a real sample response and
Himalayas's own code examples in their docs):
{
  "updatedAt": 1783290417, "offset": 0, "limit": 20, "totalCount": 106543,
  "jobs": [
    {
      "title": "...", "excerpt": "...", "description": "<p>...</p>" (full HTML),
      "companyName": "...", "companySlug": "...", "companyLogo": "...",
      "employmentType": "Intern" | "Full-time" | ... ,
      "minSalary": 80000, "maxSalary": 120000, "currency": "USD",
      "locationRestrictions": [] | ["United States", ...],
      "timezoneRestrictions": [],
      "categories": ["Engineering"], "parentCategories": [...],
    }, ...
  ]
}

Field names NOT explicitly confirmed from available docs (job id/guid,
canonical job URL, published-at timestamp, seniority): this collector reads
several plausible key names defensively (see _first_present()) rather than
assuming one. The first live run's log will reveal which keys actually exist
if none of the guesses match - check there before assuming this is broken.

NOT execution-tested against the live API from this sandbox.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone

from ._common import (
    classify_industry, extract_contract_type, extract_deadline, extract_education_requirement,
    extract_years_experience, html_to_text,
    infer_seniority, is_relevant_opportunity, now_iso,
)

MAX_PAGES = 15  # 15 * 20 = 300 most-recent listings per run; bounded to keep this collector's runtime and request count reasonable


def _first_present(job: dict, *keys: str):
    for k in keys:
        if job.get(k) not in (None, ""):
            return job[k]
    return None


def _safe_id_component(raw) -> str:
    """Himalayas' 'id'/'guid' field turned out, from the first real live run's
    error log, to be the full canonical job URL, not a short id/slug as
    assumed when this collector was written - e.g.
    "https://himalayas.app/companies/strada-inc/jobs/sap-successfactors-consultant".
    Using that raw string directly broke validate_feed.py's id-stability
    check (slashes/colons risk breaking stability across regenerations - see
    SCHEMA.md §24.4). Extract the last path segment (the actual job slug)
    rather than using the whole URL, same pattern already used in
    ashby.py's _job_id_from_url for the same reason.
    """
    text = str(raw)
    if "/" in text:
        tail = text.rstrip("/").split("/")[-1]
        if tail:
            return tail
    # Not URL-shaped, or empty tail - still strip anything that could break
    # id stability, being conservative rather than trusting an unknown shape.
    return "".join(c if c.isalnum() or c in "-_" else "-" for c in text)[:120]


def _unix_or_iso_to_iso(value) -> str | None:
    """First live run's error log confirmed Himalayas' per-job timestamp
    fields are raw Unix epoch seconds (e.g. 1783824459), matching the same
    convention already seen in their own docs example for the top-level
    `updatedAt` field - this collector originally assumed an ISO string here
    and was wrong. Handles both shapes defensively since the exact field
    that ends up populated (publishedAt/postedAt/pubDate/createdAt) wasn't
    confirmed to have one fixed format from documentation alone.
    """
    if value is None:
        return None
    if isinstance(value, str):
        # Already string - assume ISO-ish and pass through; downstream
        # validate_feed.py will catch anything genuinely malformed.
        return value
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc).isoformat().replace("+00:00", "Z")
    except (TypeError, ValueError, OSError):
        return None


def _employment_type_to_opportunity_type(raw: str | None) -> str:
    if not raw:
        return "job"
    low = raw.lower()
    if "intern" in low:
        return "internship"
    if "fellow" in low:
        return "fellowship"
    return "job"


def _employment_type_to_contract_type(raw: str | None, title: str, description: str) -> str:
    if raw:
        low = raw.lower()
        if "part" in low:
            return "part_time"
        if "contract" in low:
            return "contract"
        if "full" in low:
            return "permanent"
    return extract_contract_type(title, description)


def _location_from_restrictions(restrictions: list, title: str, description: str) -> dict:
    """Himalayas gives locationRestrictions as an explicit list of allowed
    countries (empty = worldwide) - a much cleaner signal than free-text
    parsing when present, so this builds the location dict directly rather
    than routing through parse_location(). An empty list is treated as a
    positive "worldwide" signal, same spirit as _REMOTE_POSITIVE_SIGNAL
    elsewhere in this pipeline.
    """
    from ._common import _AFRICAN_COUNTRY_MAP  # noqa: PLC0415 - internal reuse, not a public API

    if not restrictions:
        return {
            "raw": "Worldwide (no location restriction)", "country": None, "region": None,
            "is_remote_from_kenya": True, "scope": "international", "relocation_country": None,
        }

    restriction_lower = [r.lower().strip() for r in restrictions]
    matched_african = next(
        (name for r in restriction_lower for name in _AFRICAN_COUNTRY_MAP.values() if name.lower() == r),
        None,
    )
    raw_str = ", ".join(restrictions)

    if matched_african:
        return {
            "raw": raw_str, "country": matched_african, "region": None,
            "is_remote_from_kenya": matched_african.lower() == "kenya",
            "scope": "regional", "relocation_country": None,
        }

    # Restricted to one or more specific non-African countries - not relevant
    # unless role-specific international mobility evidence overrides it.
    return {
        "raw": raw_str, "country": restrictions[0], "region": None,
        "is_remote_from_kenya": False, "scope": "international", "relocation_country": None,
    }


def collect_himalayas(builder, max_pages: int = MAX_PAGES, session=None) -> int:
    import requests
    client = session or requests

    added = 0
    for page in range(max_pages):
        offset = page * 20
        try:
            resp = client.get(
                "https://himalayas.app/jobs/api",
                params={"limit": 20, "offset": offset},
                timeout=30,
            )
            resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            print(f"WARN himalayas[offset={offset}]: fetch failed - {exc}", file=sys.stderr)
            break

        payload = resp.json()
        jobs = payload.get("jobs", [])
        if not jobs:
            break

        for job_position, job in enumerate(jobs):
            title = job.get("title")
            job_id = _first_present(job, "id", "guid", "slug", "companySlug")
            if not title or not job_id:
                continue
            # companySlug alone isn't unique per-job, so combine with title-hash-ish
            # offset+index would be more stable; use offset + position as a
            # last-resort uniqueness key if no better id was found.
            stable_id = _safe_id_component(_first_present(job, "id", "guid") or f"{job_id}-{offset}-{job_position}")

            description_html = job.get("description") or job.get("excerpt") or ""
            company_name = job.get("companyName") or "Unknown company"

            restrictions = job.get("locationRestrictions") or []
            location = _location_from_restrictions(restrictions, title, description_html)

            if not is_relevant_opportunity(location, description_html):
                continue

            categories = job.get("categories") or []
            mapped_categories = builder.map_specialisations(categories, source_key="himalayas")

            employment_type = job.get("employmentType")
            years_min, years_max = extract_years_experience(description_html)
            education_level, education_fields = extract_education_requirement(description_html)
            deadline, deadline_confidence = extract_deadline(description_html)

            min_salary = job.get("minSalary")
            max_salary = job.get("maxSalary")
            currency = job.get("currency")
            compensation = None
            if min_salary and max_salary and currency:
                compensation = {
                    "min": int(min_salary), "max": int(max_salary),
                    "currency": currency, "period": "year", "disclosed": True,
                }

            apply_url = _first_present(job, "applyUrl", "url", "link", "jobUrl")
            if not apply_url and job.get("companySlug"):
                # Best-effort fallback construction if no direct URL field was found -
                # Himalayas job detail pages follow this pattern on their own site.
                apply_url = f"https://himalayas.app/companies/{job['companySlug']}/jobs/{stable_id}"

            builder.add({
                "id": f"himalayas-{stable_id}",
                "title": title,
                "opportunity_type": _employment_type_to_opportunity_type(employment_type),
                "organisation": {
                    "name": company_name,
                    "type": "unverified",  # Himalayas aggregates from many employers; can't independently verify org type
                    "verified": False,
                },
                "location": location,
                "work_mode": "remote_global" if not restrictions else ("remote_kenya" if location.get("is_remote_from_kenya") else None),
                "seniority": infer_seniority(title),
                "categories": mapped_categories,
                "specialisations": mapped_categories,
                "industry": classify_industry(title, description_html),
                "skills_required": [],
                "skills_preferred": [],
                "posted_at": _unix_or_iso_to_iso(_first_present(job, "publishedAt", "postedAt", "pubDate", "createdAt")),
                "deadline": deadline,
                "deadline_confidence": deadline_confidence,
                "years_experience_min": years_min,
                "years_experience_max": years_max,
                "education_required": education_level,
                "education_field": education_fields,
                "contract_type": _employment_type_to_contract_type(employment_type, title, description_html),
                "source": {
                    "name": "Himalayas",
                    "url": "https://himalayas.app",
                    "confidence": builder.confidence_for_domain("himalayas.app"),
                    "last_seen_at": now_iso(),
                },
                "apply_url": apply_url,
                "apply_is_official": False,  # Himalayas is an aggregator, not the employer's own channel
                "flags": [],
                "eligibility_notes": None,
                "summary": html_to_text(description_html),
                "raw_description_url": apply_url,
                **({"compensation": compensation} if compensation else {}),
            })
            added += 1

        total_count = payload.get("totalCount", 0)
        if offset + 20 >= total_count:
            break  # reached the end of the feed

    return added
