"""Small helpers shared by every collector.

Deliberately tiny - each collector should still be easy to read end-to-end.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from html.parser import HTMLParser

from normalizers.location import default_location_normalizer, normalise_unicode
from normalizers.multilingual import (
    extract_contract_type_multilingual,
    extract_deadline_multilingual,
    extract_languages_required_multilingual,
    extract_years_experience_multilingual,
)


def now_iso() -> str:
    """Current UTC as an ISO-8601 Z-suffixed string, matching SCHEMA.md."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def millis_to_iso(millis: int | None) -> str | None:
    """Lever's createdAt is a millisecond epoch; the schema wants ISO-8601."""
    if millis is None:
        return None
    try:
        return datetime.fromtimestamp(int(millis) / 1000, tz=timezone.utc).isoformat().replace("+00:00", "Z")
    except (TypeError, ValueError, OSError):
        return None


class _StripTags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data):
        self.parts.append(data)


def html_to_text(html: str | None, max_chars: int = 300) -> str | None:
    """Both Greenhouse (`content`) and Lever (`descriptionPlain` is optional,
    `description` is HTML) give us HTML descriptions. Strip tags for `summary`.
    Truncated because feed.json is fetched on every app launch - keeping it
    small matters more than being complete (raw_description_url has the full
    thing anyway)."""
    if not html:
        return None
    parser = _StripTags()
    parser.feed(html)
    text = re.sub(r"\s+", " ", "".join(parser.parts)).strip()
    if not text:
        return None
    return (text[:max_chars] + "...") if len(text) > max_chars else text


# ---------------------------------------------------------------------------
# Location parsing
# ---------------------------------------------------------------------------
# Both Greenhouse and Lever give us free-text locations like "Nairobi, Kenya",
# "Remote - Africa", "Kigali, Rwanda / Remote", etc. There's no structured
# country/city field, so we parse best-effort - never confidently claim a
# country we can't verify. Spec §14: don't invent structured data.

_AFRICAN_COUNTRIES = {
    "kenya", "nigeria", "south africa", "ghana", "rwanda", "tanzania", "uganda",
    "ethiopia", "senegal", "cote d'ivoire", "côte d'ivoire", "ivory coast", "morocco",
    "egypt", "cameroon", "zambia", "zimbabwe", "malawi", "mozambique", "madagascar",
    "botswana", "mauritius", "namibia", "angola", "burkina faso", "mali", "sudan",
    "south sudan", "somalia", "sierra leone", "liberia", "togo", "benin", "gambia",
    "guinea", "niger", "chad", "burundi", "djibouti", "eritrea", "gabon", "congo",
    "drc", "democratic republic of congo", "democratic republic of the congo",
    "central african republic", "eswatini", "swaziland", "lesotho",
}

# Everywhere else we care about tagging is either "international" scope or
# a passthrough. Kept short - additions welcome but every entry here is doing
# work in the fit engine's location scoring, not just decorative.
_NON_AFRICAN_HINT_MAP = {
    "united states": "United States", "usa": "United States", "u.s.a": "United States",
    "us": "United States", "u.s": "United States",
    "united kingdom": "United Kingdom", "uk": "United Kingdom", "u.k": "United Kingdom",
    "canada": "Canada", "germany": "Germany", "france": "France",
    "netherlands": "Netherlands", "switzerland": "Switzerland", "belgium": "Belgium",
    "sweden": "Sweden", "denmark": "Denmark", "norway": "Norway",
    "spain": "Spain", "italy": "Italy", "ireland": "Ireland",
    "australia": "Australia", "japan": "Japan", "singapore": "Singapore", "india": "India",
    "united arab emirates": "United Arab Emirates", "uae": "United Arab Emirates",
}

_AFRICAN_COUNTRY_MAP = {c: c.title() for c in _AFRICAN_COUNTRIES}


def _find_country_hint(text: str, hint_map: dict) -> str | None:
    """Word-boundary match against a term->canonical-name map, longest terms
    checked first. Word-boundary matching (not naive substring) is what
    correctly catches short abbreviations like "US"/"UK" in strings like
    "Remote (US)" or "Remote-US" without also matching them inside unrelated
    words - naive substring matching on "us" would match inside "focus",
    "campus", "business" etc.
    """
    for term in sorted(hint_map.keys(), key=len, reverse=True):
        if re.search(r"\b" + re.escape(term) + r"\b", text):
            return hint_map[term]
    return None


# Terms that, alongside "remote" with no specific country, are a genuine
# positive signal that a role is open to Africa-based/global applicants -
# as opposed to a bare "Remote" that in practice often means remote-within-
# one-country. Deliberately narrow; add terms only when you've seen them
# actually used this way in a real job posting, not speculatively.
_REMOTE_POSITIVE_SIGNAL = re.compile(
    r"\b(africa|afrique|áfrica|afrika|افريقيا|أفريقيا|emea|global|anywhere|worldwide|international|"
    r"sub[\s-]?saharan|subsaharienne|subsaariana|pan[\s-]?african|panafricain)\b",
    re.I,
)

_REMOTE_SIGNAL = re.compile(
    r"\b(remote|remotely|à distance|a distance|télétravail|teletravail|remoto|عن بعد|mbali)\b",
    re.I,
)
_HYBRID_SIGNAL = re.compile(r"\b(hybrid|hybride|híbrido|hibrido|هجين|mseto)\b", re.I)


# Visa/relocation sponsorship language. If present, a role is worth keeping
# even when its location text points at a non-African country - a genuinely
# sponsorable role is a real opportunity for a Kenyan applicant, unlike a bare
# "Remote (US)" posting that in practice only hires US residents. Requires
# fairly explicit affirmative phrasing, and is guarded against negations
# below - "no visa sponsorship available" is far more common in real postings
# than a genuine sponsorship offer, and a bare regex match alone can't tell
# the two apart.
_SPONSORSHIP_SIGNAL = re.compile(
    r"\b(visa sponsorship|will sponsor|sponsors? (?:work )?visas?|"
    r"work authorization sponsorship|immigration support|"
    r"relocation (?:assistance|support|package|provided)|h-?1b sponsorship)\b",
    re.I,
)

_SPONSORSHIP_NEGATION = re.compile(
    r"\b(no|not|cannot|will not|won'?t|unable to|does not)\s+(?:provide\s+|offer\s+)?"
    r"(?:visa\s+)?sponsor",
    re.I,
)

# A sponsorship phrase can appear in company-wide boilerplate that is copied
# into every vacancy. It is only strong enough to override a non-African duty
# station when the same passage ties the offer to this role/position or
# explicitly invites international applicants. This prevents generic employer
# immigration-benefit text from making an entire US/Canada board appear open
# to Africa-based applicants.
_ROLE_SPECIFIC_MOBILITY_CONTEXT = re.compile(
    r"\b(this (?:role|position|job)|successful candidate|selected candidate|"
    r"international (?:candidate|candidates|applicant|applicants)|"
    r"applicants? (?:from|based in) (?:any country|anywhere|worldwide)|"
    r"open to (?:global|international|worldwide) (?:candidate|candidates|applicant|applicants))\b",
    re.I,
)


def has_sponsorship_signal(text: str | None) -> bool:
    """True only when the text makes an affirmative sponsorship claim, not
    merely mentions visas/sponsorship. Checked against real feed description
    text before being written this way."""
    if not text:
        return False
    if not _SPONSORSHIP_SIGNAL.search(text):
        return False
    if _SPONSORSHIP_NEGATION.search(text):
        return False
    return True


def has_role_specific_mobility_signal(text: str | None) -> bool:
    """Return True only for role-level international mobility evidence.

    A bare affirmative sponsorship phrase remains useful metadata, but it no
    longer determines feed inclusion. Inclusion requires nearby role-specific
    context or an explicit invitation to international applicants.
    """
    if not text or not has_sponsorship_signal(text):
        return False

    # Explicit international-applicant language anywhere in the description
    # is sufficiently role-specific.
    if _ROLE_SPECIFIC_MOBILITY_CONTEXT.search(text):
        return True

    # Otherwise require the sponsorship phrase and role/position wording to
    # occur in the same local passage, not in unrelated benefits boilerplate.
    for match in _SPONSORSHIP_SIGNAL.finditer(text):
        start = max(0, match.start() - 160)
        end = min(len(text), match.end() + 160)
        if _ROLE_SPECIFIC_MOBILITY_CONTEXT.search(text[start:end]):
            return True
    return False


def is_relevant_opportunity(location: dict, description: str | None = None) -> bool:
    """Single feed-inclusion rule shared by all collectors."""
    return is_relevant_to_african_applicant(location) or has_role_specific_mobility_signal(description)


def parse_location(raw: str | None) -> dict:
    """Multilingual, evidence-scored parse of a free-text location string.

    Phase 4 preserves the legacy location keys and adds canonical country/city,
    administrative area, coordinates, evidence and detected-language fields.
    """
    if not raw:
        return {
            "raw": None, "country": None, "region": None,
            "is_remote_from_kenya": False, "scope": None, "relocation_country": None,
            "country_code": None, "country_iso3": None, "city": None, "admin_area": None,
            "coordinates": None, "normalisation_confidence": 0.0,
            "normalisation_evidence": [], "location_language": "en", "is_african": False,
        }

    raw_stripped = raw.strip()
    lower = normalise_unicode(raw_stripped)
    match = default_location_normalizer().normalise(raw_stripped)
    is_remote = bool(_REMOTE_SIGNAL.search(raw_stripped) or _REMOTE_POSITIVE_SIGNAL.search(raw_stripped))

    country = match.country
    if country is None:
        # Retain the legacy limited non-African map for eligibility filtering.
        country = _find_country_hint(lower, _NON_AFRICAN_HINT_MAP)

    is_remote_from_kenya = False
    scope: str | None = None
    if match.country_code == "KE":
        scope = "national"
        is_remote_from_kenya = is_remote
    elif match.is_african and match.country_code:
        scope = "regional"
    elif country:
        scope = "international"
    elif is_remote and _REMOTE_POSITIVE_SIGNAL.search(raw_stripped):
        scope = "international"
        is_remote_from_kenya = True
    elif match.region:
        scope = "regional"
        is_remote_from_kenya = is_remote

    return {
        "raw": raw_stripped,
        "country": country,
        "region": match.region,
        "is_remote_from_kenya": is_remote_from_kenya,
        "scope": scope,
        "relocation_country": None,
        "country_code": match.country_code,
        "country_iso3": match.country_iso3,
        "city": match.city,
        "admin_area": match.admin_area,
        "coordinates": match.coordinates,
        "normalisation_confidence": match.confidence,
        "normalisation_evidence": list(match.evidence),
        "matched_location_alias": match.matched_alias,
        "location_language": match.detected_language,
        "is_african": match.is_african,
    }


def infer_work_mode(raw_location: str | None, structured_hint: str | None = None) -> str | None:
    """Infer work mode from structured or multilingual free-text signals."""
    if structured_hint:
        h = normalise_unicode(structured_hint)
        if h in {"remote", "remoto", "a distance", "عن بعد", "mbali"}:
            return "remote_global"
        if h in {"hybrid", "hybride", "hibrido", "هجين", "mseto"}:
            return "hybrid"
        if h in {"on site", "onsite", "sur site", "presencial", "في الموقع"}:
            return "onsite"

    if not raw_location:
        return None
    remote = bool(_REMOTE_SIGNAL.search(raw_location))
    hybrid = bool(_HYBRID_SIGNAL.search(raw_location))
    if remote and hybrid:
        return "hybrid"
    if hybrid:
        return "hybrid"
    if remote:
        match = default_location_normalizer().normalise(raw_location)
        if match.country_code == "KE":
            return "remote_kenya"
        if match.region in {"East Africa", "West Africa", "Central Africa", "Southern Africa", "North Africa", "Sub-Saharan Africa", "Africa"}:
            return "remote_regional"
        return "remote_global"
    return None


# ---------------------------------------------------------------------------
# Africa filter
# ---------------------------------------------------------------------------
# Greenhouse and Lever don't let us filter by country server-side, and most
# multinationals hire globally. We keep only postings that are either in an
# African country OR remote in a way an African applicant could take.
# Anything else is dropped rather than shipped as noise (recommendations
# doc §7: better a small feed of relevant roles than a big feed to sift).

def is_relevant_to_african_applicant(location: dict) -> bool:
    """`location` is the dict returned by :func:`parse_location`."""
    if location.get("is_remote_from_kenya"):
        return True
    if location.get("is_african") or location.get("country_code"):
        return bool(location.get("is_african") or location.get("country_code") in default_location_normalizer()._iso2)
    country = (location.get("country") or "").lower()
    return country in _AFRICAN_COUNTRIES


# ---------------------------------------------------------------------------
# Seniority inference from job title
# ---------------------------------------------------------------------------
# Neither Greenhouse nor Lever exposes a structured seniority field. Titles
# are the only signal, and title patterns are noisy - "Manager" alone doesn't
# distinguish mid from senior, and "Senior" prefixes are used inconsistently.
# We only tag seniority when the title is unambiguous; everything else stays
# None (SCHEMA.md says nullable and the fit engine handles missing values).

_TITLE_LEADERSHIP = re.compile(r"\b(chief|cxo|ceo|cfo|coo|cto|cio|cmo|vp|vice president|head of|country director|regional director|executive director|managing director)\b", re.I)
_TITLE_SENIOR = re.compile(r"\b(senior|sr\.?|principal|lead|staff|manager|director)\b", re.I)
_TITLE_ENTRY = re.compile(r"\b(intern|internship|junior|jr\.?|graduate|trainee|entry[- ]?level|associate)\b", re.I)


def infer_seniority(title: str | None) -> str | None:
    if not title:
        return None
    if _TITLE_LEADERSHIP.search(title):
        return "leadership"
    if _TITLE_ENTRY.search(title):
        return "entry"
    if _TITLE_SENIOR.search(title):
        # "Manager" and "Director" are ambiguous - could be mid or senior in
        # NGO/multilateral hierarchies. Conservatively tag as `senior`; the
        # fit engine's seniorityOpenness will handle stretch matches.
        return "senior"
    return None


# ---------------------------------------------------------------------------
# v3: years-of-experience extraction
# ---------------------------------------------------------------------------
# Every pattern here was written against real phrasing seen in ReliefWeb/
# Greenhouse/Lever job descriptions during Phase 1 development. Patterns are
# intentionally conservative - a false negative (missing signal) just leaves
# the field null, which the app already handles; a false positive (wrong
# number) actively misleads the fit engine and search filters, which is worse.

_YOE_PATTERNS = [
    # "5-8 years", "5 to 8 years" -> explicit range, most reliable signal
    (re.compile(r"\b(\d{1,2})\s*(?:-|to)\s*(\d{1,2})\+?\s*years?\b", re.I), "range"),
    # "at least 5 years", "minimum 5 years", "5+ years"
    (re.compile(r"\b(?:at least|minimum(?:\s+of)?)\s+(\d{1,2})\+?\s*years?\b", re.I), "min"),
    (re.compile(r"\b(\d{1,2})\+\s*years?\b", re.I), "min"),
    # bare "5 years experience" / "5 years of experience" - treat as a floor,
    # not an exact requirement, since job ads rarely mean "exactly 5".
    (re.compile(r"\b(\d{1,2})\s*years?\s*(?:of\s+)?(?:relevant\s+|professional\s+|work\s+)?experience\b", re.I), "min"),
]


def extract_years_experience(text: str | None) -> tuple[int | None, int | None]:
    """Return multilingual experience range for English/French/Portuguese/Arabic/Swahili."""
    minimum, maximum, _languages = extract_years_experience_multilingual(text)
    return minimum, maximum


# ---------------------------------------------------------------------------
# v3: education requirement extraction
# ---------------------------------------------------------------------------

_EDUCATION_LEVELS = [
    # Order matters - check most-specific/highest first so "Master's or PhD
    # preferred" resolves to phd, not masters.
    ("phd", re.compile(r"\b(ph\.?d|doctorate|doctoral degree)\b", re.I)),
    ("masters", re.compile(r"\b(master'?s?( degree)?|msc|ma\b|mba|meng)\b", re.I)),
    ("bachelor", re.compile(r"\b(bachelor'?s?( degree)?|bsc|ba\b|beng|undergraduate degree)\b", re.I)),
    ("diploma", re.compile(r"\b(diploma|associate degree)\b", re.I)),
    ("secondary", re.compile(r"\b(high school diploma|secondary school certificate|kcse)\b", re.I)),
]

# Degree *field* is separate from level - "Bachelor's in Engineering" should
# give both level=bachelor and fields=["engineering"]. Kept short; extend as
# real source text reveals more patterns worth catching.
_EDUCATION_FIELD_PATTERN = re.compile(
    r"\b(?:degree|diploma|ph\.?d|master'?s?|bachelor'?s?)\s+in\s+"
    r"([a-z][a-z\s,/&-]{2,60}?)"
    r"(?:\.|,|;|\(|\bis\b|\brequired\b|\bpreferred\b|\band\b\s+\d|\bor\b|$)",
    re.I,
)


def extract_education_requirement(text: str | None) -> tuple[str | None, list[str]]:
    """Returns (level, fields). `level` is the highest-mentioned qualification
    (a job that says "Bachelor's required, Master's preferred" returns
    "masters" since that's the ceiling mentioned, giving the user useful
    signal about what would make them a strong candidate - not just the bar).
    `fields` is best-effort, often empty - that's fine, it's a bonus signal.
    """
    if not text:
        return None, []

    level = None
    for level_id, pattern in _EDUCATION_LEVELS:
        if pattern.search(text):
            level = level_id
            break  # first match in priority order is the ceiling

    fields = []
    for m in _EDUCATION_FIELD_PATTERN.finditer(text):
        field = m.group(1).strip().lower()
        if 2 < len(field) < 60:
            fields.append(field)

    return level, fields[:3]  # cap - this is a bonus signal, not a full parse


# ---------------------------------------------------------------------------
# v3: language requirement extraction
# ---------------------------------------------------------------------------

_LANGUAGE_TERMS = {
    "english": ["english"],
    "french": ["french", "francophone"],
    "arabic": ["arabic"],
    "portuguese": ["portuguese"],
    "swahili": ["swahili", "kiswahili"],
    "amharic": ["amharic"],
    "spanish": ["spanish"],
}

_LANGUAGE_CONTEXT = re.compile(
    r"(fluen[ct]|proficien[ct]|working knowledge of|native speaker of|command of|required[:\s])",
    re.I,
)


def extract_languages_required(text: str | None) -> list[str]:
    """Extract explicitly required languages across five supported posting languages."""
    return extract_languages_required_multilingual(text)


# ---------------------------------------------------------------------------
# v3: contract type extraction
# ---------------------------------------------------------------------------

_CONTRACT_PATTERNS = [
    ("volunteer", re.compile(r"\bvolunteer\b", re.I)),
    ("consultant", re.compile(r"\bconsultan(t|cy)\b", re.I)),
    ("part_time", re.compile(r"\bpart[\s-]?time\b", re.I)),
    ("fixed_term", re.compile(r"\bfixed[\s-]?term\b|\b\d+[\s-]?month(?:s)?\s+contract\b", re.I)),
    ("contract", re.compile(r"\bcontract(?:or)?\b", re.I)),
    ("permanent", re.compile(r"\bpermanent\b|\bfull[\s-]?time\b", re.I)),
]


def extract_contract_type(title: str | None, text: str | None) -> str:
    """Extract contract type across English, French, Portuguese, Arabic and Swahili."""
    contract, _language = extract_contract_type_multilingual(title, text)
    return contract


def extract_deadline(text: str | None, default_year: int | None = None) -> tuple[str | None, str]:
    """Extract an explicit multilingual application deadline when present."""
    deadline, confidence, _language = extract_deadline_multilingual(text, default_year=default_year)
    return deadline, confidence


# ---------------------------------------------------------------------------
# v3: industry classification
# ---------------------------------------------------------------------------
# Best-effort heuristic classifier. Real accuracy comes from collectors that
# can pass a source's own category/department field through taxonomy.json's
# alias map (preferred path - see FeedBuilder.map_category equivalent for
# industries in refresh_feed.py). This function is the fallback for sources
# that give us nothing better than raw title + description text.

_INDUSTRY_KEYWORDS = {
    "technology": ["software engineer", "developer", "backend", "frontend", "full stack", "devops", "data engineer", "data scientist", "product manager", "ux designer", "cybersecurity", "site reliability", "machine learning", "data analyst", "qa engineer", "mobile engineer", "cloud engineer", "python", "javascript"],
    "financial_services": ["credit analyst", "credit risk", "credit analysis", "loan officer", "banking", "treasury", "underwrit", "risk manager", "actuary", "financial analyst"],
    "healthcare": ["nurse", "physician", "clinical", "medical officer", "pharmacist", "public health"],
    "education": ["teacher", "lecturer", "curriculum", "instructor", "school principal"],
    "development_humanitarian": ["programme officer", "program officer", "humanitarian", "protection officer", "m&e officer", "grants officer", "field coordinator", "country director", "ngo", "livelihoods", "smallholder farmers"],
    "agriculture_food": ["agronomist", "agricultural", "farm", "livestock", "veterinary"],
    "energy_environment": ["solar", "renewable energy", "environmental", "climate", "paygo"],
    "legal": ["lawyer", "attorney", "legal counsel", "compliance officer", "paralegal"],
    "marketing_communications": ["marketing manager", "communications officer", "content writer", "social media", "journalist"],
    "sales_business_development": ["sales representative", "business development", "account manager", "sales executive"],
    "operations_supply_chain": ["supply chain", "logistics", "warehouse", "procurement officer"],
    "human_resources": ["human resources", "hr manager", "recruiter", "talent acquisition"],
    "hospitality_tourism": ["hotel", "chef", "waiter", "tour guide", "front desk"],
    "construction": ["site engineer", "quantity surveyor", "construction manager", "foreman"],
    "public_sector": ["civil servant", "government", "county government"],
    "design_creative": ["graphic designer", "ui designer", "illustrator", "architect"],
    "transport_logistics": ["driver", "freight", "fleet manager", "customs"],
    "retail": ["store manager", "cashier", "merchandiser"],
    "administration": ["executive assistant", "office administrator", "receptionist", "data entry"],
    "customer_operations": ["customer service", "call centre", "customer success"],
    "skilled_trades": ["electrician", "plumber", "welder", "technician", "mechanic"],
}


def classify_industry(title: str | None, text: str | None = None) -> str | None:
    combined = f"{title or ''} {text or ''}".lower()
    if not combined.strip():
        return None
    scores: dict[str, int] = {}
    for industry_id, keywords in _INDUSTRY_KEYWORDS.items():
        for kw in keywords:
            if kw in combined:
                scores[industry_id] = scores.get(industry_id, 0) + 1
    if not scores:
        return None
    return max(scores, key=scores.get)


# ---------------------------------------------------------------------------
# v3: salary normalisation
# ---------------------------------------------------------------------------

def normalise_salary(
    min_amount: float | None,
    max_amount: float | None,
    currency: str | None,
    period: str | None,
    fx_rates_to_usd: dict[str, float] | None = None,
) -> tuple[float | None, float | None]:
    """Converts a salary range to USD-equivalent for cross-source/cross-
    currency comparison, normalised to an annual figure. Returns (None, None)
    if we don't have enough to convert confidently - never silently assume
    an exchange rate or a period. `fx_rates_to_usd` maps ISO currency code to
    "1 unit of that currency in USD" (e.g. {"KES": 0.0067}), refreshed daily
    by scripts/refresh_fx.py and passed in by the caller.
    """
    if min_amount is None and max_amount is None:
        return None, None
    if not currency or not fx_rates_to_usd or currency.upper() not in fx_rates_to_usd:
        return None, None

    rate = fx_rates_to_usd[currency.upper()]
    period_multiplier = {"year": 1, "month": 12, "hour": 2080, "day": 260}.get((period or "").lower())
    if period_multiplier is None:
        return None, None  # unknown period - don't guess

    def convert(amount: float | None) -> float | None:
        if amount is None:
            return None
        return round(amount * rate * period_multiplier, 2)

    return convert(min_amount), convert(max_amount)
