"""Index/circular collectors for Tanzania PSRS and South Africa DPSA."""
from __future__ import annotations

import re
import sys
from typing import Iterable
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .government_pdf import collect_pdf_url


def _date_from_text(text: str) -> str | None:
    match = re.search(r"(\d{1,2}[-/]\d{1,2}[-/]\d{4}|\d{1,2}\s+[A-Za-z]+\s+\d{4})", text or "")
    return match.group(1) if match else None


def collect_government_circular_target(builder, portal: dict, session=None) -> int:
    import requests
    client = session or requests
    try:
        response = client.get(portal["listing_url"], headers={"Accept": "text/html"}, timeout=45)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
    except Exception as exc:  # noqa: BLE001
        print(f"WARN government_circular[{portal.get('id')}]: index fetch failed - {exc}", file=sys.stderr)
        return 0

    parser = portal.get("pdf_parser")
    max_documents = int(portal.get("max_documents", 8))
    candidates: list[tuple[str, str, str | None]] = []
    if parser == "tanzania_psrs":
        for anchor in soup.find_all("a", href=True):
            href = urljoin(portal["listing_url"], anchor.get("href"))
            title = anchor.get_text(" ", strip=True)
            if not href.lower().endswith(".pdf"):
                continue
            if not re.search(r"nafasi\s+za\s+kazi|tangazo\s+la\s+kazi", title, re.I):
                continue
            candidates.append((title, href, _date_from_text(title)))
    elif parser == "south_africa_dpsa":
        # The index links to the latest circular page; that page links to a full
        # document and department PDFs. Follow only the newest circular.
        circular_links = []
        for anchor in soup.find_all("a", href=True):
            title = anchor.get_text(" ", strip=True)
            href = urljoin(portal["listing_url"], anchor.get("href"))
            match = re.search(r"Circular\s+(\d+)\s+of\s+(\d{4})", title, re.I)
            if match:
                circular_links.append((int(match.group(2)), int(match.group(1)), href))
        if circular_links:
            _, _, latest_url = sorted(circular_links, reverse=True)[0]
            try:
                detail = client.get(latest_url, headers={"Accept": "text/html"}, timeout=45)
                detail.raise_for_status(); detail_soup = BeautifulSoup(detail.text, "html.parser")
                page_text = detail_soup.get_text(" ", strip=True)
                posted = _date_from_text(page_text)
                for anchor in detail_soup.find_all("a", href=True):
                    href = urljoin(latest_url, anchor.get("href"))
                    if href.lower().split("?", 1)[0].endswith(".pdf"):
                        candidates.append((anchor.get_text(" ", strip=True), href, posted))
            except Exception as exc:  # noqa: BLE001
                print(f"WARN government_circular[{portal.get('id')}]: circular page failed - {exc}", file=sys.stderr)
    else:
        return 0

    seen: set[str] = set(); added = 0
    for _title, url, posted in candidates:
        canonical = url.split("#", 1)[0]
        if canonical in seen: continue
        seen.add(canonical)
        added += collect_pdf_url(builder, portal, canonical, posted_at=posted, session=client)
        if len(seen) >= max_documents: break
    return added


def collect_government_circular(builder, portals: Iterable[dict], session=None) -> int:
    return sum(collect_government_circular_target(builder, portal, session=session) for portal in portals)
