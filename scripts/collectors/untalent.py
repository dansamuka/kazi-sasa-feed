"""UN Talent JSON/RSS feed collector.

UN Talent provides JSON and RSS job feeds after access is requested. The
exact feed URL is supplied through UNTALENT_FEED_URL, keeping the collector
compatible with either format and avoiding hard-coding account-specific URLs.
"""
from __future__ import annotations

import email.utils
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any

from normalizers.text import as_text, as_text_list
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


def _iso_date(value: str | None) -> str | None:
    if not value:
        return None
    text = value.strip()
    if text.endswith("Z") or "T" in text:
        return text
    try:
        parsed = email.utils.parsedate_to_datetime(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    except (TypeError, ValueError, OverflowError):
        return text


def _json_rows(payload: Any) -> list[dict]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("jobs", "results", "data", "items", "openings"):
        value = payload.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
        if isinstance(value, dict):
            for nested in ("jobs", "results", "data", "items"):
                rows = value.get(nested)
                if isinstance(rows, list):
                    return [row for row in rows if isinstance(row, dict)]
    return []


def _rss_rows(text: str) -> list[dict]:
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return []
    rows = []
    for item in root.findall(".//item"):
        row: dict[str, Any] = {}
        for child in item:
            key = child.tag.split("}")[-1]
            value = "".join(child.itertext()).strip()
            if key == "category":
                row.setdefault("categories", []).append(value)
            elif key in row:
                existing = row[key]
                row[key] = existing + [value] if isinstance(existing, list) else [existing, value]
            else:
                row[key] = value
        rows.append(row)
    return rows


def _field(job: dict, *keys, default=None):
    for key in keys:
        value = job.get(key)
        if value not in (None, "", [], {}):
            return value
    return default


def _stable_id(job: dict, title: str, url: str | None) -> str:
    raw = _field(job, "id", "job_id", "guid", "slug")
    if raw:
        value = re.sub(r"[^A-Za-z0-9._-]+", "-", as_text(raw) or "").strip("-")
        if value:
            return f"untalent-{value}"
    if url:
        tail = url.rstrip("/").split("/")[-1]
        if tail:
            return f"untalent-{tail}"
    slug = re.sub(r"[^a-z0-9]+", "-", title.casefold()).strip("-")[:64]
    return f"untalent-{slug or 'job'}"


def collect_untalent(builder, feed_url: str, token: str | None = None, session=None) -> int:
    import requests

    client = session or requests
    headers = {"Accept": "application/json, application/rss+xml, application/xml;q=0.9"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        response = client.get(feed_url, headers=headers, timeout=30)
        response.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        print(f"WARN untalent: fetch failed - {exc}", file=sys.stderr)
        return 0

    try:
        rows = _json_rows(response.json())
    except Exception:  # noqa: BLE001
        rows = _rss_rows(getattr(response, "text", ""))

    added = 0
    for job in rows:
        title = as_text(_field(job, "title", "name", "job_title"))
        if not title:
            continue
        org_value = _field(job, "organization", "organisation", "company", "agency", "source")
        org_name = as_text(org_value) or "UN Talent-listed organisation"
        raw_location = as_text(_field(job, "location", "locations", "duty_station", "city", "country"))
        description = as_text(_field(job, "description", "summary", "body", "content")) or ""
        location = parse_location(raw_location)
        if not is_relevant_opportunity(location, description):
            continue

        url = as_text(_field(job, "apply_url", "application_url", "url", "link"))
        categories_raw = as_text_list(_field(job, "areas", "categories", "category", "functions", default=[]))
        categories = builder.map_specialisations(categories_raw, source_key="untalent")
        years_min, years_max = extract_years_experience(description)
        education_level, education_fields = extract_education_requirement(description)
        extracted_deadline, deadline_confidence = extract_deadline(description)
        deadline = as_text(_field(job, "deadline", "closing_date", "expires_at")) or extracted_deadline
        if deadline and deadline_confidence == "unknown":
            deadline_confidence = "explicit"

        builder.add({
            "id": _stable_id(job, title, url),
            "title": title,
            "opportunity_type": "internship" if "intern" in title.casefold() else "job",
            "organisation": {"name": org_name, "type": "multilateral", "verified": True},
            "location": location,
            "work_mode": infer_work_mode(" ".join(part for part in (raw_location, description[:500]) if part)),
            "seniority": infer_seniority(title),
            "categories": categories,
            "specialisations": categories,
            "industry": builder.industry_for_specialisations(categories) or classify_industry(title, description) or "development_humanitarian",
            "skills_required": [],
            "skills_preferred": [],
            "posted_at": _iso_date(as_text(_field(job, "published_at", "posted_at", "pubDate", "date"))),
            "deadline": deadline,
            "deadline_confidence": deadline_confidence,
            "years_experience_min": years_min,
            "years_experience_max": years_max,
            "education_required": education_level,
            "education_field": education_fields,
            "contract_type": extract_contract_type(title, " ".join(as_text_list(_field(job, "contract", "contract_type"))) + " " + description),
            "source": {
                "name": "UN Talent",
                "url": "https://untalent.org/",
                "confidence": builder.confidence_for_domain("untalent.org"),
                "last_seen_at": now_iso(),
            },
            "apply_url": url,
            "apply_is_official": bool(url and "untalent.org" not in url.casefold()),
            "flags": [],
            "eligibility_notes": None,
            "summary": html_to_text(description),
            "raw_description_url": url,
        })
        added += 1
    return added
