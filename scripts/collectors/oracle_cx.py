"""Public Oracle Candidate Experience career-site collector.

Oracle Recruiting Candidate Experience exposes a public read-only requisition
resource used by the career site itself. The adapter uses that resource when a
site number is configured, then falls back to official HTML/JSON-LD extraction
if the tenant changes shape or temporarily rejects the request.
"""
from __future__ import annotations

import sys
from typing import Any, Iterable
from urllib.parse import urlparse

from .official_common import opportunity_from_jobposting
from .official_html import collect_official_html_target


def _requisition_rows(payload: Any) -> list[dict]:
    """Return job rows from common Oracle CE response envelopes."""
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("requisitionList", "jobs", "results"):
        value = payload.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
    items = payload.get("items")
    if isinstance(items, list):
        direct = [row for row in items if isinstance(row, dict)]
        nested: list[dict] = []
        for row in direct:
            for key in ("requisitionList", "jobs", "results"):
                value = row.get(key)
                if isinstance(value, list):
                    nested.extend(item for item in value if isinstance(item, dict))
        return nested or direct
    return []


def _first(row: dict, *keys: str):
    for key in keys:
        value = row.get(key)
        if value not in (None, "", []):
            return value
    return None


def _jobposting(row: dict, target: dict, site_number: str) -> dict | None:
    title = _first(row, "Title", "title", "JobTitle", "jobTitle", "RequisitionTitle")
    if not title:
        return None
    job_id = _first(row, "Id", "id", "RequisitionId", "requisitionId", "ExternalJobId", "externalJobId")
    career_url = target["career_site_url"].rstrip("/")
    url = _first(row, "ExternalJobUrl", "externalJobUrl", "JobUrl", "jobUrl", "url")
    if not url and job_id:
        parsed = urlparse(career_url)
        language = target.get("language", "en")
        url = f"{parsed.scheme}://{parsed.netloc}/{language}/sites/{site_number}/job/{job_id}"
    description = _first(
        row, "ShortDescriptionStr", "shortDescription", "Description", "description",
        "ExternalDescriptionStr", "externalDescription",
    ) or ""
    location = _first(row, "PrimaryLocation", "primaryLocation", "Location", "location", "WorkLocation", "workLocation")
    if isinstance(location, dict):
        location = ", ".join(str(location.get(key)) for key in ("City", "State", "Country", "Name") if location.get(key))
    return {
        "@type": "JobPosting",
        "title": title,
        "description": description,
        "datePosted": _first(row, "PostedDate", "postedDate", "PostingStartDate", "postingStartDate"),
        "validThrough": _first(row, "PostingEndDate", "postingEndDate", "EndDate", "endDate"),
        "employmentType": _first(row, "WorkerType", "workerType", "EmploymentType", "employmentType"),
        "jobLocation": {"address": {"name": location}} if location else None,
        "url": url or career_url,
    }


def _collect_api(builder, target: dict, session) -> int:
    site_number = target.get("site_number")
    if not site_number:
        return 0
    career_url = target["career_site_url"]
    parsed = urlparse(career_url)
    endpoint = f"{parsed.scheme}://{parsed.netloc}/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
    limit = min(int(target.get("page_size", 25)), 100)
    max_pages = int(target.get("max_pages", 20))
    added = 0
    seen: set[str] = set()
    for page in range(max_pages):
        offset = page * limit
        finder = (
            f"findReqs;siteNumber={site_number},limit={limit},offset={offset},"
            "sortBy=POSTING_DATES_DESC"
        )
        try:
            response = session.get(
                endpoint,
                params={"onlyData": "true", "finder": finder},
                headers={"Accept": "application/json"},
                timeout=30,
            )
            response.raise_for_status()
            payload = response.json()
            rows = _requisition_rows(payload)
        except Exception as exc:  # noqa: BLE001
            print(f"WARN oracle_cx[{target.get('organisation_id')}]: public requisition API failed - {exc}", file=sys.stderr)
            break
        for row in rows:
            posting = _jobposting(row, target, str(site_number))
            if not posting:
                continue
            opportunity = opportunity_from_jobposting(
                builder,
                target,
                posting,
                source_name="Oracle Candidate Experience institutional board",
                source_url=career_url,
                prefix="oracle-cx",
            )
            if opportunity and opportunity["id"] not in seen:
                builder.add(opportunity)
                seen.add(opportunity["id"])
                added += 1
        has_more = payload.get("hasMore") if isinstance(payload, dict) else None
        if not rows or has_more is False or len(rows) < limit:
            break
    return added


def collect_oracle_cx_target(builder, target: dict, session=None) -> int:
    import requests

    client = session or requests
    added = _collect_api(builder, target, client)
    if added:
        return added
    fallback = dict(target)
    fallback["listing_url"] = fallback.pop("career_site_url")
    fallback.setdefault("link_patterns", [r"/job/\d+", r"/jobs/preview/\d+"])
    fallback.setdefault("exclude_patterns", [r"/jobs/?$"])
    fallback.setdefault("max_jobs", 100)
    return collect_official_html_target(
        builder,
        fallback,
        session=client,
        source_name="Oracle Candidate Experience institutional board",
    )


def collect_oracle_cx(builder, targets: Iterable[dict], session=None) -> int:
    return sum(collect_oracle_cx_target(builder, target, session=session) for target in targets)
