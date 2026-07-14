# Phase 3 implementation — registry-driven collection pipeline and public filters

Phase 3 replaces the manually wired collector loop with a declarative collector
registry and shared execution runner. It also exposes the Phase 2 metadata on
the public GitHub Pages board and repairs Jobicy's list/string parsing failure.

## Collector framework

New files:

- `scripts/collectors/base.py` — `CollectorSpec`, `CollectorContext`, and
  `CollectorRunSummary` contracts.
- `scripts/collectors/registry.py` — the authoritative built-in collector
  registry and serialisable collector manifest.
- `scripts/pipeline/collect.py` — isolated collector execution, configuration
  checks, target counts, duration tracking, rollback of partial records, error
  containment, and health data.
- `scripts/pipeline/http.py` — shared HTTP session with retry/backoff, per-source
  timeout and throttling policy, short-lived JSON caching, and request metrics.
- `scripts/normalizers/text.py` — defensive string/list/object normalisation
  for inconsistent third-party payloads.

`scripts/refresh_feed.py` now obtains all collectors from
`default_collector_specs()` and executes them through `CollectorRunner`.
Adding a new collector no longer requires adding a new import and try/except
block to the orchestrator.

Operational additions:

- `--list-collectors` prints the registered collector inventory.
- `--only-source KEY` runs one or more selected collectors for diagnostics.
- `reports/collector_manifest.json` records source kind, scheduling class,
  configuration requirements, freshness targets, and HTTP policy.
- `reports/collector_errors.json` records structured failures and skipped sources,
  including on an all-source failure before the last good feed is protected.
- `reports/source_health.json` is version 2.0 and can include duration,
  returned count, actual added count, source kind, schedule class, missing
  environment variables, and count mismatches.
- Collector ordering remains identical to Phase 2 to preserve default feed
  ordering where upstream responses are unchanged.

## Jobicy repair

Jobicy fields are no longer assumed to be strings. The collector now handles:

- strings;
- lists and nested lists;
- display-value objects;
- numeric values;
- malformed jobs containers and non-object rows.

`jobGeo`, `jobType`, `jobLevel`, `jobIndustry`, descriptions, company names,
URLs, dates, and salary fields are normalised before string operations. A
fixture test reproduces the reported list-field failure and verifies successful
collection.

## Public board filters

The static site payload now includes:

- country and country code;
- city;
- role family and subfamily;
- detailed organisation type;
- eligibility status and confidence;
- thematic sectors.

The board adds working multi-select filters for:

1. Country
2. City
3. Role family
4. Organisation type
5. Eligibility

Cards now show role family, organisation type, and eligibility badges. Expanded
cards show canonical city/country and eligibility confidence. Search also
covers role family, organisation type, eligibility, and thematic sectors.

The publication guard now supports `--require-phase3-site` and prevents GitHub
Actions from publishing a site missing these filters or payload fields.

## Compatibility and validation

- Feed schema remains `3.1`; Phase 3 changes orchestration and presentation,
  not the Android feed contract.
- All 204 packaged opportunity IDs remain unchanged.
- Existing Phase 1 registry compatibility remains available through the
  `_adapter_config` wrapper.
- The current Android DTO projection is unchanged.
- `docs/index.html` was regenerated from the packaged `feed.json`.
- Offline suite: 123 tests passing.
- Feed and seed validation: zero errors and zero warnings.

## Scope boundary

Phase 3 makes the pipeline scalable and the Phase 2 metadata useful in the web
interface. It does not add new external source families. Recruitee, expanded
ReliefWeb coverage, UN feeds, enterprise ATS adapters, DFIs, NGOs, and public
service portals remain later source-onboarding phases.
