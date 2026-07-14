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


def _is_government_opportunity(opp: dict) -> bool:
    profile = opp.get("government_profile") or {}
    source = opp.get("source") or {}
    return bool(profile.get("is_government_or_public_service") or source.get("kind") == "government_official")


def _government_key(opp: dict) -> str | None:
    if not _is_government_opportunity(opp):
        return None
    profile = opp.get("government_profile") or {}
    fields = opp.get("government_fields") or {}
    organisation = opp.get("organisation") or {}
    location = opp.get("location") or {}
    nationalities = profile.get("eligible_nationalities") or fields.get("eligible_nationalities") or []
    country = _norm(
        location.get("country_code") or location.get("country")
        or (nationalities[0] if len(nationalities) == 1 else None)
        or (opp.get("public_institution_profile") or {}).get("country_code")
    )
    registry = _norm(profile.get("registry_id") or organisation.get("id") or organisation.get("name"))
    reference = _norm(profile.get("advert_reference") or fields.get("advert_reference"))
    title = _norm(opp.get("title"))
    if not country or not registry or not title:
        return None
    if reference:
        return f"government:{country}|{registry}|{reference}|{title}"
    grade = _norm(profile.get("public_service_grade") or fields.get("public_service_grade"))
    city = _norm(location.get("city") or location.get("admin_area"))
    return f"government:{country}|{registry}|{title}|{grade}|{city}"


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
    government_key = _government_key(opp)
    if government_key:
        # Government vacancies commonly share one portal URL or parent circular
        # PDF. URL-only deduplication would collapse hundreds of distinct posts.
        keys.append(government_key)
    else:
        for field in ("apply_url", "raw_description_url"):
            value = canonical_url(opp.get(field))
            if value:
                keys.append(f"url:{value}")
    # Government vacancies are identified only by their stable ID and explicit
    # government identity key.  They must never be collapsed by broad semantic
    # or description fingerprints: circulars routinely contain repeated job
    # titles across grades, departments, locations, and advert references.
    if not government_key:
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
    government_safe_duplicate_count = 0
    government_destructive_loss_count = 0

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
        winner_is_government = _is_government_opportunity(winner)
        loser_is_government = _is_government_opportunity(loser)
        government_match = any(key.startswith("government:") for key in matched_keys)
        exact_id_match = any(key.startswith("id:") for key in matched_keys)
        government_duplicate_type = None
        if loser_is_government:
            if winner_is_government and (government_match or exact_id_match):
                government_safe_duplicate_count += 1
                government_duplicate_type = "safe_identity_consolidation"
            else:
                government_destructive_loss_count += 1
                government_duplicate_type = "destructive_or_unexplained_loss"
        events.append({
            "kept_id": winner.get("id"),
            "removed_id": loser.get("id"),
            "replaced_existing": replace,
            "kept_source": (winner.get("source") or {}).get("name"),
            "removed_source": (loser.get("source") or {}).get("name"),
            "matched_by": sorted(matched_keys)[:8],
            "government_duplicate_type": government_duplicate_type,
        })

    government_input = sum(1 for row in opportunities if _is_government_opportunity(row))
    government_published = sum(1 for row in kept if _is_government_opportunity(row))
    government_removed = government_input - government_published
    # ``government_removed`` includes legitimate consolidation where the same
    # post appears in both a full circular and a department-specific PDF.  The
    # certification gate must measure only unexplained/destructive loss, not
    # safe duplicate cleanup.
    government_total_removed_percent = round((government_removed / government_input * 100), 1) if government_input else 0.0
    government_safe_duplicate_percent = round((government_safe_duplicate_count / government_input * 100), 1) if government_input else 0.0
    government_destructive_loss_percent = round((government_destructive_loss_count / government_input * 100), 1) if government_input else 0.0
    report = {
        "input_count": len(opportunities),
        "published_count": len(kept),
        "removed_count": len(opportunities) - len(kept),
        "official_replacements": sum(1 for row in events if row["replaced_existing"]),
        "government_input_count": government_input,
        "government_published_count": government_published,
        "government_removed_count": government_removed,
        "government_safe_duplicate_count": government_safe_duplicate_count,
        "government_destructive_loss_count": government_destructive_loss_count,
        "government_total_removed_percent": government_total_removed_percent,
        "government_duplicate_consolidation_percent": government_safe_duplicate_percent,
        "government_destructive_loss_percent": government_destructive_loss_percent,
        # Backward-compatible field: "loss" now means destructive loss only.
        "government_loss_percent": government_destructive_loss_percent,
        "events": events,
    }
    return kept, report
