from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
REPO = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

from bs4 import XMLParsedAsHTMLWarning
from classifiers.ngo import NGOClassifier
from collectors.official_common import jsonld_job_postings
from refresh_feed import FeedBuilder


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_ngo_confidence_is_clamped_when_canonical_and_context_scores_stack():
    taxonomy = {
        "ngo_or_un_organisation_types": [],
        "institutional_support_title_phrases": [],
        "negative_title_phrases": [],
        "tracks": [{
            "id": "programme_management",
            "classification": "development",
            "canonical_specialisation": "programme_management",
            "title_phrases": [],
            "context_phrases": ["programme delivery"],
        }],
    }
    result = NGOClassifier(taxonomy).classify({
        "title": "Programme Delivery Officer",
        "summary": "Leads programme delivery across the department.",
        "organisation": {"type_detail": "government"},
        "specialisations": ["programme_management"],
    }).as_dict()
    assert result["classification"] == "development"
    assert 0 <= result["confidence"] <= 1
    assert result["confidence"] == 0.99


def test_all_reviewed_ngo_cases_publish_schema_safe_confidence():
    classifier = NGOClassifier(load(REPO / "config/ngo_taxonomy.json"))
    for case in load(REPO / "config/ngo_test_cases.json")["cases"]:
        profile = classifier.classify({
            "title": case["title"],
            "organisation": {"type_detail": case["organisation_type"]},
            "specialisations": case.get("specialisations", []),
        }).as_dict()
        assert 0 <= profile["confidence"] <= 1, case


def test_xml_shaped_official_payload_does_not_emit_parser_warning():
    xml = '<?xml version="1.0"?><feed><entry><title>Programme Officer</title></entry></feed>'
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert jsonld_job_postings(xml) == []
    assert not any(issubclass(w.category, XMLParsedAsHTMLWarning) for w in caught)


def test_unmapped_taxonomy_warning_is_emitted_once(capsys):
    builder = FeedBuilder(load(REPO / "taxonomy.json"), load(REPO / "config/source_registry.json"))
    assert builder.map_specialisation("Never Seen Label", source_key="himalayas") is None
    assert builder.map_specialisation("Never Seen Label", source_key="himalayas") is None
    assert builder.map_industry("Never Seen Industry") is None
    assert builder.map_industry("Never Seen Industry") is None
    stderr = capsys.readouterr().err
    assert stderr.count("Never Seen Label") == 1
    assert stderr.count("Never Seen Industry") == 1
