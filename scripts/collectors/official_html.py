"""Registry-driven collector for official DFI and multilateral careers pages."""
from __future__ import annotations

import sys
from typing import Iterable

from .official_common import (
    extract_candidate_links,
    is_expired,
    jsonld_job_postings,
    opportunity_from_jobposting,
    opportunity_from_page,
)


def collect_official_html_target(builder, target: dict, session=None, source_name: str = "DFI and multilateral official career page") -> int:
    import requests

    client = session or requests
    listing_url = target["listing_url"]
    try:
        response = client.get(listing_url, headers={"Accept": "text/html,application/xhtml+xml"}, timeout=30)
        response.raise_for_status()
        html = response.text
    except Exception as exc:  # noqa: BLE001
        print(f"WARN official_html[{target.get('organisation_id')}]: listing fetch failed - {exc}", file=sys.stderr)
        return 0

    added = 0
    seen_ids: set[str] = set()
    for job in jsonld_job_postings(html):
        opportunity = opportunity_from_jobposting(
            builder, target, job, source_name=source_name, source_url=listing_url, prefix="official"
        )
        if opportunity and opportunity["id"] not in seen_ids and not is_expired(opportunity):
            builder.add(opportunity)
            seen_ids.add(opportunity["id"])
            added += 1

    patterns = target.get("link_patterns") or [r"/career", r"/vacanc", r"/job"]
    exclude = target.get("exclude_patterns") or [r"/careers/?$", r"/vacancies/?$", r"/jobs/?$"]
    candidates = extract_candidate_links(html, listing_url, patterns, exclude)
    max_jobs = int(target.get("max_jobs", 60))
    detail_fetch = bool(target.get("detail_fetch", True))
    for title, url, context in candidates[:max_jobs]:
        detail_html = ""
        if detail_fetch and not url.lower().split("?", 1)[0].endswith((".pdf", ".doc", ".docx")):
            try:
                detail = client.get(url, headers={"Accept": "text/html,application/xhtml+xml"}, timeout=30)
                detail.raise_for_status()
                detail_html = detail.text
            except Exception as exc:  # noqa: BLE001
                print(f"WARN official_html[{target.get('organisation_id')}]: detail fetch failed for {url} - {exc}", file=sys.stderr)
        opportunity = opportunity_from_page(
            builder,
            target,
            title=title,
            url=url,
            page_html=detail_html,
            context_text=context,
            source_name=source_name,
            prefix="official",
        )
        if opportunity and opportunity["id"] not in seen_ids and not is_expired(opportunity):
            builder.add(opportunity)
            seen_ids.add(opportunity["id"])
            added += 1
    return added


def collect_official_html(builder, targets: Iterable[dict], session=None) -> int:
    return sum(
        collect_official_html_target(
            builder, target, session=session,
            source_name=target.get("source_name", "DFI and multilateral official career page"),
        )
        for target in targets
    )
