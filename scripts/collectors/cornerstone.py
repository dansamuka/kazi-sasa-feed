"""Public Cornerstone/CSOD career-site collector for World Bank Group and peers."""
from __future__ import annotations

import re
import sys
from typing import Any, Iterable
from urllib.parse import urlparse

from normalizers.temporal import normalise_datetime
from ._common import (
    classify_industry,
    extract_contract_type,
    extract_deadline,
    extract_education_requirement,
    extract_languages_required,
    extract_years_experience,
    html_to_text,
    infer_seniority,
    infer_work_mode,
    now_iso,
    parse_location,
)
from .official_common import clean_text, is_official_opportunity_in_scope, stable_official_id


def _extract_context(html: str) -> tuple[str | None, str | None]:
    token_patterns = [
        r"csod\.context\.token\s*=\s*['\"]([^'\"]+)",
        r"['\"]token['\"]\s*:\s*['\"]([^'\"]+)",
    ]
    cloud_patterns = [
        r"csod\.context\.endpoints\.cloud\s*=\s*['\"]([^'\"]+)",
        r"['\"]cloud['\"]\s*:\s*['\"]([^'\"]+)",
    ]
    token = next((match.group(1) for pattern in token_patterns if (match := re.search(pattern, html))), None)
    cloud = next((match.group(1) for pattern in cloud_patterns if (match := re.search(pattern, html))), None)
    return token, cloud


def _requisitions(payload: Any) -> tuple[list[dict], int]:
    if not isinstance(payload, dict):
        return [], 0
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    rows = data.get("requisitions") or data.get("jobs") or data.get("results") or []
    rows = [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []
    total = data.get("totalCount") or data.get("total") or len(rows)
    try:
        total = int(total)
    except (TypeError, ValueError):
        total = len(rows)
    return rows, total


def _location_text(job: dict) -> str | None:
    locations = job.get("locations") or job.get("jobLocations") or []
    if not isinstance(locations, list):
        locations = [locations]
    values: list[str] = []
    for item in locations:
        if isinstance(item, dict):
            for key in ("city", "state", "country", "displayName", "name"):
                value = clean_text(item.get(key))
                if value and value not in values:
                    values.append(value)
        else:
            value = clean_text(item)
            if value:
                values.append(value)
    return ", ".join(values) or clean_text(job.get("location"))


def _job_url(target: dict, job: dict) -> str:
    explicit = clean_text(job.get("jobUrl") or job.get("url") or job.get("applyUrl"))
    if explicit:
        return explicit
    req = job.get("requisitionId") or job.get("id") or job.get("requisitionNumber")
    company = target.get("company") or urlparse(target["career_site_url"]).hostname.split(".")[0]
    site_id = int(target.get("site_id", 1))
    return f"https://{company}.csod.com/ux/ats/careersite/{site_id}/home/requisition/{req}?c={company}"


def _add_job(builder, target: dict, job: dict) -> bool:
    title = clean_text(job.get("displayJobTitle") or job.get("jobTitle") or job.get("title"))
    if not title:
        return False
    description = clean_text(job.get("externalDescription") or job.get("description") or job.get("jobDescription")) or ""
    raw_location = _location_text(job)
    location = parse_location(raw_location)
    if not is_official_opportunity_in_scope(
        location, title, description, allow_non_african=bool(target.get("include_non_african_roles"))
    ):
        return False
    categories = builder.infer_specialisations(title, description, limit=3)
    years_min, years_max = extract_years_experience(description)
    education, fields = extract_education_requirement(description)
    deadline = normalise_datetime(job.get("applicationDeadline") or job.get("validThrough") or job.get("endDate"), end_of_day=True)
    deadline_confidence = "explicit" if deadline else "unknown"
    if not deadline:
        deadline, deadline_confidence = extract_deadline(description)
    url = _job_url(target, job)
    builder.add({
        "id": stable_official_id("cornerstone", target["organisation_id"], url, title),
        "title": title,
        "opportunity_type": "internship" if "intern" in title.casefold() else "job",
        "organisation": {"name": target["name"], "type": target.get("type", "multilateral"), "verified": True},
        "location": location,
        "work_mode": infer_work_mode(" ".join(filter(None, [raw_location, title, description[:500]]))),
        "seniority": infer_seniority(title),
        "categories": categories,
        "specialisations": categories,
        "source_context_specialisations": builder.map_specialisations(list(target.get("default_specialisations") or []), source_key="cornerstone", limit=3),
        "industry": builder.industry_for_specialisations(categories) or classify_industry(title, description),
        "skills_required": [],
        "skills_preferred": [],
        "posted_at": normalise_datetime(job.get("postedDate") or job.get("datePosted") or job.get("postingStartDate")),
        "deadline": deadline,
        "deadline_confidence": deadline_confidence,
        "years_experience_min": years_min,
        "years_experience_max": years_max,
        "education_required": education,
        "education_field": fields,
        "languages_required": extract_languages_required(description),
        "contract_type": extract_contract_type(title, description),
        "source": {"name": "Cornerstone-hosted institutional board", "url": target["career_site_url"], "confidence": "official", "last_seen_at": now_iso()},
        "apply_url": url,
        "apply_is_official": True,
        "flags": [],
        "eligibility_notes": None,
        "summary": html_to_text(description),
        "raw_description_url": url,
    })
    return True


def collect_cornerstone_target(builder, target: dict, session=None) -> int:
    import requests

    client = session or requests
    career_url = target["career_site_url"]
    try:
        page = client.get(career_url, headers={"Accept": "text/html"}, timeout=30)
        page.raise_for_status()
        token, cloud = _extract_context(page.text)
    except Exception as exc:  # noqa: BLE001
        print(f"WARN cornerstone[{target.get('organisation_id')}]: career page fetch failed - {exc}", file=sys.stderr)
        return 0
    if not token or not cloud:
        print(f"WARN cornerstone[{target.get('organisation_id')}]: public token or cloud endpoint not found", file=sys.stderr)
        return 0

    site_id = int(target.get("site_id", 1))
    page_size = min(int(target.get("page_size", 50)), 100)
    max_pages = int(target.get("max_pages", 20))
    api_url = cloud.rstrip("/") + "/rec-job-search/external/jobs"
    company = target.get("company") or urlparse(career_url).hostname.split(".")[0]
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Origin": f"https://{company}.csod.com",
        "Referer": f"https://{company}.csod.com/",
        "Csod-Accept-Language": "en-US",
    }
    added = 0
    for page_number in range(1, max_pages + 1):
        payload = {
            "careerSiteId": site_id,
            "careerSitePageId": int(target.get("page_id", 1)),
            "pageNumber": page_number,
            "pageSize": page_size,
            "cultureId": int(target.get("culture_id", 1)),
            "searchText": "",
            "cultureName": target.get("culture_name", "en-US"),
            "states": [], "countryCodes": [], "cities": [], "placeID": "", "radius": None,
            "postingsWithinDays": None, "customFieldCheckboxKeys": [], "customFieldDropdowns": [], "customFieldRadios": [],
        }
        try:
            response = client.post(api_url, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            rows, total = _requisitions(response.json())
        except Exception as exc:  # noqa: BLE001
            print(f"WARN cornerstone[{target.get('organisation_id')}]: API page {page_number} failed - {exc}", file=sys.stderr)
            break
        for job in rows:
            if _add_job(builder, target, job):
                added += 1
        if not rows or page_number * page_size >= total:
            break
    return added


def collect_cornerstone(builder, targets: Iterable[dict], session=None) -> int:
    return sum(collect_cornerstone_target(builder, target, session=session) for target in targets)
