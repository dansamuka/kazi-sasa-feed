# Phase 12 Run #38 Test-Order Hotfix

## Problem

The safe deployment process correctly preserved the live 945-record `feed.json`, but six historical regression tests still treated the repository-root feed as the immutable 204-record packaged snapshot. The Phase 12 test also expected certification metadata before the workflow's bootstrap step ran.

## Correction

- Added `scripts/tests/fixtures/legacy_packaged_feed.json` as the immutable 204-record compatibility fixture.
- Moved all historical stable-ID and Android DTO projection assertions to that fixture.
- Kept the repository-root `feed.json` as a mutable publication artifact that may contain any valid live record count.
- Changed the Phase 12 feed test to run `migrate_phase12.migrate_data()` in memory against the current root feed and validate the migrated result.
- Confirmed the full suite against both the bundled 204-record feed and a simulated 945-record pre-certification live feed.

## Result

- 287/287 tests pass on the bundled snapshot.
- 287/287 tests pass with a simulated 945-record live feed lacking Phase 12 metadata.
- The workflow can now reach the certification bootstrap step instead of failing before migration.
