"""Cross-source duplicate resolution with official-source precedence."""
from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def _norm(value) -> str:
    text = str(value or "").casefold()
    text = re.sub(r"\b(limited|ltd|incorporated|inc|plc|llc|company|co)\b", " ", text)
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def canonical_url(value: str | None) -> str | None:
    if not value or not str(value).startswith(("http://", "https://")):
        return None
    parts = urlsplit(str(value))
    host = parts.netloc.casefold().removeprefix("www.")
    path = re.sub(r"/+", "/", parts.path).rstrip("/")
    ignored = {"utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term", "ref", "source"}
    query = urlencode(sorted((k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k.casefold() not in ignored))
    return urlunsplit(("https", host, path, query, ""))


GENERIC_ORGANISATIONS = {
    "unknown employer",
    "unknown organisation",
    "confidential",
    "confidential employer",
    "not disclosed",
    "undisclosed",
    "reliefweb listed organisation",
}


def _usable_organisation_name(opp: dict) -> str | None:
    org = _norm((opp.get("organisation") or {}).get("name"))
    if not org or org in GENERIC_ORGANISATIONS:
        return None
    return org


def _semantic_key(opp: dict) -> str | None:
    org = _usable_organisation_name(opp)
    title = _norm(opp.get("title"))
    location = opp.get("location") or {}
    country = _norm(location.get("country_code") or location.get("country"))
    city = _norm(location.get("city"))
    deadline = _norm(opp.get("deadline"))
    if not org or not title or not country:
        return None
    if city:
        return f"semantic:{org}|{title}|{country}|{city}"
    if deadline:
        return f"semantic:{org}|{title}|{country}|{deadline}"
    return None


def _description_hash(opp: dict) -> str | None:
    text = _norm(opp.get("summary"))
    if len(text) < 120:
        return None
    return hashlib.sha256(text[:2000].encode()).hexdigest()[:20]


def _keys(opp: dict) -> list[str]:
    keys = [f"id:{opp.get('id')}"]
    for field in ("apply_url", "raw_description_url"):
        value = canonical_url(opp.get(field))
        if value:
            keys.append(f"url:{value}")
    semantic = _semantic_key(opp)
    if semantic:
        keys.append(semantic)
    org = _usable_organisation_name(opp)
    title = _norm(opp.get("title"))
    location = opp.get("location") or {}
    country = _norm(location.get("country_code") or location.get("country"))
    city = _norm(location.get("city"))
    desc = _description_hash(opp)
    if org and title and desc and country:
        keys.append(f"content:{org}|{title}|{country}|{city}|{desc}")
    return keys


def precedence_score(opp: dict) -> tuple[int, int]:
    source = opp.get("source") or {}
    confidence = source.get("confidence")
    kind = source.get("kind")
    score = 0
    if opp.get("apply_is_official"):
        score += 100
    score += {"official": 45, "aggregated": 20, "community": 5, "unverified": 0}.get(confidence, 0)
    score += {
        "employer_ats": 35,
        "employer_official": 35,
        "government_official": 35,
        "institution_official": 35,
        "institutional_aggregator": 12,
        "commercial_aggregator": 0,
    }.get(kind, 0)
    if (opp.get("organisation") or {}).get("verified"):
        score += 8
    completeness = sum(bool(opp.get(field)) for field in (
        "deadline", "years_experience_min", "education_required", "contract_type",
        "role_family", "industry", "summary",
    ))
    completeness += sum(bool((opp.get("location") or {}).get(field)) for field in ("country_code", "city"))
    return score, completeness


def deduplicate_opportunities(opportunities: list[dict]) -> tuple[list[dict], dict]:
    kept: list[dict] = []
    key_to_index: dict[str, int] = {}
    events: list[dict] = []

    for candidate in opportunities:
        candidate_keys = _keys(candidate)
        matched_keys = [key for key in candidate_keys if key in key_to_index]
        matched_indexes = {key_to_index[key] for key in matched_keys}
        if not matched_indexes:
            index = len(kept)
            kept.append(candidate)
            for key in candidate_keys:
                key_to_index[key] = index
            continue

        index = min(matched_indexes)
        incumbent = kept[index]
        replace = precedence_score(candidate) > precedence_score(incumbent)
        winner, loser = (candidate, incumbent) if replace else (incumbent, candidate)
        if replace:
            kept[index] = candidate
        all_keys = set(_keys(winner)) | set(_keys(loser))
        for key in all_keys:
            key_to_index[key] = index
        events.append({
            "kept_id": winner.get("id"),
            "removed_id": loser.get("id"),
            "replaced_existing": replace,
            "kept_source": (winner.get("source") or {}).get("name"),
            "removed_source": (loser.get("source") or {}).get("name"),
            "matched_by": sorted(matched_keys)[:8],
        })

    report = {
        "input_count": len(opportunities),
        "published_count": len(kept),
        "removed_count": len(opportunities) - len(kept),
        "official_replacements": sum(1 for row in events if row["replaced_existing"]),
        "events": events,
    }
    return kept, report
