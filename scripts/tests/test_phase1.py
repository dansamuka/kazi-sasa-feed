"""Phase 1 organisation/source registry architecture tests."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
REPO = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))

from refresh_feed import _adapter_config  # noqa: E402
from registry import (  # noqa: E402
    LEGACY_CONFIG_FILE,
    adapter_boards,
    legacy_ats_payload,
    legacy_sources_payload,
    load_organisation_registry,
    load_source_registry,
)
from validate_registry import validate_all  # noqa: E402


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_all_phase1_registries_validate():
    assert validate_all(REPO) == []


def test_organisation_registry_has_all_migrated_targets():
    registry = load_organisation_registry(REPO / "config" / "organisations.json")
    assert len(registry["organisations"]) >= 51
    assert sum(len(org["sources"]) for org in registry["organisations"]) >= 52


def test_existing_adapter_target_counts_are_preserved():
    registry = load_organisation_registry(REPO / "config" / "organisations.json")
    assert {adapter: len(adapter_boards(registry, adapter)) for adapter in LEGACY_CONFIG_FILE} == {
        "greenhouse": 8,
        "lever": 3,
        "ashby": 7,
        "pinpoint": 5,
        "recruitee": 5,
    }


def test_legacy_ats_files_are_exact_generated_artifacts():
    registry = load_organisation_registry(REPO / "config" / "organisations.json")
    for adapter, filename in LEGACY_CONFIG_FILE.items():
        assert _load(REPO / "config" / filename) == legacy_ats_payload(registry, adapter)


def test_sources_json_is_exact_generated_artifact():
    registry = load_source_registry(REPO / "config" / "source_registry.json")
    assert _load(REPO / "sources.json") == legacy_sources_payload(registry)


def test_refresh_orchestrator_reads_registry_targets():
    expected = adapter_boards(load_organisation_registry(REPO / "config" / "organisations.json"), "greenhouse")
    actual = _adapter_config(REPO, "config/organisations.json", "greenhouse", "greenhouse_boards.json")
    assert actual == expected


def test_every_organisation_has_stable_id_and_source():
    registry = load_organisation_registry(REPO / "config" / "organisations.json")
    assert all(org["id"] and org["name"] and org["sources"] for org in registry["organisations"])
    assert len({org["id"] for org in registry["organisations"]}) == len(registry["organisations"])


def test_all_54_african_countries_are_registered():
    countries = _load(REPO / "config" / "african_locations.json")["countries"]
    assert len(countries) == 54
    assert len({country["iso2"] for country in countries}) == 54
    assert {"KE", "ZA", "NG", "CI", "EG", "MA"} <= {country["iso2"] for country in countries}


def test_role_registry_covers_current_organisation_career_families():
    roles = _load(REPO / "config" / "role_taxonomy.json")
    valid = {role["id"] for role in roles["role_families"]}
    organisations = load_organisation_registry(REPO / "config" / "organisations.json")
    referenced = {family for org in organisations["organisations"] for family in org.get("career_families", [])}
    assert referenced <= valid


def test_phase9_public_portals_are_registered_with_explicit_status():
    data = _load(REPO / "config" / "public_portals.json")
    assert len(data["portals"]) == 5
    enabled = [portal for portal in data["portals"] if portal["enabled"]]
    disabled = [portal for portal in data["portals"] if not portal["enabled"]]
    assert {portal["country_code"] for portal in enabled} == {"KE", "TZ", "ZA"}
    assert {portal["country_code"] for portal in disabled} == {"UG", "RW"}
    assert all(portal.get("disabled_reason") for portal in disabled)


def test_phase1_does_not_change_packaged_feed_ids():
    ids = [row["id"] for row in _load(REPO / "feed.json")["opportunities"]]
    digest = hashlib.sha256(("\n".join(ids) + "\n").encode()).hexdigest()
    assert len(ids) == 204
    assert digest == "8f10da989a13304af96d18d317ec4a1227f178123be50dc4cf8a983f10c49e86"


def test_registry_policy_declares_authoritative_files():
    registry_policy = _load(REPO / "config" / "source_policies.json")["registry"]
    assert all(registry_policy.values())
