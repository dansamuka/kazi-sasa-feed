"""Phase 2 additive schema, enrichment and compatibility tests."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
REPO = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

from phase2_enrichment import Phase2Enricher, legacy_projection  # noqa: E402
from refresh_feed import FEED_VERSION, FeedBuilder  # noqa: E402
from validate_feed import validate_feed  # noqa: E402


def _load(path: str) -> dict:
    return json.loads((REPO / path).read_text(encoding="utf-8"))


def _enricher() -> Phase2Enricher:
    return Phase2Enricher(
        _load("config/organisations.json"),
        _load("config/african_locations.json"),
        _load("config/role_taxonomy.json"),
        _load("config/source_registry.json"),
    )


def _minimal_old_opportunity() -> dict:
    return {
        "id": "legacy-1",
        "title": "Legacy role",
        "opportunity_type": "job",
        "organisation": {"name": "Legacy Employer", "type": "employer", "verified": False},
        "location": {
            "raw": "Nairobi, Kenya", "country": "Kenya", "region": None,
            "is_remote_from_kenya": False, "scope": "national", "relocation_country": None,
        },
        "source": {
            "name": "Employer career page", "url": "https://example.org/careers/1",
            "confidence": "official",
        },
        "apply_url": "https://example.org/careers/1",
        "flags": [],
        "deadline_confidence": "unknown",
    }


def test_phase2_uses_additive_feed_version():
    assert FEED_VERSION == "3.8"
    assert _load("feed.json")["meta"]["feed_version"] == "3.8"
    assert _load("seed.json")["meta"]["feed_version"] == "3.8"


def test_old_v30_shaped_opportunity_still_validates_cleanly():
    feed = {
        "meta": {"feed_version": "3.0", "generated_at": "2026-07-13T00:00:00Z", "opportunity_count": 1},
        "opportunities": [_minimal_old_opportunity()],
    }
    result = validate_feed(feed, _load("taxonomy.json"), _load("config/role_taxonomy.json"))
    assert result.errors == []
    assert result.warnings == []


def test_known_organisation_is_enriched_from_registry():
    opp = _minimal_old_opportunity()
    opp["organisation"] = {"name": "One Acre Fund", "type": "ngo", "verified": True}
    enriched = _enricher().enrich(opp)
    assert enriched["organisation"]["id"] == "one-acre-fund"
    assert enriched["organisation"]["registry_managed"] is True
    assert enriched["organisation"]["type_detail"] == "ngo"


def test_unknown_organisation_remains_honestly_unregistered():
    enriched = _enricher().enrich(_minimal_old_opportunity())
    assert enriched["organisation"]["id"] is None
    assert enriched["organisation"]["registry_managed"] is False


def test_location_enrichment_adds_city_country_code_and_region_without_rewriting_legacy_country():
    opp = _minimal_old_opportunity()
    opp["location"]["raw"] = "Cape Town City Centre, Cape Town Region"
    opp["location"]["country"] = "South Africa"
    enriched = _enricher().enrich(opp)
    location = enriched["location"]
    assert location["country"] == "South Africa"
    assert location["city"] == "Cape Town"
    assert location["country_code"] == "ZA"
    assert location["region_canonical"] == "Southern Africa"
    assert location["normalisation_confidence"] == 1.0


def test_role_family_and_theme_are_derived_from_canonical_specialisation():
    opp = _minimal_old_opportunity()
    opp.update({
        "industry": "financial_services",
        "specialisations": ["climate_finance"],
        "categories": ["climate_finance"],
    })
    enriched = _enricher().enrich(opp)
    assert enriched["role_family"] == "investment"
    assert enriched["role_subfamily"] == "climate_finance"
    assert {"finance", "climate"} <= set(enriched["thematic_sectors"])


def test_remote_emea_role_gets_likely_eligible_evidence_not_certain_eligibility():
    opp = _minimal_old_opportunity()
    opp["location"] = {
        "raw": "Remote (EMEA)", "country": None, "region": None,
        "is_remote_from_kenya": True, "scope": "international", "relocation_country": None,
    }
    opp["work_mode"] = "remote_global"
    enriched = _enricher().enrich(opp)
    assert enriched["eligibility"]["status"] == "likely_eligible"
    assert enriched["eligibility"]["confidence"] < 1.0
    assert "remote_regional_or_africa" in enriched["eligibility"]["evidence"]


def test_explicit_citizenship_restriction_is_not_overridden_by_african_location():
    opp = _minimal_old_opportunity()
    opp["summary"] = "Applicants must be a Kenyan citizen for this national position."
    enriched = _enricher().enrich(opp)
    assert enriched["eligibility"]["status"] == "citizenship_restricted"
    assert enriched["eligibility"]["citizenship_required"] is True


def test_source_is_linked_to_governance_registry():
    opp = _minimal_old_opportunity()
    opp["source"] = {
        "name": "One Acre Fund", "url": "https://boards.greenhouse.io/oneacrefund",
        "confidence": "official",
    }
    enriched = _enricher().enrich(opp)
    assert enriched["source"]["id"] == "greenhouse-hosted-employer-board"
    assert enriched["source"]["kind"] == "employer_ats"
    assert enriched["source"]["registry_managed"] is True


def test_feed_builder_enriches_new_collector_records_when_configured():
    builder = FeedBuilder(_load("taxonomy.json"), _load("config/source_registry.json"), enricher=_enricher())
    builder.add(_minimal_old_opportunity())
    assert "eligibility" in builder.opportunities[0]
    assert "country_code" in builder.opportunities[0]["location"]
    assert "type_detail" in builder.opportunities[0]["organisation"]


def test_validator_rejects_bad_phase2_role_and_eligibility():
    opp = _enricher().enrich(_minimal_old_opportunity())
    opp["role_family"] = "invented_role"
    opp["eligibility"]["confidence"] = 1.5
    feed = {
        "meta": {"feed_version": "3.8", "generated_at": "2026-07-13T00:00:00Z", "opportunity_count": 1},
        "opportunities": [opp],
    }
    result = validate_feed(feed, _load("taxonomy.json"), _load("config/role_taxonomy.json"))
    assert any("role_family" in error for error in result.errors)
    assert any("eligibility.confidence" in error for error in result.errors)


def test_role_registry_maps_every_legacy_industry_and_specialisation():
    taxonomy = _load("taxonomy.json")
    roles = _load("config/role_taxonomy.json")
    assert set(roles["industry_role_family_map"]) == {row["id"] for row in taxonomy["industries"]}
    assert set(roles["specialisation_role_family_map"]) == {row["id"] for row in taxonomy["specialisations"]}


def test_packaged_feed_has_phase2_fields_on_every_record():
    for opp in _load("feed.json")["opportunities"]:
        assert {"id", "type_detail", "registry_managed"} <= set(opp["organisation"])
        assert {"city", "country_code", "country_canonical", "region_canonical", "normalisation_confidence"} <= set(opp["location"])
        assert {"role_family", "role_subfamily", "thematic_sectors", "eligibility"} <= set(opp)
        assert {"status", "confidence", "citizenship_required", "eligible_nationalities", "work_authorisation_required", "evidence"} <= set(opp["eligibility"])
        assert {"id", "kind", "registry_managed"} <= set(opp["source"])


def test_phase2_does_not_change_packaged_opportunity_ids():
    ids = [row["id"] for row in json.loads((Path(__file__).parent / "fixtures" / "legacy_packaged_feed.json").read_text(encoding="utf-8"))["opportunities"]]
    digest = hashlib.sha256(("\n".join(ids) + "\n").encode()).hexdigest()
    assert len(ids) == 204
    assert digest == "8f10da989a13304af96d18d317ec4a1227f178123be50dc4cf8a983f10c49e86"


def test_phase2_preserves_current_android_dto_projection():
    for filename, expected in {
        "scripts/tests/fixtures/legacy_packaged_feed.json": "9091a81b364025ea9d61c9b961231bdd6187fc0d025532297da761469419637c",
        "seed.json": "5d881af69edd21e0e983dddc0b2ed0f5c4ba958130baac7536fbb97d99cd75fe",
    }.items():
        opportunities = _load(filename)["opportunities"]
        payload = json.dumps(
            [legacy_projection(row) for row in opportunities],
            sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        )
        assert hashlib.sha256(payload.encode()).hexdigest() == expected
