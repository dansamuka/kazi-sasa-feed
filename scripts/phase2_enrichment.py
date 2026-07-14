"""Backward-compatible Phase 2 schema enrichment.

The current Android app ignores unknown JSON keys, so Phase 2 adds richer
organisation, role, location, source and eligibility metadata without removing
or renaming any field consumed by the existing DTOs.
"""
from __future__ import annotations

import re
import unicodedata
from copy import deepcopy
from typing import Any
from urllib.parse import urlparse

from normalizers.location import AfricanLocationNormalizer, detect_text_language
from normalizers.multilingual import extract_eligibility_signals_multilingual
from classifiers.investment import InvestmentClassifier
from classifiers.ngo import NGOClassifier
from classifiers.africa_access import AfricaAccessClassifier, legacy_eligibility_from_access

VALID_ELIGIBILITY_STATUSES = {
    "eligible",
    "likely_eligible",
    "uncertain",
    "local_only",
    "citizenship_restricted",
    "internal_only",
    "ineligible",
}


def _normalise_text(value: str | None) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", _normalise_text(value)).strip("-")


class Phase2Enricher:
    """Enrich opportunities while preserving every legacy field."""

    def __init__(
        self,
        organisations: dict[str, Any] | None = None,
        locations: dict[str, Any] | None = None,
        roles: dict[str, Any] | None = None,
        sources: dict[str, Any] | None = None,
        investment_taxonomy: dict[str, Any] | None = None,
        ngo_taxonomy: dict[str, Any] | None = None,
        global_countries: dict[str, Any] | None = None,
    ):
        self.organisations = organisations or {"organisations": []}
        self.locations = locations or {"countries": []}
        self.roles = roles or {"role_families": []}
        self.sources = sources or {"sources": []}
        self.investment_taxonomy = investment_taxonomy or {}
        self.ngo_taxonomy = ngo_taxonomy or {}
        self.global_countries = global_countries or {"countries": []}
        self._investment_classifier = InvestmentClassifier(self.investment_taxonomy) if self.investment_taxonomy else None
        self._ngo_classifier = NGOClassifier(self.ngo_taxonomy) if self.ngo_taxonomy else None
        self._africa_access_classifier = AfricaAccessClassifier(self.locations, self.global_countries) if self.global_countries.get("countries") else None
        self._location_normalizer = AfricanLocationNormalizer(self.locations)

        self._organisations_by_name: dict[str, dict[str, Any]] = {}
        for organisation in self.organisations.get("organisations", []):
            for name in [organisation.get("name"), *organisation.get("aliases", [])]:
                key = _normalise_text(name)
                if key:
                    self._organisations_by_name[key] = organisation

        self._countries: list[tuple[str, dict[str, Any]]] = []
        self._cities: list[tuple[str, str, dict[str, Any]]] = []
        for country in self.locations.get("countries", []):
            names = {
                country.get("name"), country.get("iso2"), country.get("iso3"),
                *country.get("aliases", []),
            }
            for name in names:
                key = _normalise_text(name)
                if key:
                    self._countries.append((key, country))
            for city in country.get("cities", []):
                for name in {city.get("name"), *city.get("aliases", [])}:
                    key = _normalise_text(name)
                    if key:
                        self._cities.append((key, city.get("name"), country))
        self._countries.sort(key=lambda item: len(item[0]), reverse=True)
        self._cities.sort(key=lambda item: len(item[0]), reverse=True)

        self._role_family_ids = {row["id"] for row in self.roles.get("role_families", [])}
        self._specialisation_role_map = self.roles.get("specialisation_role_family_map", {})
        self._industry_role_map = self.roles.get("industry_role_family_map", {})
        self._thematic_map = self.roles.get("thematic_sector_map", {})

        self._sources_by_name = {
            _normalise_text(row.get("name")): row
            for row in self.sources.get("sources", [])
            if row.get("name")
        }
        self._sources_by_domain = {
            row.get("domain", "").lower(): row
            for row in self.sources.get("sources", [])
            if row.get("domain")
        }

    def enrich(self, opportunity: dict[str, Any]) -> dict[str, Any]:
        opp = deepcopy(opportunity)
        self._enrich_organisation(opp)
        self._enrich_location(opp)
        self._enrich_role(opp)
        self._enrich_ngo(opp)
        self._enrich_government(opp)
        self._enrich_public_institution(opp)
        self._enrich_multinational(opp)
        self._enrich_africa_access(opp)
        self._enrich_eligibility(opp)
        self._enrich_source(opp)
        return opp

    def _match_organisation(self, name: str | None) -> dict[str, Any] | None:
        key = _normalise_text(name)
        if not key:
            return None
        exact = self._organisations_by_name.get(key)
        if exact:
            return exact
        # Conservative suffix cleanup for common ATS presentation variants.
        for suffix in (" careers", " jobs", " plc", " limited", " ltd"):
            if key.endswith(suffix):
                match = self._organisations_by_name.get(key[: -len(suffix)].strip())
                if match:
                    return match
        return None

    def _enrich_organisation(self, opp: dict[str, Any]) -> None:
        organisation = opp.setdefault("organisation", {})
        matched = self._match_organisation(organisation.get("name"))
        if matched:
            organisation["id"] = matched["id"]
            organisation["verified"] = bool(
                organisation.get("verified")
                or any(source.get("verified") for source in matched.get("sources", []))
            )
            organisation["type_detail"] = matched.get("organisation_type")
            organisation["registry_managed"] = True
        else:
            organisation.setdefault("id", None)
            organisation.setdefault("verified", False)
            organisation.setdefault("type_detail", organisation.get("type", "unverified"))
            organisation["registry_managed"] = False

        institution_type = organisation.get("type_detail") or organisation.get("type") or "unverified"
        is_dfi = institution_type in {
            "dfi", "development_bank", "multilateral", "investment_firm",
            "asset_manager", "private_equity", "venture_capital",
        }
        organisation_id = organisation.get("id")
        matched_pack = matched.get("source_pack") if matched else None
        opp["institution_profile"] = {
            "is_dfi_or_multilateral": bool(is_dfi),
            "institution_type": institution_type,
            "registry_id": organisation_id,
            "source_pack": matched_pack,
            "phase7_priority_institution": matched_pack == "phase7_dfi_multilateral",
        }

    def _enrich_ngo(self, opp: dict[str, Any]) -> None:
        organisation = opp.get("organisation") or {}
        matched = self._match_organisation(organisation.get("name"))
        source_pack = matched.get("source_pack") if matched else None
        registry_id = organisation.get("id")
        if self._ngo_classifier:
            profile = self._ngo_classifier.classify(opp).as_dict()
        else:
            is_ngo = (organisation.get("type_detail") or organisation.get("type")) in {"ngo", "un_agency", "foundation", "consulting_firm"}
            profile = {
                "is_ngo_or_un": bool(is_ngo), "organisation_group": "ngo_or_development" if is_ngo else "other",
                "classification": "institutional_support" if is_ngo else "not_ngo_un",
                "track": None, "canonical_specialisation": None, "confidence": 0.5,
                "evidence": [], "negative_evidence": [], "is_programme_role": False,
            }
        profile.update({
            "registry_id": registry_id,
            "source_pack": source_pack,
            "phase8_priority_organisation": source_pack == "phase8_ngo_un_development",
        })
        opp["ngo_profile"] = profile


    def _enrich_government(self, opp: dict[str, Any]) -> None:
        organisation = opp.get("organisation") or {}
        matched = self._match_organisation(organisation.get("name"))
        source_pack = matched.get("source_pack") if matched else None
        institution_type = organisation.get("type_detail") or organisation.get("type") or "unverified"
        fields = opp.get("government_fields") or {}
        existing_profile = opp.get("government_profile") or {}
        is_government = institution_type in {"government", "regulator", "state_owned_enterprise", "university"} or source_pack in {"phase9_government_wave1", "phase10_kenya_public_institutions"} or bool(existing_profile.get("is_government_or_public_service"))
        opp["government_profile"] = {
            "is_government_or_public_service": bool(is_government),
            "institution_type": institution_type,
            "registry_id": organisation.get("id"),
            "source_pack": source_pack,
            "phase9_priority_portal": source_pack == "phase9_government_wave1",
            "phase10_kenya_public_institution": source_pack == "phase10_kenya_public_institutions",
            "public_institution_category": matched.get("public_institution_category") if matched else None,
            "advert_reference": fields.get("advert_reference", existing_profile.get("advert_reference")),
            "public_service_grade": fields.get("public_service_grade", existing_profile.get("public_service_grade")),
            "salary_scale": fields.get("salary_scale", existing_profile.get("salary_scale")),
            "number_of_positions": fields.get("number_of_positions", existing_profile.get("number_of_positions")),
            "citizenship_required": fields.get("citizenship_required", existing_profile.get("citizenship_required")),
            "eligible_nationalities": fields.get("eligible_nationalities") or existing_profile.get("eligible_nationalities") or [],
            "application_method": fields.get("application_method", existing_profile.get("application_method")),
            "application_form_url": fields.get("application_form_url", existing_profile.get("application_form_url")),
            "internal_only": bool(fields.get("internal_only", existing_profile.get("internal_only", False))),
            "county_or_region_requirement": fields.get("county_or_region_requirement", existing_profile.get("county_or_region_requirement")),
            "source_document_url": fields.get("source_document_url", existing_profile.get("source_document_url")),
        }


    def _enrich_public_institution(self, opp: dict[str, Any]) -> None:
        organisation = opp.get("organisation") or {}
        matched = self._match_organisation(organisation.get("name"))
        source_pack = matched.get("source_pack") if matched else None
        opp["public_institution_profile"] = {
            "is_kenya_public_institution": source_pack == "phase10_kenya_public_institutions",
            "category": matched.get("public_institution_category") if matched else None,
            "registry_id": organisation.get("id"),
            "source_pack": source_pack,
            "country_code": "KE" if source_pack == "phase10_kenya_public_institutions" else None,
        }

    def _enrich_multinational(self, opp: dict[str, Any]) -> None:
        organisation = opp.get("organisation") or {}
        matched = self._match_organisation(organisation.get("name"))
        source_pack = matched.get("source_pack") if matched else None
        is_multinational = (organisation.get("type_detail") or organisation.get("type")) == "multinational" or source_pack == "phase11_multinationals"
        opp["multinational_profile"] = {
            "is_multinational": bool(is_multinational),
            "sector": matched.get("multinational_sector") if matched else None,
            "registry_id": organisation.get("id"),
            "source_pack": source_pack,
            "phase11_priority_employer": bool(matched and matched.get("phase11_priority_employer")),
            "african_city_footprint": list(matched.get("african_city_footprint") or []) if matched else [],
        }

    def _find_country(self, location: dict[str, Any], raw_normalised: str) -> dict[str, Any] | None:
        existing = _normalise_text(location.get("country"))
        for term, country in self._countries:
            if existing == term or (term and re.search(rf"\b{re.escape(term)}\b", raw_normalised)):
                return country
        return None

    def _find_city(self, raw_normalised: str, country: dict[str, Any] | None) -> str | None:
        for term, city_name, city_country in self._cities:
            if country and city_country.get("iso2") != country.get("iso2"):
                continue
            if re.search(rf"\b{re.escape(term)}\b", raw_normalised):
                return city_name
        return None

    def _enrich_location(self, opp: dict[str, Any]) -> None:
        location = opp.setdefault("location", {})
        raw = location.get("raw") or ""
        match = self._location_normalizer.normalise(raw, existing_country=location.get("country"))

        location["city"] = match.city
        location["country_code"] = match.country_code
        location["country_iso3"] = match.country_iso3
        location["admin_area"] = match.admin_area
        location["coordinates"] = match.coordinates
        location["country_canonical"] = match.country or location.get("country")
        location["region_canonical"] = match.region or location.get("region")
        location["normalisation_confidence"] = match.confidence
        location["normalisation_evidence"] = list(match.evidence)
        location["matched_location_alias"] = match.matched_alias
        location["location_language"] = match.detected_language
        location["is_african"] = match.is_african

        # Phase 12 recognises non-African ISO codes/names as well. This prevents
        # locations such as ``Tashkent, UZ`` from being misclassified as an
        # official vacancy with an unknown duty station.
        if self._africa_access_classifier and not match.country_code:
            global_match = self._africa_access_classifier.detect_global_country(
                raw, location.get("country_code") or location.get("country_iso3"), location.get("country")
            )
            if global_match:
                location["country_code"] = global_match.get("iso2")
                location["country_iso3"] = global_match.get("iso3")
                location["country_canonical"] = global_match.get("name")
                location["region_canonical"] = "Non-Africa" if not global_match.get("is_african") else location.get("region_canonical")
                location["is_african"] = bool(global_match.get("is_african"))
                location["known_non_african"] = not bool(global_match.get("is_african"))
                location["global_location_evidence"] = ["global_country_registry_match"]
                location["normalisation_confidence"] = max(float(location.get("normalisation_confidence") or 0), 0.96)
            else:
                location["known_non_african"] = False
                location["global_location_evidence"] = []
        else:
            location["known_non_african"] = False
            location["global_location_evidence"] = []

        # Explicitly preserve the six legacy location keys. Phase 4 adds richer
        # metadata but never rewrites what the current Android DTO consumes.
        location.setdefault("raw", raw or None)
        location.setdefault("country", None)
        location.setdefault("region", None)
        location.setdefault("is_remote_from_kenya", False)
        location.setdefault("scope", None)
        location.setdefault("relocation_country", None)

    def _enrich_role(self, opp: dict[str, Any]) -> None:
        specialisations = opp.get("specialisations") or opp.get("categories") or []
        role_subfamily = specialisations[0] if specialisations else None
        role_family = None
        if role_subfamily:
            role_family = self._specialisation_role_map.get(role_subfamily)
        if not role_family:
            role_family = self._industry_role_map.get(opp.get("industry"))
        if role_family not in self._role_family_ids:
            role_family = None

        opp["role_family"] = role_family
        opp["role_subfamily"] = role_subfamily

        themes: list[str] = []
        for key in [opp.get("industry"), *specialisations]:
            for theme in self._thematic_map.get(key, []):
                if theme not in themes:
                    themes.append(theme)
        opp["thematic_sectors"] = themes

        if self._investment_classifier:
            classification = self._investment_classifier.classify(opp)
            profile = classification.as_dict()
            opp["investment_profile"] = profile
            if classification.is_investment_role:
                opp["role_family"] = "investment"
                if classification.canonical_specialisation:
                    opp["role_subfamily"] = classification.canonical_specialisation
                    for theme in self._thematic_map.get(classification.canonical_specialisation, []):
                        if theme not in opp["thematic_sectors"]:
                            opp["thematic_sectors"].append(theme)

    @staticmethod
    def _eligibility_text(opp: dict[str, Any]) -> str:
        return " ".join(
            str(value or "")
            for value in (
                opp.get("title"), opp.get("summary"), opp.get("eligibility_notes"),
                (opp.get("location") or {}).get("raw"),
            )
        )

    def _enrich_africa_access(self, opp: dict[str, Any]) -> None:
        if not self._africa_access_classifier:
            opp.setdefault("africa_relevance", {
                "status": "unresolved", "confidence": 0.0, "evidence": ["classifier_not_configured"],
                "certification_level": "unverified", "default_visible": False,
                "known_country_code": None, "known_country_name": None,
            })
            opp.setdefault("african_applicant_access", {
                "status": "unknown", "confidence": 0.0, "evidence": ["classifier_not_configured"],
                "evidence_strength": "none", "eligible_nationalities": [],
                "citizenship_required": None, "work_authorisation_required": None,
                "certification_level": "unverified",
            })
            return
        relevance, access = self._africa_access_classifier.classify(opp)
        opp["africa_relevance"] = relevance.as_dict()
        opp["african_applicant_access"] = access.as_dict()

    def _enrich_eligibility(self, opp: dict[str, Any]) -> None:
        if self._africa_access_classifier and opp.get("african_applicant_access"):
            access = self._africa_access_classifier.classify_access(
                opp, self._africa_access_classifier.classify_relevance(opp)
            )
            legacy = legacy_eligibility_from_access(access)
            legacy["detected_language"] = detect_text_language(self._eligibility_text(opp))
            opp["eligibility"] = legacy
            return
        location = opp.get("location") or {}
        text = self._eligibility_text(opp)
        normalised = _normalise_text(text)
        evidence: list[str] = []
        eligible_nationalities: list[str] = []
        citizenship_required: bool | None = None
        work_authorisation_required: bool | None = None

        multilingual = extract_eligibility_signals_multilingual(text)
        internal = multilingual["internal_only"] or bool(re.search(r"\b(internal candidates? only|internal applicants? only|staff only)\b", normalised))
        local_only = multilingual["local_only"] or bool(re.search(r"\b(local candidates? only|nationals? only|national position|local hire)\b", normalised))
        citizenship = multilingual["citizenship"] or bool(re.search(r"\b(must be|only) (?:a |an )?[a-z ]+ (?:citizen|national)\b", normalised))
        work_auth = multilingual["work_auth"] or bool(re.search(r"\b(must have|require[sd]?) (?:existing |valid )?(?:work authori[sz]ation|right to work|work permit)\b", normalised))

        if internal:
            status, confidence = "internal_only", 0.98
            evidence.append("internal_candidate_only")
        elif citizenship or local_only:
            citizenship_required = citizenship or None
            status, confidence = "citizenship_restricted" if citizenship else "local_only", 0.9
            evidence.append("citizenship_or_local_recruitment_restriction")
        elif work_auth:
            work_authorisation_required = True
            status, confidence = "uncertain", 0.82
            evidence.append("existing_work_authorisation_required")
        elif multilingual["international"]:
            status, confidence = "likely_eligible", 0.9
            evidence.append("international_applicants_explicitly_welcome")
        elif location.get("is_remote_from_kenya"):
            mode = opp.get("work_mode")
            if mode == "remote_kenya":
                status, confidence = "likely_eligible", 0.92
                evidence.append("remote_from_kenya")
            elif mode == "remote_regional" or "emea" in normalised or "africa" in normalised:
                status, confidence = "likely_eligible", 0.82
                evidence.append("remote_regional_or_africa")
            else:
                status, confidence = "likely_eligible", 0.78
                evidence.append("remote_global_or_worldwide")
        elif location.get("country_code") == "KE":
            status, confidence = "likely_eligible", 0.86
            evidence.append("duty_station_in_kenya")
        elif location.get("country_code"):
            status, confidence = "uncertain", 0.62
            evidence.extend(["duty_station_in_africa", "work_authorisation_unknown"])
        else:
            status, confidence = "uncertain", 0.35
            evidence.append("insufficient_eligibility_evidence")

        opp["eligibility"] = {
            "status": status,
            "confidence": confidence,
            "citizenship_required": citizenship_required,
            "eligible_nationalities": eligible_nationalities,
            "work_authorisation_required": work_authorisation_required,
            "evidence": evidence,
            "detected_language": multilingual.get("detected_language") or detect_text_language(text),
        }

    def _source_match(self, source: dict[str, Any]) -> dict[str, Any] | None:
        url = source.get("url") or ""
        host = (urlparse(url).hostname or "").lower()
        for domain, row in self._sources_by_domain.items():
            if host == domain or host.endswith("." + domain):
                return row
        name = _normalise_text(source.get("name"))
        if name in self._sources_by_name:
            return self._sources_by_name[name]
        # Employer-specific ATS source names are organisation names, not the
        # generic registry label, so infer the platform from the host.
        platform_domains = {
            "greenhouse.io": "greenhouse-hosted-employer-board",
            "lever.co": "lever-hosted-employer-board",
            "ashbyhq.com": "ashby-hosted-employer-board",
            "pinpointhq.com": "pinpoint-hosted-employer-board",
        }
        for domain, source_id in platform_domains.items():
            if host == domain or host.endswith("." + domain):
                return next((r for r in self.sources.get("sources", []) if r.get("id") == source_id), None)
        return None

    def _enrich_source(self, opp: dict[str, Any]) -> None:
        source = opp.setdefault("source", {})
        matched = self._source_match(source)
        if matched:
            source["id"] = matched.get("id")
            source["kind"] = matched.get("source_kind")
            source["registry_managed"] = True
        else:
            source.setdefault("id", None)
            confidence = source.get("confidence", "unverified")
            source.setdefault("kind", {
                "official": "direct_or_official",
                "aggregated": "aggregator",
                "community": "community",
            }.get(confidence, "unverified"))
            source["registry_managed"] = False


def legacy_projection(opportunity: dict[str, Any]) -> dict[str, Any]:
    """Project only fields consumed by the current Android DTOs.

    Used by migration tests to prove that Phase 2 is additive and does not
    alter the current app's parsed data.
    """
    top_fields = [
        "id", "title", "opportunity_type", "work_mode", "seniority", "categories",
        "skills_required", "skills_preferred", "posted_at", "deadline",
        "deadline_confidence", "compensation", "apply_url", "apply_is_official",
        "flags", "eligibility_notes", "summary", "raw_description_url", "industry",
        "specialisations", "years_experience_min", "years_experience_max",
        "education_required", "education_field", "languages_required", "contract_type",
    ]
    result = {key: opportunity.get(key) for key in top_fields if key in opportunity}
    result["organisation"] = {
        key: (opportunity.get("organisation") or {}).get(key)
        for key in ("name", "type", "verified")
        if key in (opportunity.get("organisation") or {})
    }
    result["location"] = {
        key: (opportunity.get("location") or {}).get(key)
        for key in ("raw", "country", "region", "is_remote_from_kenya", "scope", "relocation_country")
        if key in (opportunity.get("location") or {})
    }
    result["source"] = {
        key: (opportunity.get("source") or {}).get(key)
        for key in ("name", "url", "confidence", "last_seen_at")
        if key in (opportunity.get("source") or {})
    }
    return result
