"""Conservative multilingual extraction for Phase 4.

Supported languages: English, French, Portuguese, Arabic and Swahili. The
functions favour false negatives over false positives because incorrect
experience, contract, deadline or eligibility data is more harmful than a
missing field.
"""
from __future__ import annotations

import calendar
import re
import unicodedata
from datetime import datetime, timezone
from typing import Any

from normalizers.location import detect_text_language, normalise_unicode

SUPPORTED_LANGUAGES = ("en", "fr", "pt", "ar", "sw")

# Range then minimum patterns. Arabic-Indic digits are normalised first.
_DIGIT_TRANS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")


def _digits(value: str | None) -> str:
    return (value or "").translate(_DIGIT_TRANS)


_YOE_PATTERNS: dict[str, list[tuple[re.Pattern[str], str]]] = {
    "en": [
        (re.compile(r"\b(\d{1,2})\s*(?:-|to)\s*(\d{1,2})\+?\s*years?\b", re.I), "range"),
        (re.compile(r"\b(?:at least|minimum(?:\s+of)?)\s+(\d{1,2})\+?\s*years?\b", re.I), "min"),
        (re.compile(r"\b(\d{1,2})\+\s*years?\b", re.I), "min"),
        (re.compile(r"\b(\d{1,2})\s*years?\s*(?:of\s+)?(?:relevant\s+|professional\s+|work\s+)?experience\b", re.I), "min"),
    ],
    "fr": [
        (re.compile(r"\b(\d{1,2})\s*(?:-|à|a)\s*(\d{1,2})\s*ans?\b", re.I), "range"),
        (re.compile(r"\b(?:au moins|minimum(?: de)?|minimum requis)\s+(\d{1,2})\s*ans?\b", re.I), "min"),
        (re.compile(r"\b(\d{1,2})\s*ans?\s+d['’ ]?exp[ée]rience\b", re.I), "min"),
    ],
    "pt": [
        (re.compile(r"\b(\d{1,2})\s*(?:-|a)\s*(\d{1,2})\s*anos?\b", re.I), "range"),
        (re.compile(r"\b(?:pelo menos|mínimo(?: de)?|minimo(?: de)?)\s+(\d{1,2})\s*anos?\b", re.I), "min"),
        (re.compile(r"\b(\d{1,2})\s*anos?\s+de\s+experi[êe]ncia\b", re.I), "min"),
    ],
    "ar": [
        (re.compile(r"(?:من\s*)?(\d{1,2})\s*(?:-|إلى|الى)\s*(\d{1,2})\s*سن(?:ة|وات)", re.I), "range"),
        (re.compile(r"(?:خبرة\s*)?(?:لا تقل عن|على الأقل|الحد الأدنى)\s*(\d{1,2})\s*سن(?:ة|وات)", re.I), "min"),
        (re.compile(r"(\d{1,2})\s*سن(?:ة|وات)\s*(?:من\s*)?الخبرة", re.I), "min"),
    ],
    "sw": [
        (re.compile(r"\bmiaka\s*(\d{1,2})\s*(?:-|hadi)\s*(\d{1,2})\b", re.I), "range"),
        (re.compile(r"\b(?:angalau|kiwango cha chini cha)\s*miaka\s*(\d{1,2})\b", re.I), "min"),
        (re.compile(r"\bmiaka\s*(\d{1,2})\s*(?:ya\s*)?uzoefu\b", re.I), "min"),
    ],
}


def extract_years_experience_multilingual(text: str | None) -> tuple[int | None, int | None, list[str]]:
    text = _digits(text)
    mins: list[int] = []
    maxs: list[int] = []
    languages: list[str] = []
    for language, patterns in _YOE_PATTERNS.items():
        matched_lang = False
        for pattern, kind in patterns:
            for match in pattern.finditer(text):
                matched_lang = True
                if kind == "range":
                    low, high = int(match.group(1)), int(match.group(2))
                    if 0 <= low <= high <= 40:
                        mins.append(low); maxs.append(high)
                else:
                    value = int(match.group(1))
                    if 0 <= value <= 40:
                        mins.append(value)
        if matched_lang:
            languages.append(language)
    return (min(mins) if mins else None, max(maxs) if maxs else None, languages)


_CONTRACT_PATTERNS: list[tuple[str, str, re.Pattern[str]]] = [
    ("volunteer", "en", re.compile(r"\bvolunteer\b", re.I)),
    ("consultant", "en", re.compile(r"\bconsultan(?:t|cy)\b", re.I)),
    ("part_time", "en", re.compile(r"\bpart[\s-]?time\b", re.I)),
    ("fixed_term", "en", re.compile(r"\bfixed[\s-]?term\b|\b\d+[\s-]?month(?:s)?\s+contract\b", re.I)),
    ("contract", "en", re.compile(r"\bcontract(?:or)?\b", re.I)),
    ("permanent", "en", re.compile(r"\bpermanent\b|\bfull[\s-]?time\b", re.I)),
    ("volunteer", "fr", re.compile(r"\bb[ée]n[ée]vole\b|\bvolontariat\b", re.I)),
    ("consultant", "fr", re.compile(r"\bconsultant(?:e)?\b|\bconsultance\b", re.I)),
    ("part_time", "fr", re.compile(r"\btemps partiel\b", re.I)),
    ("fixed_term", "fr", re.compile(r"\bcontrat à dur[ée]e d[ée]termin[ée]e\b|\bcdd\b|\bposte temporaire\b", re.I)),
    ("permanent", "fr", re.compile(r"\bcontrat à dur[ée]e ind[ée]termin[ée]e\b|\bcdi\b|\btemps plein\b", re.I)),
    ("contract", "fr", re.compile(r"\bsous contrat\b|\bcontrat\b", re.I)),
    ("volunteer", "pt", re.compile(r"\bvolunt[aá]ri[oa]\b", re.I)),
    ("consultant", "pt", re.compile(r"\bconsultor(?:a|ia)?\b", re.I)),
    ("part_time", "pt", re.compile(r"\btempo parcial\b", re.I)),
    ("fixed_term", "pt", re.compile(r"\bprazo determinado\b|\bcontrato a termo\b|\bcontrato de \d+ meses\b", re.I)),
    ("permanent", "pt", re.compile(r"\btempo integral\b|\bcontrato permanente\b|\bsem termo\b", re.I)),
    ("contract", "pt", re.compile(r"\bcontrato\b", re.I)),
    ("volunteer", "ar", re.compile(r"متطوع|تطوع", re.I)),
    ("consultant", "ar", re.compile(r"استشاري|مستشار", re.I)),
    ("part_time", "ar", re.compile(r"دوام جزئي", re.I)),
    ("fixed_term", "ar", re.compile(r"عقد محدد المدة|عقد لمدة \d+ أشهر", re.I)),
    ("permanent", "ar", re.compile(r"دوام كامل|عقد دائم", re.I)),
    ("contract", "ar", re.compile(r"عقد", re.I)),
    ("volunteer", "sw", re.compile(r"\bkujitolea\b|\bmjitoleaji\b", re.I)),
    ("consultant", "sw", re.compile(r"\bmshauri\b|\bushauri\b", re.I)),
    ("part_time", "sw", re.compile(r"\bmuda wa sehemu\b", re.I)),
    ("fixed_term", "sw", re.compile(r"\bmkataba wa muda maalum\b", re.I)),
    ("permanent", "sw", re.compile(r"\bmuda wote\b|\bajira ya kudumu\b", re.I)),
    ("contract", "sw", re.compile(r"\bmkataba\b", re.I)),
]


def extract_contract_type_multilingual(title: str | None, text: str | None) -> tuple[str, str | None]:
    for source in (title or "", text or ""):
        for contract, language, pattern in _CONTRACT_PATTERNS:
            if pattern.search(source):
                return contract, language
    return "unknown", None


_LANGUAGE_TERMS = {
    "english": ["english", "anglais", "inglês", "ingles", "الإنجليزية", "kiingereza"],
    "french": ["french", "français", "francais", "francophone", "francês", "الفرنسية", "kifaransa"],
    "arabic": ["arabic", "arabe", "árabe", "العربية", "kiarabu"],
    "portuguese": ["portuguese", "portugais", "português", "البرتغالية", "kireno"],
    "swahili": ["swahili", "kiswahili", "السواحيلية"],
    "amharic": ["amharic", "amharique", "amárico", "الأمهرية"],
    "spanish": ["spanish", "espagnol", "espanhol", "الإسبانية", "kihispania"],
}
_REQUIREMENT_CONTEXT = re.compile(
    r"fluen|proficien|working knowledge|command of|required|maîtrise|courant|obligatoire|"
    r"domínio|fluente|obrigatório|إجادة|بطلاقة|مطلوب|ufasaha|anahitajika",
    re.I,
)


def extract_languages_required_multilingual(text: str | None) -> list[str]:
    if not text:
        return []
    low = text.casefold()
    found: set[str] = set()
    negation = re.compile(r"no language required|language not required|aucune langue requise|langue non requise|idioma não obrigatório|idioma nao obrigatorio|اللغة غير مطلوبة|lugha haihitajiki", re.I)
    incidental = re.compile(r"^(?:\s+)(government|government-funded|donor|embassy|agency|company|market|office|law|national)", re.I)
    for language, terms in _LANGUAGE_TERMS.items():
        for term in terms:
            for match in re.finditer(re.escape(term.casefold()), low):
                before = low[max(0, match.start() - 80):match.start()]
                after = low[match.end():min(len(low), match.end() + 45)]
                window = before + low[match.start():match.end()] + after
                if negation.search(window):
                    continue
                # Requirement wording normally precedes the language ("fluent
                # in French") or immediately follows it ("French required").
                # A distant phrase such as "French government ... no language
                # required" must not create a false requirement.
                required_before = bool(_REQUIREMENT_CONTEXT.search(before))
                required_after = bool(_REQUIREMENT_CONTEXT.search(after[:25]))
                if incidental.search(after) and not required_before:
                    continue
                if required_before or required_after:
                    found.add(language); break
    return sorted(found)


_MONTHS: dict[str, dict[str, int]] = {
    "en": {name.casefold(): i for i, name in enumerate(calendar.month_name) if name} | {name.casefold(): i for i, name in enumerate(calendar.month_abbr) if name},
    "fr": {"janvier":1,"février":2,"fevrier":2,"mars":3,"avril":4,"mai":5,"juin":6,"juillet":7,"août":8,"aout":8,"septembre":9,"octobre":10,"novembre":11,"décembre":12,"decembre":12},
    "pt": {"janeiro":1,"fevereiro":2,"março":3,"marco":3,"abril":4,"maio":5,"junho":6,"julho":7,"agosto":8,"setembro":9,"outubro":10,"novembro":11,"dezembro":12},
    "sw": {"januari":1,"februari":2,"machi":3,"aprili":4,"mei":5,"juni":6,"julai":7,"agosti":8,"septemba":9,"oktoba":10,"novemba":11,"desemba":12},
}
_DEADLINE_LABEL = re.compile(r"deadline|closing date|apply by|date limite|clôture|cloture|prazo|data limite|آخر موعد|تاريخ الإغلاق|mwisho wa kutuma|tarehe ya mwisho", re.I)


def _iso(day: int, month: int, year: int) -> str | None:
    try:
        return datetime(year, month, day, 23, 59, 59, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
    except ValueError:
        return None


def extract_deadline_multilingual(text: str | None, default_year: int | None = None) -> tuple[str | None, str, str | None]:
    if not text or not _DEADLINE_LABEL.search(text):
        return None, "unknown", None
    source = _digits(text)
    # Numeric date after a deadline label, supports dd/mm/yyyy and yyyy-mm-dd.
    for match in re.finditer(r"(?:deadline|closing date|apply by|date limite|cl[ôo]ture|prazo|data limite|آخر موعد|تاريخ الإغلاق|mwisho wa kutuma|tarehe ya mwisho)[^\d]{0,30}(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", source, re.I):
        value=_iso(int(match.group(3)),int(match.group(2)),int(match.group(1)))
        if value: return value,"explicit",detect_text_language(match.group(0))
    for match in re.finditer(r"(?:deadline|closing date|apply by|date limite|cl[ôo]ture|prazo|data limite|آخر موعد|تاريخ الإغلاق|mwisho wa kutuma|tarehe ya mwisho)[^\d]{0,30}(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})", source, re.I):
        year=int(match.group(3)); year += 2000 if year < 100 else 0
        value=_iso(int(match.group(1)),int(match.group(2)),year)
        if value: return value,"explicit",detect_text_language(match.group(0))
    # Day + named month + year.
    all_months={name:(language,number) for language,rows in _MONTHS.items() for name,number in rows.items()}
    month_names="|".join(sorted((re.escape(x) for x in all_months),key=len,reverse=True))
    pattern=re.compile(rf"(?:deadline|closing date|apply by|date limite|cl[ôo]ture|prazo|data limite|mwisho wa kutuma|tarehe ya mwisho)[^\d]{{0,30}}(\d{{1,2}})\s+(?:de\s+)?({month_names})(?:\s+(?:de\s+)?)?(\d{{4}})?",re.I)
    match=pattern.search(source.casefold())
    if match:
        language,month=all_months[match.group(2).casefold()]
        year=int(match.group(3) or default_year or datetime.now(timezone.utc).year)
        value=_iso(int(match.group(1)),month,year)
        if value: return value,"explicit",language
    return None,"unknown",None


_ELIGIBILITY_PATTERNS = {
    "internal_only": re.compile(r"internal candidates? only|internal applicants? only|staff only|candidats? internes? uniquement|apenas candidatos internos|للمرشحين الداخليين فقط|waombaji wa ndani pekee", re.I),
    "local_only": re.compile(r"local candidates? only|nationals? only|national position|local hire|candidats? locaux seulement|ressortissants? uniquement|apenas candidatos locais|apenas nacionais|للمواطنين فقط|مرشحون محليون فقط|raia pekee|waombaji wa ndani pekee", re.I),
    "citizenship": re.compile(r"must be (?:a |an )?.+? citizen|citizenship required|doit être ressortissant|nationalité .* requise|deve ser cidadão|nacionalidade .* obrigatória|يجب أن يكون .* مواطناً|الجنسية .* مطلوبة|lazima awe raia", re.I),
    "work_auth": re.compile(r"existing work authori[sz]ation|required right to work|valid work permit|autorisation de travail valide|permis de travail requis|autorização de trabalho válida|visto de trabalho obrigatório|تصريح عمل ساري|إذن العمل مطلوب|kibali halali cha kufanya kazi", re.I),
    "international": re.compile(r"international applicants? welcome|open to applicants? worldwide|candidatures internationales|candidats internationaux|candidaturas internacionais|candidatos internacionais|المرشحون الدوليون|waombaji wa kimataifa", re.I),
}


def extract_eligibility_signals_multilingual(text: str | None) -> dict[str, Any]:
    source=text or ""
    matches={key: bool(pattern.search(source)) for key,pattern in _ELIGIBILITY_PATTERNS.items()}
    return {**matches,"detected_language":detect_text_language(source)}
