"""Adzuna Search API collector.

IMPORTANT SCOPE NOTE: Adzuna's API covers 12 countries total, of which
**South Africa is the only African country covered**. Kenya, Nigeria, Ghana,
Uganda, Egypt, Rwanda, and everywhere else on the continent are NOT in
Adzuna's coverage. This collector is deliberately scoped to South Africa
(country code "za") - do not try to query Adzuna for other African country
codes, it will silently return empty or error, and treating that as "no jobs
in Kenya today" would be actively misleading rather than just incomplete.

Endpoint: https://api.adzuna.com/v1/api/jobs/{country}/search/{page}
Auth: app_id + app_key (free registration at https://developer.adzuna.com/)
Docs: https://developer.adzuna.com/docs/search

Requires ADZUNA_APP_ID and ADZUNA_APP_KEY environment variables / repo
secrets. Skips cleanly (returns 0) if either is unset, same pattern as the
ReliefWeb collector's appname requirement.

NOT execution-tested against the live API from this sandbox.
"""
from __future__ import annotations

import sys

from normalizers.temporal import normalise_datetime

from ._common import (
    extract_contract_type, extract_deadline, extract_education_requirement,
    extract_years_experience, html_to_text, infer_seniority, now_iso,
    classify_industry,
)

# Adzuna's own `contract_type` field (permanent/contract) and
# `contract_time` field (full_time/part_time) map onto our ContractType enum.
_ADZUNA_CONTRACT_MAP = {
    ("permanent", "full_time"): "permanent",
    ("permanent", "part_time"): "part_time",
    ("contract", "full_time"): "contract",
    ("contract", "part_time"): "contract",
}


def _map_contract(job: dict, title: str, description: str) -> str:
    ctype = job.get("contract_type")
    ctime = job.get("contract_time")
    mapped = _ADZUNA_CONTRACT_MAP.get((ctype, ctime))
    if mapped:
        return mapped
    # Fall back to text-based extraction if Adzuna didn't structure it.
    return extract_contract_type(title, description)


def collect_adzuna(builder, app_id: str, app_key: str, country: str = "za",
                    query: str | None = None, results_per_page: int = 50, max_pages: int = 3, session=None) -> int:
    """Fetches Adzuna listings for one country. `country` defaults to "za"
    (South Africa) - see module docstring for why that's the only African
    option. `query` is an optional `what=` search term; leave None to pull
    the general feed for that country.
    """
    import requests
    client = session or requests

    if country.lower() != "za":
        print(
            f"WARN adzuna: country='{country}' requested but Adzuna has no African "
            f"coverage outside South Africa ('za'). Refusing to silently return an "
            f"empty result that could be mistaken for 'no jobs found'.",
            file=sys.stderr,
        )
        return 0

    added = 0
    for page in range(1, max_pages + 1):
        url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"
        params = {
            "app_id": app_id,
            "app_key": app_key,
            "results_per_page": results_per_page,
            "content-type": "application/json",
        }
        if query:
            params["what"] = query

        try:
            resp = client.get(url, params=params, timeout=30)
            resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            print(f"WARN adzuna[{country} p{page}]: fetch failed - {exc}", file=sys.stderr)
            break

        payload = resp.json()
        results = payload.get("results", [])
        if not results:
            break  # ran out of pages

        for job in results:
            adzuna_id = job.get("id")
            title = job.get("title")
            if not adzuna_id or not title:
                continue

            description = job.get("description") or ""
            company = (job.get("company") or {}).get("display_name") or "Unknown employer"
            location_obj = job.get("location") or {}
            location_display = location_obj.get("display_name")
            area_parts = location_obj.get("area") or []

            # Adzuna's `area` is a list like ["South Africa", "Western Cape",
            # "Cape Town"] - most specific last. Country is always area[0]
            # for country-scoped searches; keep it simple and explicit.
            country_name = area_parts[0] if area_parts else "South Africa"

            salary_min = job.get("salary_min")
            salary_max = job.get("salary_max")
            # Adzuna's salary_is_predicted has been observed as both int (0/1)
            # and string ("0"/"1") depending on client. bool("0") is True in
            # Python since it's a non-empty string - explicitly compare
            # against the "falsy" values rather than trusting bool() here.
            raw_predicted = job.get("salary_is_predicted")
            salary_predicted = str(raw_predicted) not in ("0", "0.0", "False", "None", "")
            compensation = None
            if salary_min and salary_max and not salary_predicted:
                # Only include employer-disclosed salaries, not Adzuna's own
                # ML-predicted estimates (salary_is_predicted=1) - spec §14:
                # don't present an estimate as disclosed fact.
                compensation = {
                    "min": int(salary_min),
                    "max": int(salary_max),
                    "currency": "ZAR",
                    "period": "year",
                    "disclosed": True,
                }

            category = (job.get("category") or {}).get("label", "")
            categories = builder.map_specialisations([category], source_key="adzuna") if category else []

            years_min, years_max = extract_years_experience(description)
            education_level, education_fields = extract_education_requirement(description)
            deadline, deadline_confidence = extract_deadline(description)

            builder.add({
                "id": f"adzuna-{adzuna_id}",
                "title": title,
                "opportunity_type": "internship" if "intern" in title.lower() else "job",
                "organisation": {
                    "name": company,
                    "type": "unverified",  # Adzuna aggregates from many boards; can't verify org type
                    "verified": False,
                },
                "location": {
                    "raw": location_display,
                    "country": country_name,
                    "region": None,
                    "is_remote_from_kenya": False,  # SA-based roles, not Kenya-remote
                    "scope": "national",
                    "relocation_country": None,
                },
                "work_mode": "remote_global" if "remote" in (location_display or "").lower() else None,
                "seniority": infer_seniority(title),
                "categories": categories,
                "specialisations": categories,
                "industry": classify_industry(title, description),
                "skills_required": [],
                "skills_preferred": [],
                "posted_at": normalise_datetime(job.get("created")),
                "deadline": deadline,
                "deadline_confidence": deadline_confidence,
                "years_experience_min": years_min,
                "years_experience_max": years_max,
                "education_required": education_level,
                "education_field": education_fields,
                "contract_type": _map_contract(job, title, description),
                "source": {
                    "name": "Adzuna",
                    "url": "https://www.adzuna.co.za",
                    # Adzuna is an aggregator of other boards' postings, same
                    # trust tier as BrighterMonday/MyJobMag - never "official".
                    "confidence": builder.confidence_for_domain("adzuna.com"),
                    "last_seen_at": now_iso(),
                },
                "apply_url": job.get("redirect_url"),
                "apply_is_official": False,  # Adzuna redirect, not the employer's own page
                "flags": [],
                "eligibility_notes": None,
                "summary": html_to_text(description),
                "raw_description_url": job.get("redirect_url"),
                **({"compensation": compensation} if compensation else {}),
            })
            added += 1

        if len(results) < results_per_page:
            break  # last page

    return added


def collect_adzuna_portfolio(builder, app_id: str, app_key: str, searches: list[dict] | None = None, session=None) -> int:
    """Run the configured South Africa search portfolio.

    The general feed remains first for backward-compatible breadth, followed by
    targeted searches for investment, development, NGO and public-sector roles.
    Duplicate Adzuna IDs are resolved by the Phase 5 deduplication layer.
    """
    searches = searches or [{"country": "za", "query": None, "max_pages": 3, "results_per_page": 50}]
    total = 0
    for search in searches:
        total += collect_adzuna(
            builder,
            app_id=app_id,
            app_key=app_key,
            country=search.get("country", "za"),
            query=search.get("query"),
            results_per_page=int(search.get("results_per_page", 50)),
            max_pages=int(search.get("max_pages", 1)),
            session=session,
        )
    return total
