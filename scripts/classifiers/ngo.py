"""Conservative NGO, UN and development-programme role classifier.

The classifier deliberately separates employer context from role evidence. A
software engineer at UNICEF is an NGO/UN institutional role, not a humanitarian
programme role. A Monitoring, Evaluation and Learning Adviser at any employer
can still be identified as a development-programme role from title evidence.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()


def _contains(text: str, phrase: str) -> bool:
    phrase_n = _norm(phrase)
    return bool(phrase_n and re.search(rf"\b{re.escape(phrase_n)}\b", text))


@dataclass(frozen=True)
class NGOClassification:
    is_ngo_or_un: bool
    organisation_group: str
    classification: str
    track: str | None
    canonical_specialisation: str | None
    confidence: float
    evidence: tuple[str, ...]
    negative_evidence: tuple[str, ...]
    is_programme_role: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "is_ngo_or_un": self.is_ngo_or_un,
            "organisation_group": self.organisation_group,
            "classification": self.classification,
            "track": self.track,
            "canonical_specialisation": self.canonical_specialisation,
            "confidence": round(min(1.0, max(0.0, float(self.confidence))), 2),
            "evidence": list(self.evidence),
            "negative_evidence": list(self.negative_evidence),
            "is_programme_role": self.is_programme_role,
        }


class NGOClassifier:
    def __init__(self, taxonomy: dict[str, Any]):
        self.taxonomy = taxonomy
        self.tracks = taxonomy.get("tracks", [])
        self.ngo_types = set(taxonomy.get("ngo_or_un_organisation_types", []))
        self.support_phrases = list(taxonomy.get("institutional_support_title_phrases", []))
        self.negative_phrases = list(taxonomy.get("negative_title_phrases", []))

    @staticmethod
    def _organisation_group(organisation_type: str, is_ngo: bool) -> str:
        if not is_ngo:
            return "other"
        return {
            "un_agency": "un_agency",
            "multilateral": "regional_or_multilateral",
            "foundation": "foundation",
            "consulting_firm": "development_implementer",
            "ngo": "ngo",
        }.get(organisation_type, "ngo_or_development")

    def classify(self, opportunity: dict[str, Any]) -> NGOClassification:
        organisation = opportunity.get("organisation") or {}
        organisation_type = str(organisation.get("type_detail") or organisation.get("type") or "unverified")
        is_ngo = organisation_type in self.ngo_types
        group = self._organisation_group(organisation_type, is_ngo)
        title = _norm(opportunity.get("title"))
        context = _norm(" ".join(str(value or "") for value in (
            opportunity.get("title"), opportunity.get("summary"),
            opportunity.get("role_subfamily"), opportunity.get("industry"),
        )))
        specialisations = set(opportunity.get("specialisations") or opportunity.get("categories") or [])

        negative = tuple(
            f"title_phrase:{_norm(phrase).replace(' ', '_')}"
            for phrase in self.negative_phrases if _contains(title, phrase)
        )
        support = tuple(
            f"support_title:{_norm(phrase).replace(' ', '_')}"
            for phrase in self.support_phrases if _contains(title, phrase)
        )

        best: tuple[float, dict[str, Any], list[str]] | None = None
        for track in self.tracks:
            score = 0.0
            evidence: list[str] = []
            canonical = track.get("canonical_specialisation")
            if canonical and canonical in specialisations:
                score += 0.82
                evidence.append(f"canonical_specialisation:{canonical}")
            for phrase in track.get("title_phrases", []):
                if _contains(title, phrase):
                    score = max(score, 0.96)
                    evidence.append(f"title_phrase:{_norm(phrase).replace(' ', '_')}")
                    break
            if score < 0.9:
                for phrase in track.get("context_phrases", []):
                    if _contains(context, phrase):
                        score += 0.24
                        evidence.append(f"context_phrase:{_norm(phrase).replace(' ', '_')}")
                        break
            if best is None or score > best[0]:
                best = (score, track, evidence)

        score, track, evidence = best or (0.0, {}, [])
        # Employer context can strengthen a role already evidenced, but never
        # turns a support role into a programme role by itself.
        if is_ngo and score >= 0.45:
            score = min(0.99, score + 0.05)
            evidence.append("ngo_or_un_institution")

        if negative and score < 0.9:
            score = max(0.0, score - 0.45)
        if support and score < 0.9:
            score = max(0.0, score - 0.35)

        # Multiple independent signals may add above 1.0. Confidence is a
        # probability-like schema field, so clamp before publication.
        score = min(0.99, max(0.0, score))

        if score >= 0.75 and track:
            classification = str(track.get("classification") or "technical_programme")
            return NGOClassification(
                is_ngo, group, classification, str(track.get("id")),
                str(track.get("canonical_specialisation")), score,
                tuple(dict.fromkeys(evidence)), tuple(dict.fromkeys((*negative, *support))), True,
            )

        if is_ngo:
            return NGOClassification(
                True, group, "institutional_support", None, None,
                0.82 if (negative or support) else 0.68,
                ("ngo_or_un_institution",), tuple(dict.fromkeys((*negative, *support))), False,
            )
        return NGOClassification(
            False, group, "not_ngo_un", None, None, 0.95,
            (), tuple(dict.fromkeys((*negative, *support))), False,
        )
