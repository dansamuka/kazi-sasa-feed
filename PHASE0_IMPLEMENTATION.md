# Phase 0 implementation record

Implemented against the supplied `kazi-sasa-feed-v3 (14).zip` snapshot.

## Completed

- Bumped generated feed output from schema `2.0` to `3.0`.
- Normalised all published category and specialisation values to canonical taxonomy IDs.
- Added source-specific mappings for Adzuna, One Acre Fund, GiveDirectly, Jumo, Stripe, Cloudflare, GitLab and Notion internal department labels.
- Prevented unmapped raw taxonomy values and raw skill values from being published.
- Removed the duplicate RemoteOK source registration and added a source-registry validator.
- Replaced generic sponsorship-based inclusion with role-specific international mobility evidence.
- Migrated the packaged `feed.json` and offline `seed.json` to clean v3 taxonomy.
- Added coverage, source-health, rejection-audit and migration-summary reports.
- Added one saved-response fixture test for every current collector.
- Corrected GitHub Actions so it runs pytest rather than merely executing a test module.
- Added CI gates for source-registry validation and zero feed warnings.
- Regenerated the static GitHub Pages board from the cleaned feed.

## Measured result

- Feed records: 609 before; 204 retained; 405 rejected for insufficient African/global eligibility evidence.
- Stable IDs: all 204 retained records kept their original IDs.
- Validation: 322 warnings before; 0 warnings after.
- Source registry: 18 entries before; 17 after removing one duplicate.
- Offline tests: 72 passing, including 11 collector fixture tests.

## Environment limitation

The supplied snapshot was normalised locally rather than freshly downloaded from every live source. GitHub secret values are not visible inside a ZIP, so ReliefWeb and Adzuna credentials could not be independently verified here. The workflow now reports whether those secret groups are configured without printing their values.
