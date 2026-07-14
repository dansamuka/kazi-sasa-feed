"""Shared extraction helpers for official DFI and multilateral career sites."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from html import unescape
from typing import Any, Iterable
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

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


def clean_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple, set)):
        value = " ".join(str(item) for item in value if item not in (None, ""))
    elif isinstance(value, dict):
        value = " ".join(str(item) for item in value.values() if item not in (None, ""))
    raw = unescape(str(value))
    text = BeautifulSoup(raw, "html.parser").get_text(" ", strip=True) if "<" in raw and ">" in raw else raw
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


_INVALID_JOB_TITLE_PATTERNS = [
    r"^javascript is disabled$", r"^enable javascript", r"^access denied$",
    r"^careers?$", r"^jobs?$", r"^vacanc(?:y|ies)$", r"^current vacancies$",
    r"^career opportunities$", r"^job opportunities$", r"^work(?:ing)? with us$",
    r"^join us$", r"^recruitment$", r"^opportunities$", r"^equal employment opportunity",
    r"^military veterans$", r"^privacy policy$", r"^terms (?:of use|and conditions)$",
    r"^about us$", r"^our people$", r"^talent community$", r"^register your interest$",
]


def is_valid_job_title(value: Any, organisation_name: str | None = None) -> bool:
    title = clean_text(value)
    if not title or len(title) < 4 or len(title) > 220:
        return False
    normalised = re.sub(r"[^a-z0-9]+", " ", title.casefold()).strip()
    if any(re.search(pattern, normalised, re.I) for pattern in _INVALID_JOB_TITLE_PATTERNS):
        return False
    if organisation_name:
        org = re.sub(r"[^a-z0-9]+", " ", organisation_name.casefold()).strip()
        if normalised == org:
            return False
    if len(normalised.split()) == 1 and normalised in {"career", "careers", "jobs", "vacancies", "recruitment"}:
        return False
    return True


def choose_job_title(listing_title: Any, page_title: Any, organisation_name: str | None = None) -> str | None:
    listing = clean_text(listing_title)
    page = clean_text(page_title)
    listing_valid = is_valid_job_title(listing, organisation_name)
    page_valid = is_valid_job_title(page, organisation_name)
    if listing_valid and not page_valid:
        return listing
    if page_valid and not listing_valid:
        return page
    if listing_valid and page_valid:
        # Prefer the specific listing title unless the detail title is clearly
        # a richer version of the same vacancy.
        lkey = re.sub(r"[^a-z0-9]+", " ", listing.casefold()).strip()
        pkey = re.sub(r"[^a-z0-9]+", " ", page.casefold()).strip()
        if lkey in pkey and len(page) <= len(listing) + 90:
            return page
        return listing
    return None


def has_vacancy_evidence(page_html: str, url: str, title: str, context_text: str = "") -> bool:
    """Require vacancy-specific evidence before publishing generic HTML links."""
    if jsonld_job_postings(page_html):
        return True
    soup = BeautifulSoup(page_html or "", "html.parser")
    text = clean_text(soup.get_text(" ", strip=True)) or clean_text(context_text) or ""
    url_l = (url or "").casefold()
    strong_url = bool(re.search(r"/(?:job|jobs|vacanc(?:y|ies)|position|requisition|opening)s?[/_-](?:[a-z0-9-]*\d|[a-z0-9-]{8,})", url_l))
    requisition = bool(re.search(r"\b(?:requisition|vacancy|advert|reference|job)\s*(?:id|no\.?|number|ref(?:erence)?)\s*[:#-]?\s*[a-z0-9/-]{3,}\b", text, re.I))
    dates = bool(re.search(r"\b(?:closing date|application deadline|valid through|posted on|date posted)\b", text, re.I))
    job_sections = sum(bool(re.search(pattern, text, re.I)) for pattern in (
        r"\bresponsibilit(?:y|ies)\b", r"\brequirements?\b", r"\bqualifications?\b",
        r"\bduties\b", r"\bhow to apply\b", r"\bjob description\b",
    ))
    specific_title = is_valid_job_title(title) and len(title.split()) >= 2
    return bool((strong_url and specific_title) or requisition or (specific_title and dates and job_sections >= 1) or (specific_title and job_sections >= 2))


def iter_job_postings(payload: Any) -> Iterable[dict[str, Any]]:
    """Yield schema.org JobPosting objects from nested JSON-LD payloads."""
    if isinstance(payload, list):
        for item in payload:
            yield from iter_job_postings(item)
        return
    if not isinstance(payload, dict):
        return
    type_value = payload.get("@type")
    types = type_value if isinstance(type_value, list) else [type_value]
    if any(str(value).casefold() == "jobposting" for value in types if value):
        yield payload
    for key in ("@graph", "itemListElement", "mainEntity", "hasPart"):
        if key in payload:
            yield from iter_job_postings(payload[key])


def jsonld_job_postings(html: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html or "", "html.parser")
    jobs: list[dict[str, Any]] = []
    for script in soup.find_all("script", attrs={"type": re.compile(r"application/ld\+json", re.I)}):
        raw = script.string or script.get_text()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError):
            continue
        jobs.extend(iter_job_postings(payload))
    return jobs


def jsonld_location(job: dict[str, Any]) -> str | None:
    locations = job.get("jobLocation") or job.get("applicantLocationRequirements")
    if not isinstance(locations, list):
        locations = [locations] if locations else []
    values: list[str] = []
    for location in locations:
        if not isinstance(location, dict):
            text = clean_text(location)
            if text:
                values.append(text)
            continue
        address = location.get("address") if isinstance(location.get("address"), dict) else location
        for key in ("addressLocality", "addressRegion", "addressCountry", "name"):
            value = address.get(key) if isinstance(address, dict) else None
            if isinstance(value, dict):
                value = value.get("name")
            text = clean_text(value)
            if text and text not in values:
                values.append(text)
    if not values and str(job.get("jobLocationType", "")).casefold() == "telecommute":
        return "Remote - Global"
    return ", ".join(values) or None


def stable_official_id(prefix: str, organisation_id: str, url: str | None, title: str) -> str:
    raw = url or title
    digest = hashlib.sha256(raw.encode("utf-8", errors="ignore")).hexdigest()[:16]
    return f"{prefix}-{organisation_id}-{digest}"




_LOCATION_LABEL_PATTERN = re.compile(
    r"(?:^|\n|[;|])\s*(?:job\s+location|work\s+location|posting\s+location|location(?:s)?|"
    r"duty\s+station|place\s+of\s+assignment|country|city|"
    r"lieu\s+d['’]affectation|lieu\s+de\s+travail|localisation|"
    r"localiza(?:ç|c)ão|local\s+de\s+trabalho|مكان\s+العمل|موقع\s+العمل|"
    r"mahali\s+pa\s+kazi)\s*[:\-–—]\s*([^\n;|]{2,140})",
    re.I,
)

_LOCATION_ATTR_RE = re.compile(r"(?:^|[-_])(job[-_ ]?)?location(?:$|[-_])", re.I)


def _useful_location_text(value: str | None) -> bool:
    if not value:
        return False
    parsed = parse_location(value)
    return bool(
        parsed.get("country_code")
        or parsed.get("region")
        or parsed.get("is_remote_from_kenya")
        or parsed.get("scope")
    )


def extract_page_location(page_html: str, *, context_text: str = "", title: str = "") -> str | None:
    """Extract location only from location-labelled or strongly structured evidence.

    Generic institutional pages often mention many countries in programme text.
    Scanning the entire description would therefore invent duty stations. This
    helper only accepts schema-like attributes, label/value structures, explicit
    multilingual location labels, listing-card context, or a title that itself
    contains a canonical place.
    """
    soup = BeautifulSoup(page_html or "", "html.parser")
    candidates: list[str] = []

    # Structured HTML and PageUp-style location elements.
    for tag in soup.find_all(True):
        attrs = " ".join(
            str(tag.get(key) or "") for key in ("id", "class", "itemprop", "data-location", "data-job-location")
        )
        if _LOCATION_ATTR_RE.search(attrs):
            text = clean_text(tag.get("data-location") or tag.get("data-job-location") or tag.get_text(" ", strip=True))
            if text and len(text) <= 180:
                candidates.append(text)

    # Definition lists and tabular label/value pairs.
    label_re = re.compile(
        r"^(?:job\s+location|work\s+location|posting\s+location|location(?:s)?|duty\s+station|"
        r"place\s+of\s+assignment|country|city|lieu\s+d['’]affectation|localisation|"
        r"localiza(?:ç|c)ão|مكان\s+العمل|موقع\s+العمل|mahali\s+pa\s+kazi)\s*:?$",
        re.I,
    )
    for label in soup.find_all(["dt", "th", "label", "strong", "b", "span", "div"]):
        label_text = clean_text(label.get_text(" ", strip=True))
        if not label_text or not label_re.match(label_text):
            continue
        sibling = label.find_next_sibling(["dd", "td", "span", "div", "p", "li"])
        if sibling:
            text = clean_text(sibling.get_text(" ", strip=True))
            if text and len(text) <= 180:
                candidates.append(text)

    # Preserve line boundaries so explicit labels are not lost during cleanup.
    page_lines = soup.get_text("\n", strip=True)
    for match in _LOCATION_LABEL_PATTERN.finditer(page_lines):
        candidates.append(match.group(1).strip())

    # Listing-card context is usually already scoped to one vacancy.
    context = clean_text(context_text)
    if context:
        for match in _LOCATION_LABEL_PATTERN.finditer(context.replace(" | ", "\n")):
            candidates.append(match.group(1).strip())
        candidates.append(context)

    # Some official sites encode the duty station in the vacancy title.
    if title:
        candidates.append(title)

    seen: set[str] = set()
    for candidate in candidates:
        candidate = clean_text(candidate)
        key = (candidate or "").casefold()
        if not candidate or key in seen:
            continue
        seen.add(key)
        if _useful_location_text(candidate):
            return candidate
    return None



_AFRICA_ROLE_SIGNAL = re.compile(
    r"\b(?:africa|african|sub[- ]saharan|east africa|west africa|central africa|"
    r"southern africa|north africa|afrique|africa ocidental|africa oriental)\b",
    re.I,
)


def is_official_opportunity_in_scope(
    location: dict, title: str = "", description: str = "", *, allow_non_african: bool = False
) -> bool:
    """Keep African, location-neutral, or explicitly Africa-focused official roles.

    Verified official boards often publish every worldwide vacancy.  A known
    non-African duty station is excluded unless the title/lead description
    explicitly identifies an Africa remit.  Missing-location official records
    remain eligible for the separate ``official_location_pending`` quality gate.
    """
    if allow_non_african:
        return True
    if location.get("is_african") or location.get("is_remote_from_kenya"):
        return True
    if not location.get("country"):
        return True
    evidence = " ".join(filter(None, [title, (description or "")[:350]]))
    return bool(_AFRICA_ROLE_SIGNAL.search(evidence))

def opportunity_from_jobposting(builder, target: dict, job: dict, *, source_name: str, source_url: str, prefix: str) -> dict | None:
    title = clean_text(job.get("title") or job.get("name") or job.get("headline"))
    if not title:
        return None
    description_raw = job.get("description") or job.get("responsibilities") or ""
    full_text = clean_text(description_raw) or ""
    raw_location = jsonld_location(job)
    location = parse_location(raw_location)
    if not is_official_opportunity_in_scope(
        location, title, full_text, allow_non_african=bool(target.get("include_non_african_roles"))
    ):
        return None
    job_url = clean_text(job.get("url") or job.get("sameAs")) or source_url
    apply_url = clean_text(job.get("applicationContact")) or job_url
    if isinstance(job.get("applicationContact"), dict):
        apply_url = clean_text(job["applicationContact"].get("url")) or job_url

    categories = builder.infer_specialisations(title, full_text, limit=3)
    years_min, years_max = extract_years_experience(full_text)
    education, fields = extract_education_requirement(full_text)
    deadline = normalise_datetime(job.get("validThrough"), end_of_day=True)
    deadline_confidence = "explicit" if deadline else "unknown"
    if not deadline:
        deadline, deadline_confidence = extract_deadline(full_text)

    return {
        "id": stable_official_id(prefix, target["organisation_id"], job_url, title),
        "title": title,
        "opportunity_type": "internship" if "intern" in title.casefold() else "job",
        "organisation": {"name": target["name"], "type": target.get("type", "multilateral"), "verified": True},
        "location": location,
        "work_mode": infer_work_mode(" ".join(filter(None, [raw_location, clean_text(job.get("jobLocationType")), title]))),
        "seniority": infer_seniority(title),
        "categories": categories,
        "specialisations": categories,
        "source_context_specialisations": builder.map_specialisations(list(target.get("default_specialisations") or []), source_key="official_html", limit=3),
        "industry": builder.industry_for_specialisations(categories) or classify_industry(title, full_text),
        "skills_required": [],
        "skills_preferred": [],
        "posted_at": normalise_datetime(job.get("datePosted")),
        "deadline": deadline,
        "deadline_confidence": deadline_confidence,
        "years_experience_min": years_min,
        "years_experience_max": years_max,
        "education_required": education,
        "education_field": fields,
        "languages_required": extract_languages_required(full_text),
        "contract_type": extract_contract_type(title, clean_text(job.get("employmentType")) or full_text),
        "source": {"name": source_name, "url": source_url, "confidence": "official", "last_seen_at": now_iso()},
        "apply_url": apply_url,
        "apply_is_official": True,
        "flags": [],
        "eligibility_notes": None,
        "summary": html_to_text(str(description_raw)),
        "raw_description_url": job_url,
    }


def opportunity_from_page(builder, target: dict, *, title: str, url: str, page_html: str, context_text: str = "", source_name: str, prefix: str) -> dict | None:
    json_jobs = jsonld_job_postings(page_html)
    if json_jobs:
        candidate = opportunity_from_jobposting(
            builder, target, json_jobs[0], source_name=source_name, source_url=target["listing_url"], prefix=prefix
        )
        if candidate:
            candidate["apply_url"] = candidate.get("apply_url") or url
            candidate["raw_description_url"] = url
            return candidate

    soup = BeautifulSoup(page_html or "", "html.parser")
    page_heading = soup.find("h1") or soup.find("title")
    page_title = clean_text(page_heading.get_text(" ", strip=True) if page_heading else None)
    title = choose_job_title(title, page_title, target.get("name"))
    if not title:
        return None
    if not has_vacancy_evidence(page_html, url, title, context_text):
        return None
    full_text = clean_text(soup.get_text(" ", strip=True)) or clean_text(context_text) or ""
    context = clean_text(context_text) or ""
    raw_location = extract_page_location(page_html, context_text=context, title=title)
    location = parse_location(raw_location)
    if not is_official_opportunity_in_scope(
        location, title, full_text, allow_non_african=bool(target.get("include_non_african_roles"))
    ):
        return None
    categories = builder.infer_specialisations(title, full_text, limit=3)
    years_min, years_max = extract_years_experience(full_text)
    education, fields = extract_education_requirement(full_text)
    deadline, deadline_confidence = extract_deadline(full_text)
    posted_at = None
    time_tag = soup.find("time")
    if time_tag:
        posted_at = normalise_datetime(time_tag.get("datetime") or time_tag.get_text(" ", strip=True))

    return {
        "id": stable_official_id(prefix, target["organisation_id"], url, title),
        "title": title,
        "opportunity_type": "internship" if "intern" in title.casefold() else "job",
        "organisation": {"name": target["name"], "type": target.get("type", "multilateral"), "verified": True},
        "location": location,
        "work_mode": infer_work_mode(" ".join(filter(None, [raw_location, title, full_text[:500]]))),
        "seniority": infer_seniority(title),
        "categories": categories,
        "specialisations": categories,
        "source_context_specialisations": builder.map_specialisations(list(target.get("default_specialisations") or []), source_key="official_html", limit=3),
        "industry": builder.industry_for_specialisations(categories) or classify_industry(title, full_text),
        "skills_required": [],
        "skills_preferred": [],
        "posted_at": posted_at,
        "deadline": deadline,
        "deadline_confidence": deadline_confidence,
        "years_experience_min": years_min,
        "years_experience_max": years_max,
        "education_required": education,
        "education_field": fields,
        "languages_required": extract_languages_required(full_text),
        "contract_type": extract_contract_type(title, full_text),
        "source": {"name": source_name, "url": target["listing_url"], "confidence": "official", "last_seen_at": now_iso()},
        "apply_url": url,
        "apply_is_official": True,
        "flags": [],
        "eligibility_notes": None,
        "summary": (full_text[:300] + "...") if len(full_text) > 300 else full_text or None,
        "raw_description_url": url,
    }


def extract_candidate_links(html: str, base_url: str, patterns: list[str], exclude_patterns: list[str] | None = None) -> list[tuple[str, str, str]]:
    soup = BeautifulSoup(html or "", "html.parser")
    compiled = [re.compile(pattern, re.I) for pattern in patterns]
    excluded = [re.compile(pattern, re.I) for pattern in (exclude_patterns or [])]
    results: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        href = urljoin(base_url, anchor.get("href"))
        if urlparse(href).scheme not in {"http", "https"}:
            continue
        if compiled and not any(pattern.search(href) for pattern in compiled):
            continue
        if any(pattern.search(href) for pattern in excluded):
            continue
        title = clean_text(anchor.get_text(" ", strip=True))
        if not title or title.casefold() in {"apply", "apply now", "read more", "view", "details"} or not is_valid_job_title(title):
            continue
        canonical = href.split("#", 1)[0]
        if canonical in seen:
            continue
        seen.add(canonical)
        parent = anchor.find_parent(["tr", "article", "li", "div"])
        context = clean_text(parent.get_text(" ", strip=True) if parent else "") or title
        results.append((title, canonical, context))
    return results


def is_expired(opportunity: dict) -> bool:
    deadline = opportunity.get("deadline")
    if not deadline:
        return False
    try:
        parsed = datetime.fromisoformat(str(deadline).replace("Z", "+00:00"))
        return parsed < datetime.now(timezone.utc)
    except ValueError:
        return False
