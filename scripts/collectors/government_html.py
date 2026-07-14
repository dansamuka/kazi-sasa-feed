"""Phase 9 collectors for official government HTML vacancy portals."""
from __future__ import annotations

import re
import sys
from typing import Iterable
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from .government_common import government_opportunity, parse_date_dmy, parse_int


def _valid_http_url(base_url: str, value: str | None) -> str | None:
    """Return a safe absolute HTTP(S) URL or ``None``.

    Kenya PSC uses ASP.NET ``javascript:__doPostBack(...)`` links in its
    vacancy table. Those are browser actions, not application URLs, and must
    never enter the public feed. Relative HTTP paths remain supported.
    """
    if not value:
        return None
    candidate = str(value).strip()
    lowered = candidate.casefold()
    if lowered.startswith(("javascript:", "data:", "mailto:", "tel:", "#")):
        return None
    absolute = urljoin(base_url, candidate)
    parsed = urlparse(absolute)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return absolute


def _row_application_url(portal: dict, row) -> str:
    """Choose the best real URL exposed by a government vacancy row.

    Some portals expose several controls. Prefer a genuine vacancy/detail
    link, then a configured application form, and finally the official listing
    page. Falling back to the listing page is preferable to publishing an
    unusable JavaScript postback pseudo-URL.
    """
    base = portal["listing_url"]
    for link in row.find_all("a"):
        for attribute in ("href", "data-href", "data-url"):
            resolved = _valid_http_url(base, link.get(attribute))
            if resolved:
                return resolved
    return (
        _valid_http_url(base, portal.get("application_form_url"))
        or _valid_http_url(base, base)
        or base
    )


def _header_key(value: str) -> str:
    value = re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()
    aliases = {
        "advert number": "advert_reference", "advert no": "advert_reference",
        "position": "title", "job title": "title", "post": "title",
        "job scale": "grade", "grade": "grade",
        "ministry": "ministry", "department": "ministry",
        "number of vacancies": "positions", "vacancies": "positions",
        "years of experience required": "experience", "experience": "experience",
        "advert date": "posted", "posting date": "posted",
        "advert close date": "deadline", "closing date": "deadline",
    }
    return aliases.get(value, value.replace(" ", "_"))


def parse_government_table(builder, portal: dict, html: str) -> int:
    soup = BeautifulSoup(html or "", "html.parser")
    added = 0
    seen: set[str] = set()
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue
        header_cells = rows[0].find_all(["th", "td"])
        headers = [_header_key(cell.get_text(" ", strip=True)) for cell in header_cells]
        if "title" not in headers:
            continue
        for row in rows[1:]:
            cells = row.find_all(["td", "th"])
            values = [cell.get_text(" ", strip=True) for cell in cells]
            if len(values) < 2:
                continue
            record = {headers[i]: values[i] for i in range(min(len(headers), len(values)))}
            title = record.get("title")
            if not title:
                continue
            apply_url = _row_application_url(portal, row)
            summary = " | ".join(filter(None, [record.get("ministry"), record.get("experience") and f"Experience: {record['experience']} years"]))
            opportunity = government_opportunity(
                builder, portal, title=title, apply_url=apply_url,
                raw_location=portal.get("default_location") or portal.get("country_name"),
                summary=summary or None,
                advert_reference=record.get("advert_reference"),
                posted_at=parse_date_dmy(record.get("posted")),
                deadline=parse_date_dmy(record.get("deadline"), end_of_day=True),
                public_service_grade=record.get("grade"),
                number_of_positions=parse_int(record.get("positions")),
                citizenship_required=portal.get("citizenship_required", True),
                eligible_nationalities=portal.get("eligible_nationalities", []),
                application_method=portal.get("application_method", "official online portal"),
                application_form_url=portal.get("application_form_url"),
                extra_text=summary,
            )
            if opportunity["id"] not in seen:
                builder.add(opportunity); seen.add(opportunity["id"]); added += 1
    return added


def collect_government_html_target(builder, portal: dict, session=None) -> int:
    import requests
    client = session or requests
    try:
        response = client.get(portal["listing_url"], headers={"Accept": "text/html"}, timeout=40)
        response.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        print(f"WARN government_html[{portal.get('id')}]: fetch failed - {exc}", file=sys.stderr)
        return 0
    return parse_government_table(builder, portal, response.text)


def collect_government_html(builder, portals: Iterable[dict], session=None) -> int:
    return sum(collect_government_html_target(builder, portal, session=session) for portal in portals)
