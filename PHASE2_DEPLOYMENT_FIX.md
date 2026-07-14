# Phase 2 deployment-path hardening

## Problem addressed

A scheduled workflow can report success even when a refreshed file is written to a path that is not staged or published. The public GitHub Pages board and root `feed.json` must always be generated and verified as the exact repository-root artifacts committed by the workflow.

## Implementation

- All workflow commands now run from the repository root.
- The refresh command explicitly writes:
  - `feed.json`
  - `reports/coverage_report.json`
  - `reports/source_health.json`
- The site builder explicitly reads `feed.json` and writes `docs/index.html`.
- `scripts/verify_published_output.py` checks:
  - feed version is `3.1`;
  - the feed is non-empty;
  - `meta.opportunity_count` matches the actual list;
  - `generated_at` is fresh during CI;
  - every record has the additive Phase 2 organisation, role, location, source, and eligibility fields;
  - the generated site contains the same version, timestamp, and opportunity count as the root feed.
- CI now fails before committing if an old root feed or mismatched site is detected.
- Deployment-specific tests prevent reintroduction of `working-directory: scripts` for publication commands.

## Deployment

After pushing this ZIP, run **Actions → Refresh feed → Run workflow**. The workflow must pass both publication verification steps before it can commit the refreshed root feed and GitHub Pages site.
