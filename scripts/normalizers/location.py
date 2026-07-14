"""Phase 4 multilingual African location normalisation.

The normaliser is deliberately evidence-first: it emits a canonical country or
city only when an explicit country/city/admin-area/region alias is present. It
supports Unicode scripts and therefore does not erase Arabic text the way the
legacy ASCII-only normaliser did.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


def normalise_unicode(value: str | None) -> str:
    """Casefold and collapse punctuation while preserving letters in all scripts."""
    chars: list[str] = []
    for ch in unicodedata.normalize("NFKC", value or "").casefold():
        category = unicodedata.category(ch)
        chars.append(ch if category[0] in {"L", "N"} else " ")
    return re.sub(r"\s+", " ", "".join(chars)).strip()


def _contains(haystack: str, needle: str) -> bool:
    if not needle:
        return False
    return f" {needle} " in f" {haystack} "


def detect_text_language(value: str | None) -> str:
    raw = value or ""
    if re.search(r"[\u0600-\u06ff]", raw):
        return "ar"
    low = normalise_unicode(raw)
    if any(_contains(low, term) for term in ("localizacao", "localização", "vaga", "prazo", "experiencia", "experiência", "candidato", "candidatos", "apenas", "contrato", "moçambique")):
        return "pt"
    if any(_contains(low, term) for term in ("lieu d affectation", "poste base", "date limite", "expérience", "candidat", "candidats", "ressortissant", "contrat", "afrique de")):
        return "fr"
    if any(_contains(low, term) for term in ("mahali pa kazi", "jiji la", "mwisho wa kutuma", "uzoefu", "afrika mashariki", "lazima", "raia", "waombaji", "mkataba")):
        return "sw"
    return "en"


@dataclass(frozen=True)
class LocationMatch:
    raw: str | None
    country: str | None = None
    country_code: str | None = None
    country_iso3: str | None = None
    city: str | None = None
    admin_area: str | None = None
    region: str | None = None
    coordinates: dict[str, float] | None = None
    confidence: float = 0.0
    evidence: tuple[str, ...] = ()
    matched_alias: str | None = None
    detected_language: str = "en"
    is_african: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["evidence"] = list(self.evidence)
        return payload


class AfricanLocationNormalizer:
    def __init__(self, registry: dict[str, Any]):
        self.registry = registry
        self.countries = registry.get("countries", [])
        self._country_terms: list[tuple[str, str, dict[str, Any]]] = []
        self._iso2: dict[str, dict[str, Any]] = {}
        self._iso3: dict[str, dict[str, Any]] = {}
        self._city_terms: list[tuple[str, str, dict[str, Any], dict[str, Any]]] = []
        self._admin_terms: list[tuple[str, str, dict[str, Any], dict[str, Any]]] = []
        self._region_terms: list[tuple[str, str]] = []

        for country in self.countries:
            self._iso2[str(country.get("iso2", "")).upper()] = country
            self._iso3[str(country.get("iso3", "")).upper()] = country
            for alias in [country.get("name"), *country.get("aliases", [])]:
                term = normalise_unicode(alias)
                if len(term) >= 3:
                    self._country_terms.append((term, str(alias), country))
            for city in country.get("cities", []):
                for alias in [city.get("name"), *city.get("aliases", [])]:
                    term = normalise_unicode(alias)
                    if len(term) >= 2:
                        self._city_terms.append((term, str(alias), city, country))
            for area in country.get("admin_areas", []):
                for alias in [area.get("name"), *area.get("aliases", [])]:
                    term = normalise_unicode(alias)
                    if len(term) >= 2:
                        self._admin_terms.append((term, str(alias), area, country))

        for region, aliases in registry.get("region_aliases", {}).items():
            for alias in [region, *aliases]:
                term = normalise_unicode(alias)
                if term:
                    self._region_terms.append((term, region))

        self._country_terms.sort(key=lambda row: len(row[0]), reverse=True)
        self._city_terms.sort(key=lambda row: len(row[0]), reverse=True)
        self._admin_terms.sort(key=lambda row: len(row[0]), reverse=True)
        self._region_terms.sort(key=lambda row: len(row[0]), reverse=True)

    @classmethod
    def from_path(cls, path: str | Path) -> "AfricanLocationNormalizer":
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    @staticmethod
    def _iso_hint(raw: str, mapping: dict[str, dict[str, Any]], length: int) -> dict[str, Any] | None:
        # Require uppercase source notation and separators to avoid treating
        # ordinary words such as "ma", "to" or "in" as country codes.
        pattern = rf"(?:^|[\s,;/()\[\]-])([A-Z]{{{length}}})(?=$|[\s,;/()\[\]-])"
        for match in re.finditer(pattern, raw):
            country = mapping.get(match.group(1))
            if country:
                return country
        return None

    def _explicit_country(self, raw: str, normalised: str, existing_country: str | None) -> tuple[dict[str, Any] | None, str | None, str | None]:
        existing = normalise_unicode(existing_country)
        if existing:
            for term, alias, country in self._country_terms:
                if existing == term:
                    return country, "existing_country", str(existing_country)
            code = str(existing_country).upper().strip()
            if code in self._iso2:
                return self._iso2[code], "existing_iso2", code
            if code in self._iso3:
                return self._iso3[code], "existing_iso3", code

        country = self._iso_hint(raw, self._iso3, 3) or self._iso_hint(raw, self._iso2, 2)
        if country:
            return country, "explicit_iso_code", country.get("iso2")
        for term, alias, candidate in self._country_terms:
            if _contains(normalised, term):
                return candidate, "explicit_country_alias", alias
        return None, None, None

    def normalise(self, raw: str | None, existing_country: str | None = None) -> LocationMatch:
        raw_text = (raw or "").strip()
        normalised = normalise_unicode(raw_text)
        language = detect_text_language(raw_text)
        country, country_evidence, country_alias = self._explicit_country(raw_text, normalised, existing_country)

        city_matches = [row for row in self._city_terms if _contains(normalised, row[0])]
        if country:
            city_matches = [row for row in city_matches if row[3].get("iso2") == country.get("iso2")]
        city_row = city_matches[0] if city_matches else None

        # A uniquely matched city can identify its country even when the source
        # omits the country, e.g. "Duty station: Lilongwe".
        if city_row and not country:
            countries = {row[3].get("iso2") for row in city_matches if row[0] == city_row[0]}
            if len(countries) == 1:
                country = city_row[3]
                country_evidence = "country_inferred_from_unique_city"
                country_alias = city_row[1]

        admin_matches = [row for row in self._admin_terms if _contains(normalised, row[0])]
        if country:
            admin_matches = [row for row in admin_matches if row[3].get("iso2") == country.get("iso2")]
        admin_row = admin_matches[0] if admin_matches else None
        if admin_row and not country:
            countries = {row[3].get("iso2") for row in admin_matches if row[0] == admin_row[0]}
            if len(countries) == 1:
                country = admin_row[3]
                country_evidence = "country_inferred_from_admin_area"
                country_alias = admin_row[1]

        region = country.get("region") if country else None
        region_match = next(((alias, canonical) for alias, canonical in self._region_terms if _contains(normalised, alias)), None)
        if not region and region_match:
            region = region_match[1]

        evidence: list[str] = []
        if country_evidence:
            evidence.append(country_evidence)
        if city_row:
            evidence.append("explicit_city_alias")
        if admin_row:
            evidence.append("explicit_admin_area")
        if region_match:
            evidence.append("explicit_region_alias")

        if country and city_row and country_evidence in {"existing_country", "existing_iso2", "existing_iso3", "explicit_iso_code", "explicit_country_alias"}:
            confidence = 1.0
        elif city_row and country_evidence == "country_inferred_from_unique_city":
            confidence = 0.96
        elif country and country_evidence in {"existing_country", "existing_iso2", "existing_iso3", "explicit_iso_code", "explicit_country_alias"}:
            confidence = 0.93
        elif admin_row and country:
            confidence = 0.86
        elif region_match:
            confidence = 0.68
        else:
            confidence = 0.0

        city = city_row[2] if city_row else None
        coordinates = city.get("coordinates") if city else None
        return LocationMatch(
            raw=raw_text or None,
            country=country.get("name") if country else None,
            country_code=country.get("iso2") if country else None,
            country_iso3=country.get("iso3") if country else None,
            city=city.get("name") if city else None,
            admin_area=admin_row[2].get("name") if admin_row else None,
            region=region,
            coordinates=coordinates,
            confidence=confidence,
            evidence=tuple(evidence),
            matched_alias=(city_row[1] if city_row else country_alias),
            detected_language=language,
            is_african=bool(country or region_match),
        )


_DEFAULT: AfricanLocationNormalizer | None = None


def default_location_normalizer() -> AfricanLocationNormalizer:
    global _DEFAULT
    if _DEFAULT is None:
        path = Path(__file__).resolve().parents[2] / "config" / "african_locations.json"
        _DEFAULT = AfricanLocationNormalizer.from_path(path)
    return _DEFAULT
