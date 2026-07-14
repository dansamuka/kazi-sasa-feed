"""PDF vacancy parsing for Tanzania public-service advertisements and DPSA circulars."""
from __future__ import annotations

import io
import re
import sys
from typing import Iterable

from pypdf import PdfReader

from .government_common import government_opportunity, parse_int


def pdf_text(content: bytes) -> str:
    reader = PdfReader(io.BytesIO(content))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def parse_tanzania_advert_text(builder, portal: dict, text: str, url: str, posted_at=None) -> int:
    cleaned = re.sub(r"\r", "", text or "")
    deadline = None
    match = re.search(r"Mwisho\s+wa\s+kutuma\s+maombi[^\n]{0,80}?tarehe\s+([^\n.]+)", cleaned, re.I)
    if match:
        deadline = match.group(1).strip()
        # Translate Swahili month names before the shared temporal parser.
        month_map = {
            "januari": "January", "februari": "February", "machi": "March",
            "aprili": "April", "mei": "May", "juni": "June",
            "julai": "July", "agosti": "August", "septemba": "September",
            "oktoba": "October", "novemba": "November", "desemba": "December",
        }
        for sw, en in month_map.items():
            deadline = re.sub(rf"\b{sw}\b", en, deadline, flags=re.I)
    citizenship = bool(re.search(r"waombaji\s+wote\s+lazima\s+wawe\s+raia", cleaned, re.I))
    # Tanzania PSRS adverts use numbered vacancy headings followed by
    # "- Nafasi N".  Requiring that suffix avoids treating numbered
    # subsections such as MAJUKUMU YA KAZI as separate vacancies.
    blocks = list(re.finditer(
        r"(?mi)^\s*(\d+(?:\.\d+)?)\s+(.+?)\s+-\s+Nafasi\s+(\d+)\s*$",
        cleaned,
    ))
    added = 0
    for index, match in enumerate(blocks):
        title = re.sub(r"\s+", " ", match.group(2)).strip(" -")
        if any(label in title for label in ("MAJUKUMU YA KAZI", "SIFA ZA MWOMBAJI", "NGAZI YA MSHAHARA", "MASHARTI YA JUMLA")):
            continue
        start = match.end(); end = blocks[index + 1].start() if index + 1 < len(blocks) else len(cleaned)
        body = cleaned[start:end]
        salary = None
        sm = re.search(r"NGAZI\s+YA\s+MSHAHARA\s*\n?\s*([^\n]+)", body, re.I)
        if sm: salary = sm.group(1).strip()
        ref = f"{portal.get('advert_reference_prefix','TZ')}-{match.group(1)}"
        opportunity = government_opportunity(
            builder, portal, title=title.title(), apply_url=portal.get("application_form_url") or url,
            raw_location=portal.get("default_location") or "Tanzania",
            summary=re.sub(r"\s+", " ", body).strip()[:1200], advert_reference=ref,
            posted_at=posted_at, deadline=deadline, salary_scale=salary,
            number_of_positions=parse_int(match.group(3)), citizenship_required=citizenship,
            eligible_nationalities=["TZ"] if citizenship else [],
            application_method="Tanzania Recruitment Portal", application_form_url=portal.get("application_form_url"),
            source_document_url=url, extra_text=body,
        )
        builder.add(opportunity); added += 1
    return added


def parse_dpsa_text(builder, portal: dict, text: str, url: str, posted_at=None) -> int:
    cleaned = re.sub(r"\r", "", text or "")
    posts = list(re.finditer(r"(?mi)^\s*POST\s+([0-9A-Z/.-]+)\s*:\s*([^\n]+)", cleaned))
    added = 0
    for index, match in enumerate(posts):
        start = match.end(); end = posts[index + 1].start() if index + 1 < len(posts) else len(cleaned)
        body = cleaned[start:end]
        title = re.sub(r"\s+", " ", match.group(2)).strip()
        ref = match.group(1).strip()
        salary = next((m.group(1).strip() for m in [re.search(r"(?mi)^\s*SALARY\s*:\s*([^\n]+)", body)] if m), None)
        centre = next((m.group(1).strip() for m in [re.search(r"(?mi)^\s*CENTRE\s*:\s*([^\n]+)", body)] if m), None)
        closing = next((m.group(1).strip() for m in [re.search(r"(?mi)^\s*CLOSING DATE\s*:\s*([^\n]+)", body)] if m), None)
        requirements = next((m.group(1).strip() for m in [re.search(r"(?mis)^\s*REQUIREMENTS\s*:\s*(.*?)(?=^\s*(?:DUTIES|ENQUIRIES|APPLICATIONS|NOTE)\s*:|\Z)", body)] if m), None)
        opportunity = government_opportunity(
            builder, portal, title=title, apply_url=url, raw_location=centre or "South Africa",
            summary=requirements or re.sub(r"\s+", " ", body).strip()[:1000], advert_reference=ref,
            posted_at=posted_at, deadline=closing, salary_scale=salary,
            citizenship_required=portal.get("citizenship_required", True), eligible_nationalities=["ZA"],
            application_method="Z83 / department instructions", application_form_url=portal.get("application_form_url"),
            source_document_url=url, extra_text=body,
        )
        builder.add(opportunity); added += 1
    return added


def collect_pdf_url(builder, portal: dict, url: str, *, posted_at=None, session=None) -> int:
    import requests
    client = session or requests
    try:
        response = client.get(url, headers={"Accept": "application/pdf"}, timeout=60)
        response.raise_for_status()
        content = getattr(response, "content", b"")
        if not content and getattr(response, "text", None):
            content = response.text.encode("latin1", errors="ignore")
        text = pdf_text(content)
    except Exception as exc:  # noqa: BLE001
        print(f"WARN government_pdf[{portal.get('id')}]: failed {url} - {exc}", file=sys.stderr)
        return 0
    parser = portal.get("pdf_parser")
    if parser == "tanzania_psrs":
        return parse_tanzania_advert_text(builder, portal, text, url, posted_at=posted_at)
    if parser == "south_africa_dpsa":
        return parse_dpsa_text(builder, portal, text, url, posted_at=posted_at)
    print(f"WARN government_pdf[{portal.get('id')}]: unsupported parser {parser!r}", file=sys.stderr)
    return 0


def collect_government_pdf(builder, portals: Iterable[dict], session=None) -> int:
    return sum(collect_pdf_url(builder, portal, portal["listing_url"], session=session) for portal in portals)
