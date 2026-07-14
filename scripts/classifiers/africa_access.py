"""Africa relevance and African-applicant access certification.

This layer deliberately separates *where/what the role is about* from *who may
apply*.  It never treats an African duty station as proof of applicant
eligibility and consumes structured government citizenship data before weaker
text inference.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import Any

from normalizers.location import normalise_unicode

AFRICA_RELEVANCE_STATUSES = {
    "africa_based_confirmed",
    "africa_regional",
    "remote_confirmed_open_to_africa",
    "africa_remit_non_african_location",
    "official_location_pending",
    "global_access_unconfirmed",
    "non_african",
    "unresolved",
}

AFRICAN_APPLICANT_ACCESS_STATUSES = {
    "confirmed_any_african_national",
    "confirmed_specific_african_nationality",
    "confirmed_international_recruitment",
    "likely_open",
    "work_authorisation_required",
    "local_only",
    "internal_only",
    "unknown",
    "not_open",
}

CERTIFICATION_LEVELS = {"certified", "conditional", "unverified", "excluded"}

_AFRICA_REMIT_RE = re.compile(
    r"\b(?:africa|african|sub[- ]saharan|east africa|west africa|central africa|"
    r"southern africa|north africa|pan[- ]african|afrique|africa ocidental|"
    r"africa oriental|afrika mashariki|afrika magharibi)\b",
    re.I,
)
_REMOTE_GLOBAL_RE = re.compile(
    r"\b(?:remote(?:ly)?|worldwide|global(?:ly)?|anywhere|location flexible|"
    r"work from anywhere|emea|europe middle east and africa)\b",
    re.I,
)
_EXPLICIT_AFRICA_ACCESS_RE = re.compile(
    r"\b(?:open to|applications? from|applicants? from|candidates? from|eligible applicants? from)\s+"
    r"(?:all\s+)?(?:african countries|africa|the african continent|sub[- ]saharan africa)\b",
    re.I,
)
_ANY_AFRICAN_NATIONAL_RE = re.compile(
    r"\b(?:citizens?|nationals?)\s+of\s+(?:any|all)\s+african\s+(?:country|countries|states?)\b|"
    r"\bopen to african (?:citizens?|nationals?)\b",
    re.I,
)
_INTERNATIONAL_RE = re.compile(
    r"\b(?:international applicants? (?:are )?(?:welcome|eligible|encouraged)|"
    r"open to international applicants?|internationally recruited|global recruitment|"
    r"visa sponsorship (?:is )?(?:available|provided)|relocation support (?:is )?provided)\b",
    re.I,
)
_WORK_AUTH_RE = re.compile(
    r"\b(?:must|should|required to)\s+(?:already\s+)?(?:have|hold|possess)\s+"
    r"(?:valid\s+)?(?:work authori[sz]ation|right to work|work permit)|"
    r"\bno (?:visa|work permit) sponsorship\b|\bwithout sponsorship\b",
    re.I,
)
_LOCAL_ONLY_RE = re.compile(
    r"\b(?:local candidates? only|local applicants? only|locally recruited|local hire|local contract)\b",
    re.I,
)
_EXPLICIT_NATIONALITY_RE = re.compile(
    r"\b(?:national position|national officer|nationals? only|citizens? only|"
    r"must be (?:a |an )?(?:[a-z -]+ )?(?:nationals?|citizens?)|"
    r"only (?:[a-z -]+ )?(?:nationals?|citizens?)|"
    r"restricted to (?:[a-z -]+ )?(?:nationals?|citizens?))\b",
    re.I,
)
_INTERNAL_RE = re.compile(r"\b(?:internal candidates? only|internal applicants? only|staff only)\b", re.I)
_EXPLICIT_NOT_OPEN_RE = re.compile(
    r"\b(?:not open to international applicants?|no international applicants?|"
    r"applicants? must reside in|must be based in (?:the )?united states|us residents? only|"
    r"canada residents? only)\b",
    re.I,
)


@dataclass(frozen=True)
class AfricaRelevanceProfile:
    status: str
    confidence: float
    evidence: tuple[str, ...]
    certification_level: str
    default_visible: bool
    known_country_code: str | None
    known_country_name: str | None

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["evidence"] = list(self.evidence)
        return data


@dataclass(frozen=True)
class AfricanApplicantAccessProfile:
    status: str
    confidence: float
    evidence: tuple[str, ...]
    evidence_strength: str
    eligible_nationalities: tuple[str, ...]
    citizenship_required: bool | None
    work_authorisation_required: bool | None
    certification_level: str

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["evidence"] = list(self.evidence)
        data["eligible_nationalities"] = list(self.eligible_nationalities)
        return data


class AfricaAccessClassifier:
    def __init__(self, african_locations: dict[str, Any], global_countries: dict[str, Any]):
        self.african_iso2 = {
            str(row.get("iso2") or "").upper()
            for row in african_locations.get("countries", [])
            if row.get("iso2")
        }
        self.by_iso2: dict[str, dict[str, Any]] = {}
        self.by_iso3: dict[str, dict[str, Any]] = {}
        self.country_terms: list[tuple[str, dict[str, Any]]] = []
        self.nationality_terms: list[tuple[str, dict[str, Any]]] = []
        for row in global_countries.get("countries", []):
            iso2 = str(row.get("iso2") or "").upper()
            iso3 = str(row.get("iso3") or "").upper()
            if iso2:
                self.by_iso2[iso2] = row
            if iso3:
                self.by_iso3[iso3] = row
            for value in [row.get("name"), *row.get("aliases", [])]:
                term = normalise_unicode(value)
                if len(term) >= 4:
                    self.country_terms.append((term, row))
            for value in row.get("nationality_terms", []):
                term = normalise_unicode(value)
                if len(term) >= 4:
                    self.nationality_terms.append((term, row))
        self.country_terms.sort(key=lambda item: len(item[0]), reverse=True)
        self.nationality_terms.sort(key=lambda item: len(item[0]), reverse=True)

    @staticmethod
    def _combined_text(opp: dict[str, Any]) -> str:
        location = opp.get("location") or {}
        return " ".join(
            str(value or "")
            for value in (
                opp.get("title"),
                opp.get("summary"),
                opp.get("eligibility_notes"),
                location.get("raw"),
                location.get("scope"),
                opp.get("work_mode"),
            )
        )

    @staticmethod
    def _official(opp: dict[str, Any]) -> bool:
        source = opp.get("source") or {}
        return bool(
            opp.get("apply_is_official")
            or source.get("confidence") == "official"
            or source.get("kind") in {"employer_ats", "employer_official", "government_official", "institution_official"}
        )

    @staticmethod
    def _vacancy_specific(opp: dict[str, Any]) -> bool:
        title = str(opp.get("title") or "").strip()
        url = str(opp.get("apply_url") or "")
        return len(title) >= 4 and url.startswith(("http://", "https://"))

    def detect_global_country(self, raw: str | None, existing_code: str | None = None, existing_country: str | None = None) -> dict[str, Any] | None:
        if existing_code:
            row = self.by_iso2.get(str(existing_code).upper()) or self.by_iso3.get(str(existing_code).upper())
            if row:
                return row
        if existing_country:
            normalised_existing = normalise_unicode(existing_country)
            for term, row in self.country_terms:
                if normalised_existing == term:
                    return row
        raw_text = str(raw or "")
        # Uppercase ISO tokens only; avoids treating ordinary words as codes.
        for match in re.finditer(r"(?:^|[\s,;/()\[\]|-])([A-Z]{2,3})(?=$|[\s,;/()\[\]|-])", raw_text):
            token = match.group(1)
            row = self.by_iso2.get(token) or self.by_iso3.get(token)
            if row:
                return row
        normalised = normalise_unicode(raw_text)
        for term, row in self.country_terms:
            if f" {term} " in f" {normalised} ":
                return row
        return None


    def detect_nationality_codes(self, text: str | None) -> tuple[str, ...]:
        normalised = normalise_unicode(text)
        matches: list[str] = []
        for term, row in self.nationality_terms:
            if f" {term} " in f" {normalised} ":
                code = str(row.get("iso2") or "").upper()
                if code and code not in matches:
                    matches.append(code)
        # Country names in an explicit citizenship sentence are also valid.
        for term, row in self.country_terms:
            if f" {term} " in f" {normalised} ":
                code = str(row.get("iso2") or "").upper()
                if code and code not in matches:
                    matches.append(code)
        return tuple(matches)

    def classify_relevance(self, opp: dict[str, Any]) -> AfricaRelevanceProfile:
        location = opp.get("location") or {}
        text = self._combined_text(opp)
        country = self.detect_global_country(
            location.get("raw"),
            location.get("country_code") or location.get("country_iso3"),
            location.get("country_canonical") or location.get("country"),
        )
        code = str(country.get("iso2")) if country else None
        name = str(country.get("name")) if country else None
        is_african = bool(location.get("is_african") or (code and code in self.african_iso2))
        africa_remit = bool(_AFRICA_REMIT_RE.search(text))
        explicit_remote = bool(_REMOTE_GLOBAL_RE.search(text) or location.get("is_remote_from_kenya"))
        explicit_africa_access = bool(_EXPLICIT_AFRICA_ACCESS_RE.search(text))

        if is_african:
            return AfricaRelevanceProfile(
                "africa_based_confirmed", 0.99,
                ("physical_duty_station_in_africa",), "certified", True, code, name,
            )
        if country and not bool(country.get("is_african")):
            if africa_remit:
                return AfricaRelevanceProfile(
                    "africa_remit_non_african_location", 0.9,
                    ("known_non_african_duty_station", "explicit_africa_remit"),
                    "conditional", True, code, name,
                )
            return AfricaRelevanceProfile(
                "non_african", 0.99,
                ("known_non_african_duty_station",), "excluded", False, code, name,
            )
        if explicit_remote and (explicit_africa_access or (africa_remit and "remote" in text.casefold())):
            return AfricaRelevanceProfile(
                "remote_confirmed_open_to_africa", 0.9,
                ("remote_or_global_role", "explicit_africa_access"), "certified", True, None, None,
            )
        if africa_remit:
            return AfricaRelevanceProfile(
                "africa_regional", 0.84,
                ("explicit_africa_region_or_remit",), "conditional", True, None, None,
            )
        if explicit_remote:
            return AfricaRelevanceProfile(
                "global_access_unconfirmed", 0.64,
                ("global_or_remote_scope", "african_access_not_confirmed"),
                "unverified", False, None, None,
            )
        if self._official(opp) and self._vacancy_specific(opp):
            return AfricaRelevanceProfile(
                "official_location_pending", 0.55,
                ("verified_official_vacancy", "duty_station_not_confirmed"),
                "unverified", False, None, None,
            )
        return AfricaRelevanceProfile(
            "unresolved", 0.2, ("insufficient_geographic_evidence",), "unverified", False, None, None,
        )

    def classify_access(self, opp: dict[str, Any], relevance: AfricaRelevanceProfile) -> AfricanApplicantAccessProfile:
        text = self._combined_text(opp)
        government = opp.get("government_profile") or {}
        structured_citizenship = government.get("citizenship_required")
        structured_nationalities = tuple(
            sorted({str(code).upper() for code in (government.get("eligible_nationalities") or []) if code})
        )
        structured_internal = bool(government.get("internal_only"))

        if structured_internal or _INTERNAL_RE.search(text):
            return AfricanApplicantAccessProfile(
                "internal_only", 0.99, ("structured_or_explicit_internal_only",), "explicit",
                structured_nationalities, structured_citizenship, None, "excluded",
            )
        if structured_citizenship and structured_nationalities:
            african_codes = tuple(code for code in structured_nationalities if code in self.african_iso2)
            if african_codes:
                return AfricanApplicantAccessProfile(
                    "confirmed_specific_african_nationality", 0.99,
                    ("structured_government_citizenship_requirement",), "structured_source",
                    african_codes, True, None, "certified",
                )
            return AfricanApplicantAccessProfile(
                "not_open", 0.99, ("structured_non_african_citizenship_requirement",),
                "structured_source", structured_nationalities, True, None, "excluded",
            )
        if _ANY_AFRICAN_NATIONAL_RE.search(text):
            return AfricanApplicantAccessProfile(
                "confirmed_any_african_national", 0.96, ("explicit_any_african_nationality",),
                "explicit", (), False, None, "certified",
            )
        if _EXPLICIT_NOT_OPEN_RE.search(text):
            return AfricanApplicantAccessProfile(
                "not_open", 0.95, ("explicit_not_open_to_international_or_african_applicants",),
                "explicit", (), None, None, "excluded",
            )
        if _WORK_AUTH_RE.search(text):
            return AfricanApplicantAccessProfile(
                "work_authorisation_required", 0.92, ("explicit_existing_work_authorisation_required",),
                "explicit", (), None, True, "conditional",
            )
        if _EXPLICIT_NATIONALITY_RE.search(text):
            detected_codes = self.detect_nationality_codes(text)
            if not detected_codes and relevance.known_country_code:
                detected_codes = (relevance.known_country_code,)
            african_codes = tuple(code for code in detected_codes if code in self.african_iso2)
            non_african_codes = tuple(code for code in detected_codes if code and code not in self.african_iso2)
            if african_codes:
                return AfricanApplicantAccessProfile(
                    "confirmed_specific_african_nationality", 0.96,
                    ("explicit_african_nationality_requirement",),
                    "explicit", african_codes, True, None, "certified",
                )
            if non_african_codes:
                return AfricanApplicantAccessProfile(
                    "not_open", 0.96, ("explicit_non_african_nationality_requirement",),
                    "explicit", non_african_codes, True, None, "excluded",
                )
            return AfricanApplicantAccessProfile(
                "local_only", 0.88, ("explicit_nationality_requirement_country_unresolved",),
                "explicit", (), True, None, "conditional",
            )
        if _LOCAL_ONLY_RE.search(text):
            return AfricanApplicantAccessProfile(
                "local_only", 0.9, ("explicit_local_recruitment",), "explicit",
                (), None, True, "conditional",
            )
        if _INTERNATIONAL_RE.search(text):
            return AfricanApplicantAccessProfile(
                "confirmed_international_recruitment", 0.94,
                ("explicit_international_recruitment",), "explicit", (), False, None, "certified",
            )
        if _EXPLICIT_AFRICA_ACCESS_RE.search(text):
            return AfricanApplicantAccessProfile(
                "likely_open", 0.88, ("explicit_africa_applicant_access",), "explicit",
                (), False, None, "conditional",
            )
        if relevance.status == "remote_confirmed_open_to_africa":
            return AfricanApplicantAccessProfile(
                "likely_open", 0.82, ("remote_confirmed_open_to_africa",), "strong_inference",
                (), None, None, "conditional",
            )
        # Duty station alone is not applicant-access evidence.
        return AfricanApplicantAccessProfile(
            "unknown", 0.25, ("applicant_access_not_stated",), "none",
            structured_nationalities, structured_citizenship, None, "unverified",
        )

    def classify(self, opp: dict[str, Any]) -> tuple[AfricaRelevanceProfile, AfricanApplicantAccessProfile]:
        relevance = self.classify_relevance(opp)
        access = self.classify_access(opp, relevance)
        return relevance, access


def legacy_eligibility_from_access(profile: AfricanApplicantAccessProfile) -> dict[str, Any]:
    mapping = {
        "confirmed_any_african_national": "eligible",
        "confirmed_specific_african_nationality": "citizenship_restricted",
        "confirmed_international_recruitment": "eligible",
        "likely_open": "likely_eligible",
        "work_authorisation_required": "uncertain",
        "local_only": "local_only",
        "internal_only": "internal_only",
        "unknown": "uncertain",
        "not_open": "ineligible",
    }
    return {
        "status": mapping[profile.status],
        "confidence": profile.confidence,
        "citizenship_required": profile.citizenship_required,
        "eligible_nationalities": list(profile.eligible_nationalities),
        "work_authorisation_required": profile.work_authorisation_required,
        "evidence": list(profile.evidence),
        "evidence_strength": profile.evidence_strength,
    }
