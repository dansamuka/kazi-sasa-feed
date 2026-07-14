"""Phase 4 multilingual location and extraction regression tests."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
REPO = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

from collectors._common import (  # noqa: E402
    extract_contract_type,
    extract_deadline,
    extract_languages_required,
    extract_years_experience,
    infer_work_mode,
    parse_location,
)
from normalizers.location import AfricanLocationNormalizer, detect_text_language, normalise_unicode  # noqa: E402
from normalizers.multilingual import extract_eligibility_signals_multilingual  # noqa: E402
from phase2_enrichment import legacy_projection  # noqa: E402
from verify_published_output import verify_feed  # noqa: E402


def _load(path: str) -> dict:
    return json.loads((REPO / path).read_text(encoding="utf-8"))


def _normalizer() -> AfricanLocationNormalizer:
    return AfricanLocationNormalizer(_load("config/african_locations.json"))


def test_phase4_location_registry_is_continent_wide_and_multilingual():
    registry = _load("config/african_locations.json")
    assert registry["registry_version"] == "2.0"
    assert set(registry["supported_languages"]) == {"en", "fr", "pt", "ar", "sw"}
    assert len(registry["countries"]) == 54
    assert sum(len(country["cities"]) for country in registry["countries"]) >= 150
    assert sum(len(country.get("admin_areas", [])) for country in registry["countries"]) >= 60
    assert sum("coordinates" in city for country in registry["countries"] for city in country["cities"]) >= 100


def test_unicode_normalisation_preserves_arabic_letters():
    value = normalise_unicode("مكان العمل: القاهرة، مصر")
    assert "القاهرة" in value and "مصر" in value


def test_location_regression_corpus_has_at_least_500_realistic_cases():
    corpus = _load("config/location_test_cases.json")
    assert corpus["case_count"] == len(corpus["cases"])
    assert len(corpus["cases"]) >= 500


def test_every_location_regression_case_matches_expected_country_city_admin_or_region():
    normalizer = _normalizer()
    failures = []
    for case in _load("config/location_test_cases.json")["cases"]:
        match = normalizer.normalise(case["raw"])
        for field in ("country_code", "city", "admin_area", "region"):
            expected = case.get(field)
            if expected is not None and getattr(match, field) != expected:
                failures.append((case["raw"], field, expected, getattr(match, field)))
    assert failures == []


@pytest.mark.parametrize(
    ("raw", "country_code", "city", "language"),
    [
        ("Lieu d’affectation : Abidjan, Côte d’Ivoire", "CI", "Abidjan", "fr"),
        ("Localização: Maputo, Moçambique", "MZ", "Maputo", "pt"),
        ("مكان العمل: القاهرة، مصر", "EG", "Cairo", "ar"),
        ("Mahali pa kazi: Jiji la Dar es Salaam, Tanzania", "TZ", "Dar es Salaam", "sw"),
        ("Duty station: Lilongwe", "MW", "Lilongwe", "en"),
    ],
)
def test_multilingual_location_examples(raw, country_code, city, language):
    match = _normalizer().normalise(raw)
    assert match.country_code == country_code
    assert match.city == city
    assert match.detected_language == language
    assert match.confidence >= 0.93


def test_region_only_location_is_not_fabricated_into_a_country():
    match = _normalizer().normalise("Remote — Afrique de l’Ouest")
    assert match.country_code is None
    assert match.region == "West Africa"
    assert match.confidence == 0.68


def test_unrelated_non_african_location_is_not_guessed_as_african():
    match = _normalizer().normalise("Boston, Massachusetts")
    assert match.country_code is None
    assert match.city is None
    assert match.is_african is False


def test_parse_location_exposes_phase4_evidence_fields():
    location = parse_location("Cape Town City Centre, South Africa")
    assert location["country_code"] == "ZA"
    assert location["city"] == "Cape Town"
    assert location["normalisation_confidence"] == 1.0
    assert "explicit_city_alias" in location["normalisation_evidence"]
    assert location["is_african"] is True


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Minimum 5 years of experience", (5, None)),
        ("Au moins 5 ans d’expérience", (5, None)),
        ("Mínimo de 5 anos de experiência", (5, None)),
        ("خبرة لا تقل عن 5 سنوات", (5, None)),
        ("Angalau miaka 5 ya uzoefu", (5, None)),
    ],
)
def test_multilingual_years_experience(text, expected):
    assert extract_years_experience(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Full-time role", "permanent"),
        ("Contrat à durée déterminée", "fixed_term"),
        ("Contrato a termo", "fixed_term"),
        ("عقد محدد المدة", "fixed_term"),
        ("Mkataba wa muda maalum", "fixed_term"),
    ],
)
def test_multilingual_contract_types(text, expected):
    assert extract_contract_type(None, text) == expected


@pytest.mark.parametrize(
    ("text", "language"),
    [
        ("Closing date: 31 July 2026", "en"),
        ("Date limite: 31 juillet 2026", "fr"),
        ("Prazo: 31 julho 2026", "pt"),
        ("آخر موعد: 31/07/2026", "ar"),
        ("Mwisho wa kutuma: 31 Julai 2026", "sw"),
    ],
)
def test_multilingual_deadlines(text, language):
    deadline, confidence = extract_deadline(text)
    assert deadline == "2026-07-31T23:59:59Z"
    assert confidence == "explicit"
    assert detect_text_language(text) == language


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Fluent in French required", ["french"]),
        ("Maîtrise de l’anglais obligatoire", ["english"]),
        ("Domínio do português obrigatório", ["portuguese"]),
        ("إجادة اللغة العربية مطلوبة", ["arabic"]),
        ("Ufasaha wa Kiswahili unahitajika", ["swahili"]),
    ],
)
def test_multilingual_language_requirements(text, expected):
    assert extract_languages_required(text) == expected


@pytest.mark.parametrize(
    ("text", "signal", "language"),
    [
        ("Internal candidates only", "internal_only", "en"),
        ("Candidats locaux seulement", "local_only", "fr"),
        ("Apenas nacionais", "local_only", "pt"),
        ("للمواطنين فقط", "local_only", "ar"),
        ("Lazima awe raia wa Kenya", "citizenship", "sw"),
    ],
)
def test_multilingual_eligibility_restrictions(text, signal, language):
    result = extract_eligibility_signals_multilingual(text)
    assert result[signal] is True
    assert result["detected_language"] == language


@pytest.mark.parametrize(
    "text",
    ["Remote — Africa", "Télétravail — Afrique", "Remoto — África", "عن بعد — أفريقيا", "Mbali — Afrika Mashariki"],
)
def test_multilingual_remote_work_mode(text):
    assert infer_work_mode(text) == "remote_regional"


def test_all_packaged_records_have_phase4_fields_and_version():
    for filename in ("feed.json", "seed.json"):
        feed = _load(filename)
        assert feed["meta"]["feed_version"] == "3.8"
        assert set(feed["meta"]["supported_languages"]) == {"en", "fr", "pt", "ar", "sw"}
        assert feed["meta"]["location_registry_version"] == "2.0"
        for opportunity in feed["opportunities"]:
            assert {
                "country_iso3", "admin_area", "coordinates", "normalisation_evidence",
                "matched_location_alias", "location_language", "is_african",
            } <= set(opportunity["location"])
            assert "detected_language" in opportunity["eligibility"]


def test_phase4_migration_preserves_android_dto_projection():
    expected = {
        "scripts/tests/fixtures/legacy_packaged_feed.json": "9091a81b364025ea9d61c9b961231bdd6187fc0d025532297da761469419637c",
        "seed.json": "5d881af69edd21e0e983dddc0b2ed0f5c4ba958130baac7536fbb97d99cd75fe",
    }
    for filename, digest in expected.items():
        payload = json.dumps(
            [legacy_projection(row) for row in _load(filename)["opportunities"]],
            sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        )
        assert hashlib.sha256(payload.encode()).hexdigest() == digest


def test_phase4_publication_guard_passes_packaged_feed():
    assert verify_feed(
        _load("feed.json"), "3.8", require_phase2=True,
        max_age_minutes=None, require_phase4=True,
    ) == []


def test_workflow_requires_phase4_publication_fields():
    workflow = (REPO / ".github/workflows/refresh-feed.yml").read_text(encoding="utf-8")
    assert workflow.count("--require-phase4") == 2
    assert "Validate Phase 1-12 registries and schema" in workflow


def test_all_description_collectors_attempt_multilingual_deadline_extraction():
    collectors = [
        "greenhouse.py", "lever.py", "ashby.py", "pinpoint.py", "adzuna.py",
        "himalayas.py", "remotive.py", "jobicy.py", "remoteok.py", "arbeitnow.py",
    ]
    for filename in collectors:
        source = (REPO / "scripts" / "collectors" / filename).read_text(encoding="utf-8")
        assert "extract_deadline" in source
        assert '"deadline": deadline' in source
