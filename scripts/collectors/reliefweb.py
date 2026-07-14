"""Africa-wide ReliefWeb API v2 jobs collector.

Requires a pre-approved ReliefWeb ``appname``. Phase 5 queries all African
countries in bounded batches and pages through results, rather than limiting
the feed to Kenya. Complex filters are kept below problematic URL lengths by
splitting ISO3 codes into small deterministic batches.
"""
from __future__ import annotations

import re
import sys
from collections.abc import Iterable

from normalizers.text import as_text
from ._common import (
    classify_industry,
    extract_contract_type,
    extract_education_requirement,
    extract_years_experience,
    html_to_text,
    infer_seniority,
    now_iso,
)

_URL_RE = re.compile(r"https?://[^\s<>\"']+", re.I)


def _chunks(values: list[str], size: int) -> list[list[str]]:
    return [values[index:index + size] for index in range(0, len(values), size)]


def _params(appname: str, countries: list[str], limit: int, offset: int) -> list[tuple[str, object]]:
    params: list[tuple[str, object]] = [
        ("appname", appname),
        ("limit", limit),
        ("offset", offset),
        ("sort[]", "date.created:desc"),
        ("filter[operator]", "AND"),
        ("filter[conditions][0][field]", "country.iso3"),
        ("filter[conditions][1][field]", "status"),
        ("filter[conditions][1][value][]", "published"),
    ]
    params.extend(("filter[conditions][0][value][]", code) for code in countries)
    for field in (
        "title", "body", "date.created", "date.closing", "country.name", "country.iso3",
        "country.primary", "city.name", "career_categories.name", "theme.name", "type.name",
        "source.name", "source.type.name", "how_to_apply",
    ):
        params.append(("fields[include][]", field))
    return params


def _external_apply_url(how_to_apply, body: str) -> str | None:
    text = "\n".join(part for part in (as_text(how_to_apply), body) if part)
    for raw in _URL_RE.findall(text):
        url = raw.rstrip(".,);]")
        if "reliefweb.int" not in url.casefold():
            return url
    return None


def _iter_items(client, appname: str, countries: list[str], limit: int, max_pages: int):
    url = "https://api.reliefweb.int/v2/jobs"
    for batch in _chunks(countries, 9):
        for page in range(max_pages):
            offset = page * limit
            try:
                response = client.get(url, params=_params(appname, batch, limit, offset), timeout=30)
                response.raise_for_status()
                payload = response.json()
            except Exception as exc:  # noqa: BLE001
                print(f"WARN reliefweb[{','.join(batch)} offset={offset}]: fetch failed - {exc}", file=sys.stderr)
                break
            rows = payload.get("data", []) if isinstance(payload, dict) else []
            for item in rows:
                if isinstance(item, dict):
                    yield item
            count = payload.get("count", len(rows)) if isinstance(payload, dict) else len(rows)
            total = payload.get("totalCount") if isinstance(payload, dict) else None
            if not rows or count < limit or (isinstance(total, int) and offset + count >= total):
                break


def collect_reliefweb(
    builder,
    appname: str,
    country_iso3: str | Iterable[str] | None = "KEN",
    limit: int = 200,
    max_pages: int = 2,
    session=None,
) -> int:
    """Collect published ReliefWeb jobs for one or many ISO3 country codes."""
    import requests

    client = session or requests
    if country_iso3 is None:
        countries = ["KEN"]
    elif isinstance(country_iso3, str):
        countries = [country_iso3.upper()]
    else:
        countries = sorted({str(code).upper() for code in country_iso3 if code})
    if not countries:
        return 0

    added = 0
    seen_ids: set[str] = set()
    for item in _iter_items(client, appname, countries, limit, max_pages):
        fields = item.get("fields", {})
        rw_id = item.get("id")
        if rw_id is None or not fields.get("title") or str(rw_id) in seen_ids:
            continue
        seen_ids.add(str(rw_id))
        detail_url = f"https://reliefweb.int/node/{rw_id}"

        rw_type_names = {
            str(value.get("name", "")).casefold()
            for value in fields.get("type", []) if isinstance(value, dict)
        }
        opportunity_type = "internship" if "internship" in rw_type_names else "job"
        source_orgs = fields.get("source", []) if isinstance(fields.get("source"), list) else []
        org_name = source_orgs[0].get("name", "ReliefWeb-listed organisation") if source_orgs else "ReliefWeb-listed organisation"
        org_type_names = {
            str(org_type.get("name", "")).casefold()
            for source in source_orgs if isinstance(source, dict)
            for org_type in (source.get("type") or []) if isinstance(org_type, dict)
        }
        if any("multilateral" in name or "united nations" in name for name in org_type_names):
            org_type = "multilateral"
        elif any("non-governmental" in name or "ngo" in name for name in org_type_names):
            org_type = "ngo"
        else:
            org_type = "unverified"

        countries_rows = fields.get("country", []) if isinstance(fields.get("country"), list) else []
        primary = next((row for row in countries_rows if isinstance(row, dict) and row.get("primary")), None)
        country = primary or next((row for row in countries_rows if isinstance(row, dict)), {})
        country_name = country.get("name")
        country_iso = country.get("iso3")
        cities = fields.get("city", []) if isinstance(fields.get("city"), list) else []
        city_name = next((row.get("name") for row in cities if isinstance(row, dict) and row.get("name")), None)
        location_raw = ", ".join(part for part in (city_name, country_name) if part) or None

        raw_categories = [row.get("name", "") for row in fields.get("career_categories", []) if isinstance(row, dict) and row.get("name")]
        categories = builder.map_specialisations(raw_categories, source_key="reliefweb")
        body = fields.get("body") or ""
        summary_text = html_to_text(body)
        summary = (summary_text[:600] + "...") if len(summary_text) > 600 else (summary_text or None)
        dates = fields.get("date") or {}
        deadline = dates.get("closing")
        posted_at = dates.get("created")
        years_min, years_max = extract_years_experience(body)
        education_level, education_fields = extract_education_requirement(body)
        direct_url = _external_apply_url(fields.get("how_to_apply"), body)
        apply_url = direct_url or detail_url

        builder.add({
            "id": f"reliefweb-{rw_id}",
            "title": fields["title"],
            "opportunity_type": opportunity_type,
            "organisation": {"name": org_name, "type": org_type, "verified": True},
            "location": {
                "raw": location_raw,
                "country": country_name,
                "country_iso3": country_iso,
                "region": None,
                "is_remote_from_kenya": False,
                "scope": "national" if country_name else None,
                "relocation_country": None,
            },
            "work_mode": None,
            "seniority": infer_seniority(fields["title"]),
            "categories": categories,
            "specialisations": categories,
            "industry": builder.industry_for_specialisations(categories) or classify_industry(fields["title"], body) or "development_humanitarian",
            "skills_required": [],
            "skills_preferred": [],
            "posted_at": posted_at,
            "deadline": deadline,
            "deadline_confidence": "explicit" if deadline else "unknown",
            "years_experience_min": years_min,
            "years_experience_max": years_max,
            "education_required": education_level,
            "education_field": education_fields,
            "contract_type": extract_contract_type(fields["title"], body),
            "source": {
                "name": "ReliefWeb",
                "url": "https://reliefweb.int",
                "confidence": builder.confidence_for_domain("reliefweb.int"),
                "last_seen_at": now_iso(),
            },
            "apply_url": apply_url,
            "apply_is_official": bool(direct_url),
            "flags": [],
            "eligibility_notes": None,
            "summary": summary,
            "raw_description_url": detail_url,
        })
        added += 1
    return added
