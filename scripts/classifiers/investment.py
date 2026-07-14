"""High-precision investment and DFI role classifier for Phase 6.

The classifier deliberately separates role evidence from institution context:
an accounting or engineering vacancy at a DFI remains an institutional role,
not an investment role. Strong title phrases and canonical specialisations
outweigh body-text mentions, reducing false positives from employer blurbs.
"""
from __future__ import annotations

from dataclasses import dataclass
from html import unescape
import re
import unicodedata
from typing import Any


def normalise(value: Any) -> str:
    text = unicodedata.normalize("NFKD", unescape(str(value or ""))).casefold()
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^\w]+", " ", text, flags=re.UNICODE).strip()


def contains_phrase(text: str, phrase: str) -> bool:
    needle = normalise(phrase)
    if not needle:
        return False
    return bool(re.search(rf"(?<!\w){re.escape(needle)}(?!\w)", text))


@dataclass(frozen=True)
class Classification:
    classification: str
    track: str | None
    canonical_specialisation: str | None
    confidence: float
    evidence: tuple[str, ...]
    negative_evidence: tuple[str, ...]
    dfi_relevance: str
    dfi_confidence: float
    is_investment_role: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "classification": self.classification,
            "track": self.track,
            "canonical_specialisation": self.canonical_specialisation,
            "confidence": round(self.confidence, 2),
            "evidence": list(self.evidence),
            "negative_evidence": list(self.negative_evidence),
            "dfi_relevance": self.dfi_relevance,
            "dfi_confidence": round(self.dfi_confidence, 2),
            "is_investment_role": self.is_investment_role,
        }


class InvestmentClassifier:
    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.tracks = list(config.get("tracks") or [])
        self.track_ids = {row["id"] for row in self.tracks}
        self.classification_values = set(config.get("classification_values") or [])
        self.dfi_values = set(config.get("dfi_relevance_values") or [])
        self.investment_org_types = set(config.get("investment_organisation_types") or [])
        self.dfi_org_types = set(config.get("dfi_organisation_types") or [])
        self.finance_org_types = set(config.get("finance_organisation_types") or [])
        self.hard_negatives = list(config.get("hard_negative_title_phrases") or [])
        self.absolute_negatives = list(config.get("absolute_negative_title_phrases") or [])
        self.support_titles = list(config.get("institutional_support_title_phrases") or [])
        self.generic_titles = list(config.get("generic_investment_title_phrases") or [])
        self.adjacent_specs = set(config.get("adjacent_finance_specialisations") or [])
        self.non_investment_specs = set(config.get("non_investment_finance_specialisations") or [])
        self._track_by_specialisation = {
            row.get("canonical_specialisation"): row for row in self.tracks if row.get("canonical_specialisation")
        }

    @staticmethod
    def _text(opportunity: dict[str, Any]) -> tuple[str, str]:
        title = normalise(opportunity.get("title"))
        body = normalise(" ".join(str(value or "") for value in (
            opportunity.get("summary"),
            opportunity.get("eligibility_notes"),
            " ".join(opportunity.get("skills_required") or []),
            " ".join(opportunity.get("skills_preferred") or []),
        )))
        return title, body

    def _best_track(self, title: str, body: str, specialisations: list[str]) -> tuple[dict[str, Any] | None, float, list[str]]:
        best: tuple[dict[str, Any] | None, float, list[str]] = (None, 0.0, [])
        for track in self.tracks:
            score = 0.0
            evidence: list[str] = []
            canonical = track.get("canonical_specialisation")
            if canonical in specialisations:
                score += 0.82
                evidence.append(f"canonical_specialisation:{canonical}")
            title_hits = [phrase for phrase in track.get("title_phrases", []) if contains_phrase(title, phrase)]
            if title_hits:
                # Prefer the more specific phrase when generic and specialised
                # phrases both match the same title (e.g. "investment officer"
                # versus "financial institutions investment officer").
                most_specific = max(title_hits, key=lambda value: len(normalise(value)))
                score += 0.88 + min(0.12, len(normalise(most_specific)) / 250.0)
                evidence.append(f"title_phrase:{normalise(most_specific).replace(' ', '_')}")
            context_title_hits = [phrase for phrase in track.get("context_phrases", []) if contains_phrase(title, phrase)]
            if context_title_hits:
                score += 0.78
                evidence.append(f"title_context:{normalise(context_title_hits[0]).replace(' ', '_')}")
            body_hits = [phrase for phrase in track.get("context_phrases", []) if contains_phrase(body, phrase)]
            if body_hits:
                score += 0.42
                evidence.append(f"description_context:{normalise(body_hits[0]).replace(' ', '_')}")
            if score > best[1]:
                best = (track, score, evidence)
        return best

    def classify(self, opportunity: dict[str, Any]) -> Classification:
        title, body = self._text(opportunity)
        specialisations = list(opportunity.get("specialisations") or opportunity.get("categories") or [])
        organisation = opportunity.get("organisation") or {}
        org_type = organisation.get("type_detail") or organisation.get("type") or "unverified"
        is_investment_org = org_type in self.investment_org_types
        is_dfi_org = org_type in self.dfi_org_types
        is_finance_org = org_type in self.finance_org_types

        absolute_negative_hits = [phrase for phrase in self.absolute_negatives if contains_phrase(title, phrase)]
        negative_hits = [phrase for phrase in self.hard_negatives if contains_phrase(title, phrase)]
        support_hits = [phrase for phrase in self.support_titles if contains_phrase(title, phrase)]
        generic_title = next((phrase for phrase in self.generic_titles if contains_phrase(title, phrase)), None)
        track, track_score, evidence = self._best_track(title, body, specialisations)

        # Generic investment titles are strong evidence even when a more
        # specialised track cannot be inferred.
        if generic_title and track_score < 0.75:
            track = next(row for row in self.tracks if row["id"] == "investment_analysis")
            track_score = 0.82
            evidence = [f"generic_investment_title:{normalise(generic_title).replace(' ', '_')}"]

        explicit_title_evidence = any(item.startswith(("title_phrase:", "title_context:", "generic_investment_title:")) for item in evidence)
        canonical_evidence = any(item.startswith("canonical_specialisation:") for item in evidence)

        # Accounting/control titles are never investment roles unless their
        # title itself contains strong, track-specific investment evidence.
        if absolute_negative_hits or (negative_hits and not explicit_title_evidence):
            track = None
            track_score = 0.0
            evidence = []

        # Institution type contributes context only after actual role evidence.
        if track and (is_investment_org or is_dfi_org):
            # Specific description evidence becomes usable when the employer is
            # a verified investment/DFI institution, but institution context by
            # itself remains insufficient.
            body_only = not explicit_title_evidence and not canonical_evidence and any(
                item.startswith("description_context:") for item in evidence
            )
            track_score += 0.30 if body_only else 0.08
            evidence.append(f"institution_context:{org_type}")
        elif track and is_finance_org:
            track_score += 0.04
            evidence.append(f"finance_institution_context:{org_type}")

        # A weak body-only mention should not turn an unrelated role into an
        # investment role, especially at an investment institution.
        if track and not explicit_title_evidence and not canonical_evidence and track_score < 0.55:
            track = None
            evidence = []
            track_score = 0.0

        if track and track_score >= 0.7:
            classification = track.get("classification", "core_investment")
            confidence = min(0.98, track_score)
            is_investment_role = True
            canonical = track.get("canonical_specialisation")
            track_id = track.get("id")
        elif is_investment_org or is_dfi_org:
            classification = "institutional_support"
            confidence = 0.88 if (support_hits or negative_hits) else 0.72
            is_investment_role = False
            canonical = None
            track_id = None
            evidence = [f"institution_context:{org_type}"]
            if support_hits:
                evidence.append(f"support_function:{normalise(support_hits[0]).replace(' ', '_')}")
        else:
            classification = "not_investment"
            confidence = 0.92 if negative_hits else 0.78
            is_investment_role = False
            canonical = None
            track_id = None
            evidence = []

        negative_evidence = [f"non_investment_title:{normalise(value).replace(' ', '_')}" for value in [*absolute_negative_hits, *negative_hits]]
        if support_hits and not is_investment_role:
            negative_evidence.append(f"support_function_title:{normalise(support_hits[0]).replace(' ', '_')}")
        if set(specialisations) & self.non_investment_specs and not is_investment_role:
            negative_evidence.append("non_investment_finance_specialisation")

        if is_dfi_org and is_investment_role:
            dfi_relevance, dfi_confidence = "direct_investment", 0.96
        elif is_dfi_org:
            dfi_relevance, dfi_confidence = "institutional_role", 0.9
        elif is_investment_role:
            dfi_relevance, dfi_confidence = "adjacent_experience", 0.76
        else:
            dfi_relevance, dfi_confidence = "none", 0.82

        return Classification(
            classification=classification,
            track=track_id,
            canonical_specialisation=canonical,
            confidence=confidence,
            evidence=tuple(dict.fromkeys(evidence)),
            negative_evidence=tuple(dict.fromkeys(negative_evidence)),
            dfi_relevance=dfi_relevance,
            dfi_confidence=dfi_confidence,
            is_investment_role=is_investment_role,
        )
