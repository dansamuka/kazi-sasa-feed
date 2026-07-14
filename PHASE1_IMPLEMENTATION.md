# Phase 1 Implementation — Registry Architecture

Implemented on 2026-07-13 from the completed Phase 0 package.

## Objective

Introduce authoritative organisation, source, location, role and public-portal
registries without changing the published feed, collector behaviour or stable
opportunity IDs.

## Authoritative registries

- `config/organisations.json`
- `config/source_registry.json`
- `config/public_portals.json`
- `config/african_locations.json`
- `config/role_taxonomy.json`
- `config/source_policies.json`

## Migration result

- 21 unique organisations registered.
- 22 ATS connections migrated.
- Existing target counts preserved:
  - Greenhouse: 7
  - Lever: 3
  - Ashby: 7
  - Pinpoint: 5
- 17 source-governance records migrated.
- 54 African countries registered.
- 46 initial major cities registered.
- 25 high-level role families registered.
- Five government/public-service portals recorded as disabled planned targets.

## Compatibility strategy

The following files remain available, but are generated from the authoritative
registries:

- `config/greenhouse_boards.json`
- `config/lever_boards.json`
- `config/ashby_boards.json`
- `config/pinpoint_boards.json`
- `sources.json`

Run:

```bash
python3 scripts/generate_legacy_configs.py
```

CI uses `--check` and fails if any generated artifact is stale.

## Runtime integration

`scripts/refresh_feed.py` now reads ATS targets from
`config/organisations.json`. It retains a legacy fallback only for downstream
forks that have not yet migrated. The packaged repository validates that both
views are identical.

## Validation and reporting

Added:

- `scripts/registry.py`
- `scripts/validate_registry.py`
- `scripts/generate_legacy_configs.py`
- `scripts/generate_registry_report.py`
- `reports/registry_report.json`
- `scripts/tests/test_phase1.py`

The registry validator checks IDs, duplicate organisations and connections,
source confidence, all cross-referenced role families and country codes, all
54 African countries, planned portal configuration, and registry policy flags.

## Backward compatibility evidence

- The packaged feed remains at 204 opportunities.
- Opportunity ordering is unchanged.
- The SHA-256 digest of all ordered opportunity IDs remains:
  `8f10da989a13304af96d18d317ec4a1227f178123be50dc4cf8a983f10c49e86`.
- Feed and seed validation remain clean.
- 84 offline tests pass.

## Intentionally deferred

- Richer feed schema fields are Phase 2.
- Scalable collector discovery/orchestration is Phase 3.
- Full city aliases, coordinates and multilingual normalisation are Phase 4.
- Public-service portals remain disabled until their collectors and fixtures
  are implemented.
