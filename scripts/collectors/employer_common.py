"""Shared helpers for Phase 11 official employer ATS collectors."""
from __future__ import annotations

import hashlib
from typing import Any

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
from .official_common import clean_text, is_official_opportunity_in_scope


def stable_employer_id(prefix: str, organisation_id: str, external_id: Any, title: str, url: str) -> str:
    seed = str(external_id or url or title)
    digest = hashlib.sha256(seed.encode('utf-8', errors='ignore')).hexdigest()[:18]
    return f"{prefix}-{organisation_id}-{digest}"


def employer_opportunity(
    builder,
    target: dict,
    *,
    prefix: str,
    external_id: Any,
    title: Any,
    apply_url: str,
    raw_location: Any = None,
    description: Any = None,
    posted_at: Any = None,
    deadline: Any = None,
    employment_type: Any = None,
    source_name: str,
    source_url: str,
    reference: str | None = None,
) -> dict | None:
    title = clean_text(title)
    if not title:
        return None
    description_text = clean_text(description) or ''
    raw_location = clean_text(raw_location)
    location = parse_location(raw_location)
    if not is_official_opportunity_in_scope(
        location, title, description_text,
        allow_non_african=bool(target.get('include_non_african_roles')),
    ):
        return None

    specialisations = builder.infer_specialisations(title, description_text, limit=3)
    years_min, years_max = extract_years_experience(description_text)
    education, fields = extract_education_requirement(description_text)
    normalised_deadline = normalise_datetime(deadline, end_of_day=True)
    deadline_confidence = 'explicit' if normalised_deadline else 'unknown'
    if not normalised_deadline:
        normalised_deadline, deadline_confidence = extract_deadline(description_text)

    return {
        'id': stable_employer_id(prefix, target['organisation_id'], external_id, title, apply_url),
        'title': title,
        'opportunity_type': 'internship' if 'intern' in title.casefold() else 'job',
        'organisation': {
            'name': target['name'],
            'type': target.get('type', 'private'),
            'verified': True,
        },
        'location': location,
        'work_mode': infer_work_mode(' '.join(filter(None, [raw_location, title, description_text[:500]]))),
        'seniority': infer_seniority(title),
        'categories': specialisations,
        'specialisations': specialisations,
        'source_context_specialisations': builder.map_specialisations(
            list(target.get('default_specialisations') or []), source_key=prefix, limit=3
        ),
        'industry': builder.industry_for_specialisations(specialisations) or classify_industry(title, description_text),
        'skills_required': [],
        'skills_preferred': [],
        'posted_at': normalise_datetime(posted_at),
        'deadline': normalised_deadline,
        'deadline_confidence': deadline_confidence,
        'years_experience_min': years_min,
        'years_experience_max': years_max,
        'education_required': education,
        'education_field': fields,
        'languages_required': extract_languages_required(description_text),
        'contract_type': extract_contract_type(title, clean_text(employment_type) or description_text),
        'source': {
            'name': source_name,
            'url': source_url,
            'confidence': 'official',
            'last_seen_at': now_iso(),
        },
        'apply_url': apply_url,
        'apply_is_official': True,
        'flags': [],
        'eligibility_notes': None,
        'summary': html_to_text(description_text),
        'raw_description_url': apply_url,
        'external_reference': clean_text(reference),
    }
