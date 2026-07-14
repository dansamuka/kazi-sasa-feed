"""Shared helpers for Phase 9 African government vacancy collectors."""
from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import Any

from normalizers.temporal import normalise_datetime
from ._common import (
    classify_industry,
    extract_contract_type,
    extract_deadline,
    extract_education_requirement,
    extract_languages_required,
    extract_years_experience,
    infer_seniority,
    now_iso,
    parse_location,
)


def clean(value: Any) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text or None


def stable_government_id(country_code: str, portal_id: str, advert_reference: str | None, title: str, url: str) -> str:
    seed = "|".join([country_code, portal_id, advert_reference or "", title, url])
    digest = hashlib.sha256(seed.encode("utf-8", errors="ignore")).hexdigest()[:18]
    return f"government-{country_code.lower()}-{portal_id}-{digest}"


def parse_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    match = re.search(r"\d+", str(value).replace(",", ""))
    return int(match.group()) if match else None


def government_opportunity(
    builder,
    portal: dict,
    *,
    title: str,
    apply_url: str,
    raw_location: str | None = None,
    summary: str | None = None,
    advert_reference: str | None = None,
    posted_at: Any = None,
    deadline: Any = None,
    public_service_grade: str | None = None,
    salary_scale: str | None = None,
    number_of_positions: int | None = None,
    citizenship_required: bool | None = None,
    eligible_nationalities: list[str] | None = None,
    application_method: str | None = None,
    application_form_url: str | None = None,
    internal_only: bool = False,
    county_or_region_requirement: str | None = None,
    source_document_url: str | None = None,
    extra_text: str | None = None,
) -> dict:
    title = clean(title) or "Untitled public-service vacancy"
    country_name = portal.get("country_name")
    country_code = portal["country_code"]
    raw_location = clean(raw_location) or country_name
    location = parse_location(raw_location)
    location["country"] = location.get("country") or country_name
    text = " ".join(filter(None, [title, summary, extra_text]))
    inferred = builder.infer_specialisations(title, text, limit=3)
    years_min, years_max = extract_years_experience(text)
    education, fields = extract_education_requirement(text)
    normalised_deadline = normalise_datetime(deadline, end_of_day=True)
    deadline_confidence = "explicit" if normalised_deadline else "unknown"
    if not normalised_deadline:
        normalised_deadline, deadline_confidence = extract_deadline(text)

    source_url = portal["listing_url"]
    return {
        "id": stable_government_id(country_code, portal["id"], advert_reference, title, apply_url),
        "title": title,
        "opportunity_type": "internship" if "intern" in title.casefold() else "job",
        "organisation": {
            "name": portal["name"],
            "type": "government",
            "verified": True,
        },
        "location": location,
        "work_mode": None,
        "seniority": infer_seniority(title),
        "categories": inferred,
        "specialisations": inferred,
        "industry": builder.industry_for_specialisations(inferred) or classify_industry(title, text) or "public_sector",
        "skills_required": [],
        "skills_preferred": [],
        "posted_at": normalise_datetime(posted_at),
        "deadline": normalised_deadline,
        "deadline_confidence": deadline_confidence,
        "years_experience_min": years_min,
        "years_experience_max": years_max,
        "education_required": education,
        "education_field": fields,
        "languages_required": extract_languages_required(text),
        "contract_type": extract_contract_type(title, text),
        "source": {
            "name": portal.get("source_name", "Official government vacancy portal"),
            "url": source_url,
            "confidence": "official",
            "last_seen_at": now_iso(),
        },
        "apply_url": apply_url,
        "apply_is_official": True,
        "flags": [],
        "eligibility_notes": "Citizenship restricted" if citizenship_required else None,
        "summary": clean(summary),
        "raw_description_url": source_document_url or apply_url,
        "government_fields": {
            "advert_reference": clean(advert_reference),
            "public_service_grade": clean(public_service_grade),
            "salary_scale": clean(salary_scale),
            "number_of_positions": number_of_positions,
            "citizenship_required": citizenship_required,
            "eligible_nationalities": eligible_nationalities or [],
            "application_method": clean(application_method),
            "application_form_url": clean(application_form_url),
            "internal_only": bool(internal_only),
            "county_or_region_requirement": clean(county_or_region_requirement),
            "source_document_url": clean(source_document_url),
        },
    }


def parse_date_dmy(value: str | None, *, end_of_day: bool = False) -> str | None:
    value = clean(value)
    if not value:
        return None
    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y"):
        try:
            parsed = datetime.strptime(value, fmt)
            return parsed.strftime("%Y-%m-%dT23:59:59Z" if end_of_day else "%Y-%m-%dT00:00:00Z")
        except ValueError:
            pass
    return normalise_datetime(value, end_of_day=end_of_day)
