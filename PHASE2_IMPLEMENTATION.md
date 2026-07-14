# Phase 2 implementation — additive enriched feed schema

Phase 2 upgrades the published feed from version `3.0` to `3.1` without
removing or renaming any field consumed by the current Android application.
The Android parser is configured with `ignoreUnknownKeys = true`; therefore,
new Phase 2 fields are ignored safely by older app builds while future app
versions can begin consuming them.

## Implemented schema additions

Every newly collected opportunity is enriched through
`scripts/phase2_enrichment.py` before it enters the feed builder. The packaged
`feed.json` and `seed.json` snapshots were migrated through the same code.

Added metadata includes:

- Registry-backed `organisation.id`, `organisation.type_detail`, and
  `organisation.registry_managed`.
- Canonical `location.city`, `location.country_code`,
  `location.country_canonical`, `location.region_canonical`, and a
  normalisation confidence score.
- `role_family`, `role_subfamily`, and controlled `thematic_sectors`.
- Structured `eligibility` status, confidence, restrictions, and evidence.
- Registry-backed `source.id`, `source.kind`, and
  `source.registry_managed`.

Unknown or unsupported values are represented honestly as null, empty, or
`uncertain`; the migration does not invent employer IDs, cities, citizenship
rules, or eligibility guarantees.

## Registry upgrades

`config/role_taxonomy.json` is now version `2.0` and contains:

- 33 role families.
- 20 supported detailed organisation types.
- Complete mappings for all 30 legacy industries.
- Complete mappings for all 134 legacy specialisations.
- 35 controlled thematic sectors.
- Seven eligibility statuses.

The registry validator now checks all mapping coverage and cross-references.

## Backward compatibility

`scripts/migrate_phase2.py` calculates the projection of each opportunity that
the current Android DTOs actually parse. It refuses to write a migrated file
if that projection changes.

For the packaged artifacts:

- All 204 live opportunity IDs are unchanged.
- All 10 seed opportunity IDs are unchanged.
- The complete current Android DTO projections are unchanged.
- Older v3.0-shaped opportunities without Phase 2 fields still validate.

## Validation and CI

`scripts/validate_feed.py` now validates Phase 2 fields when they are present,
while continuing to accept older records where they are absent. It validates:

- Stable organisation/source IDs.
- Detailed organisation types.
- ISO-2 location codes and normalisation confidence.
- Role families, subfamilies, and thematic sectors.
- Eligibility status, confidence, flags, and evidence.

The GitHub Actions workflow supplies `config/role_taxonomy.json` to the feed
validator and runs all Phase 2 tests before publishing.

## Reporting

`reports/coverage_report.json` now includes coverage by role family, thematic
sector, eligibility status, and city, plus completeness for all principal
Phase 2 fields.

`reports/phase2_summary.json` records migration counts, registry coverage,
validation results, stable-ID hashes, and Android compatibility hashes.

## Packaged snapshot result

- 204 live opportunities retained.
- 54 live records matched to organisation registry IDs.
- 204 live records matched to source registry IDs.
- 198 live records received ISO-2 country codes.
- 139 live records received canonical cities.
- 201 live records received role families.
- 204 live records received structured eligibility evidence.
- Feed and seed validation: zero errors and zero warnings.
- Offline suite: 99 tests passing.

## Scope boundary

Phase 2 adds the schema and enrichment layer only. It does not add new live
source adapters or increase the opportunity count. Those activities begin in
later phases.
