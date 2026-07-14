# kazi-sasa-feed

The live data source for the Kazi Sasa app - a single `feed.json` file, refreshed
on a schedule by GitHub Actions and served over GitHub raw. The app
(`FeedApiService.DEFAULT_FEED_URL`) fetches this file directly; there is no
backend server.

This mirrors the pattern already proven on the Kenya Election Intelligence
Dashboard: static, source-transparent JSON, versioned in Git, rebuilt by a
scheduled workflow, no server to run or pay for.

**v3 (general-search spec):** the feed pipeline now pulls through 18 collector
families across every field, not just development/climate finance, and every
opportunity carries richer structured metadata (industry, specialisation,
years of experience, education, contract type) for the app's search and
filter UI. See `SCHEMA.md` for the full field list and the v3 spec document
for the overall plan this implements.

**Phase 0 hardening:** the packaged feed established schema v3.0, source taxonomy
terms are normalised before publication, CI fails on taxonomy warnings, the
source registry is checked for duplicates, and all collectors have offline
response-fixture tests.

**Phase 1 registry architecture:** `config/organisations.json` and
`config/source_registry.json` are now authoritative. The four per-ATS board
files and root `sources.json` are generated compatibility artifacts. The
registry currently contains 21 organisations, 22 ATS connections, all 54
African countries, an initial 46-city index, 33 role families, and five
planned public-service portal targets. The feed snapshot and its 204 stable
opportunity IDs are unchanged.

**Phase 2 additive schema:** the feed is now version 3.1 and adds registry-backed
organisation IDs, detailed organisation types, canonical African city/country
metadata, role families and subfamilies, thematic sectors, structured
eligibility evidence, and source-registry IDs. The migration is additive: all
204 opportunity IDs and the complete current Android DTO projection are
unchanged. Both `feed.json` and `seed.json` are enriched and clean.

**Phase 3 scalable collection and filters:** collectors are now declared in a
single executable registry and run through an isolated pipeline runner with
configuration checks, target counts, timings, rollback on partial failure, and
consistent health metadata. A shared HTTP client provides retry/backoff,
per-source timeouts and throttling, short-lived JSON caching, and request metrics.
Jobicy safely handles list/object fields. The GitHub Pages board now exposes
country, city, role-family, organisation-type, and eligibility filters, and CI
refuses to publish a site missing them. The Phase 3 architecture remains backward-compatible and all 204 packaged IDs remain unchanged.
**Phase 4 African location and multilingual foundation:** the feed is now
version 3.2. `config/african_locations.json` contains all 54 African countries,
155 major cities, 70 selected administrative areas, 111 city coordinates,
regional aliases, and matching aliases across English, French, Portuguese,
Arabic, and Swahili. Unicode-preserving normalisation, confidence/evidence
fields, multilingual work-mode/experience/contract/language/deadline/eligibility
extraction, and a 582-case location regression corpus are now active across
all collectors. The migration remains additive: all 204 IDs and the Android DTO
projection are unchanged.

**Phase 5 public-source expansion:** the feed is now version 3.3. Recruitee
public careers boards, Africa-wide ReliefWeb batching, optional UN Talent
JSON/RSS ingestion, and a role-lane Adzuna portfolio are registered in the
Phase 3 runner. Cross-source deduplication gives precedence to employer and
institution-official records without merging generic or unknown employers.
Regional regression gates protect published African coverage and report
stretch targets for geographic balance, source concentration, and official
application-link coverage. The packaged snapshot remains 204 records because
this release validates adapters offline rather than performing a live refresh.

**Phase 6 investment and DFI classification:** the feed is now version 3.4. A
26-track investment taxonomy distinguishes core investment, investment-adjacent,
and institutional-support roles. Title and canonical-specialisation evidence
outweigh employer descriptions; an investment/DFI employer is context rather
than proof that every vacancy is an investment role. A 99-case reviewed corpus
covers English, French, Portuguese and Arabic titles plus accounting, technology
and project-portfolio false positives. Every record now carries an
`investment_profile`, the public board has an Investment track filter, and CI
publishes a dedicated investment coverage report.


**Phase 7 DFI and multilateral source pack:** the feed is now version 3.5.
Twenty-five priority institutions are registered across Cornerstone, SAP
SuccessFactors, Oracle Candidate Experience, and official public career-page
adapters. Every opportunity now carries an additive `institution_profile` that
separates employer type from role classification. CI publishes a dedicated DFI
coverage report and the public board adds DFI/multilateral and DFI-relevance
filters. The packaged 204-record snapshot preserves all IDs and the current
Android DTO projection; newly registered institutions populate on live refresh.


**Phase 8 NGO, UN and development source pack:** the feed is now version 3.6.
Thirty-three priority organisations are registry-tagged across Greenhouse,
Recruitee, Oracle Candidate Experience, SAP SuccessFactors, PageUp and official
career pages. A 20-track NGO/development taxonomy separates humanitarian,
development and technical-programme roles from institutional support jobs.
Every record carries an additive `ngo_profile`; the public board adds NGO/UN
and development-track filters; CI publishes `ngo_coverage_report.json`. The
packaged snapshot preserves all 204 IDs and the Android DTO projection.

## Sources currently wired in

| Source | Type | Coverage | Auth needed |
|---|---|---|---|
| ReliefWeb | Public API | Humanitarian/NGO, all 54 African countries | `RELIEFWEB_APPNAME` secret |
| Greenhouse | Public API | 8 registry-managed employer boards | None |
| Lever | Public API | 3 registry-managed employer boards | None |
| Ashby | Public API | 7 registry-managed employer boards | None |
| Pinpoint | Public API | 5 registry-managed employer boards | None |
| Recruitee | Public careers API | 5 verified NGO/investment-health boards | None |
| UN Talent | JSON/RSS feed | UN and international-development opportunities | `UNTALENT_FEED_URL`; token optional |
| Cornerstone | Public institution career site | World Bank Group and compatible CSOD sites | None |
| SAP SuccessFactors | Public institution career site | IsDB, EBRD and compatible public career sites | None |
| Oracle Candidate Experience | Public institution career site | Green Climate Fund, UNDP and compatible public career sites | None |
| PageUp | Public institution career site | UNICEF and compatible PageUp sites | None |
| Official institutional pages | Public HTML/JSON-LD/document links | Registered DFIs, multilaterals, NGOs, UN agencies and development implementers | None |
| Himalayas | Public API | Global remote jobs | None |
| Remotive | Public API | Global remote jobs | None |
| Jobicy | Public API | Global remote jobs, skews Americas/EMEA | None |
| RemoteOK | Public API | Global remote jobs, tech-skewed | None |
| Arbeitnow | Public API | Europe/DACH-focused, visa-sponsorship theme | None |
| Adzuna | Public API | **South Africa only** within Africa - see `collectors/adzuna.py` | `ADZUNA_APP_ID` + `ADZUNA_APP_KEY` secrets (free registration) |

**Checked and deliberately excluded/deferred (see `LEGAL_NOTES.md`):**
BrighterMonday (ToS explicitly prohibits scraping), Fuzu/IMPACTPOOL (no public API, deferred to
partnership outreach), Workday ("free public API" claim checked and found
misleading - no sanctioned public endpoint exists), Apify-hosted scrapers
(paid platform, one specifically scrapes BrighterMonday in violation of its
ToS), Techmap/jobdatafeeds.com and Jooble (deferred, real but need direct
terms verification / a signup step).

## Files

- **`feed.json`** - the current cleaned live snapshot. The Phase 0 migration
  removed records with no verified African/global location signal and retained
  a rejection audit under `reports/phase0_rejected_records.json`.
- **`currency_rates.json`** - daily FX rates from Frankfurter, refreshed by
  `scripts/refresh_fx.py`. Not yet consumed by any collector's output (see
  SCHEMA.md) - infrastructure is in place, wiring into `compensation` is a
  follow-up task.
- **`seed.json`** - bundled fallback content, mirrored into the app at
  `app/src/main/assets/seed.json` (spec §7.7's offline/first-run fallback).
- **`SCHEMA.md`** - the field-for-field contract (spec §24 + v3 additions).
- **`LEGAL_NOTES.md`** - ToS/access basis per source; check before adding a new one.
- **`taxonomy.json`** - v3 two-level structure: `industries` (single-select),
  `specialisations` (multi-select, nested under an industry), and `skills`
  (cross-cutting, unchanged shape from v2). 30 industries, 156
  specialisations, 66 skills as of this writing.
- **`config/organisations.json`** - authoritative organisation registry,
  including 51 stable organisation records and 52 source connections. Twenty-five
  institutions belong to the Phase 7 DFI/multilateral source pack.
- **`config/source_registry.json`** - authoritative source-governance
  registry, including stable source IDs, collector mapping, source kind and
  default confidence.
- **`sources.json`** - generated backward-compatible source-confidence view.
  Do not edit it directly.
- **`config/public_portals.json`** - public-service portal registry and
  disabled Phase 1 targets awaiting their collectors.
- **`config/african_locations.json`** - Phase 4 authoritative multilingual
  index for 54 countries, 155 major cities, selected administrative areas,
  coordinates, regional aliases and five supported languages.
- **`config/location_test_cases.json`** - 582-case multilingual geographic
  regression corpus used by CI.
- **`config/role_taxonomy.json`** - role-family, organisation-type, thematic-sector, investment-classification and DFI-relevance registry;
  `taxonomy.json` remains authoritative for legacy industries, specialisations
  and skills.
- **`config/investment_taxonomy.json`** - Phase 6 authoritative 26-track investment/DFI taxonomy, title/context phrases, institution types and false-positive controls.
- **`config/investment_test_cases.json`** - 99-case reviewed investment classification regression corpus.
- **`config/source_policies.json`** - common access, publication, eligibility
  and registry-governance rules.
- **`reports/coverage_report.json`** - source, country, industry and data-
  completeness baseline generated from the published feed.
- **`reports/source_health.json`** - per-collector status/count report. During
  scheduled refreshes it records collected, empty, skipped and failed sources,
  plus Phase 3 runtime duration, configured targets and source class.
- **`reports/collector_manifest.json`** - Phase 3 executable collector registry
  inventory: source kind, scheduling class, required environment configuration,
  freshness target, HTTP policy, and configured employer targets.
- **`reports/collector_errors.json`** - structured collection failures and skipped
  sources. It is also written on an all-source failure before the pipeline refuses
  to overwrite the last good feed.
- **`reports/deduplication_report.json`** - cross-source duplicate decisions and
  official-source replacements.
- **`reports/coverage_gate_report.json`** - regional/source concentration regression
  gates and Phase 5 stretch-target warnings.
- **`reports/investment_coverage_report.json`** - Phase 6 counts by investment classification, track, DFI relevance, country, source and organisation type.
- **`reports/dfi_coverage_report.json`** - Phase 7 institution, country, source, role-family and official-link coverage.
- **`reports/registry_report.json`** - Phase 1 registry inventory and coverage
  report, including organisation, ATS, country, city and role-family counts.
- **`reports/phase0_rejected_records.json`** - audit list of records removed
  from the pre-Phase-0 snapshot and the reason for rejection.
- **`reports/phase0_summary.json`** - before/after counts, validation results,
  stable-ID confirmation and the local-environment limitations.
- **`PHASE0_IMPLEMENTATION.md`** - concise Phase 0 implementation record.
- **`PHASE1_IMPLEMENTATION.md`** - Phase 1 architecture, migration and test
  record for handover.
- **`.github/workflows/refresh-feed.yml`** - runs three times a day: refreshes
  FX rates (non-blocking), refreshes the feed, validates, runs unit tests,
  commits only if validation passes.
- **`scripts/refresh_feed.py`** - registry-driven orchestrator: loads config,
  executes collectors through `CollectorRunner`, deduplicates cross-source
  overlap, validates, and writes `feed.json`. Supports `--list-collectors` and
  `--only-source KEY` for diagnostics. Refuses to overwrite `feed.json` with
  an empty result if every collector fails.
- **`scripts/collectors/base.py`** / **`scripts/collectors/registry.py`** -
  Phase 3 collector contracts and authoritative executable collector registry.
- **`scripts/pipeline/collect.py`** - source isolation, environment/configuration
  gates, timings, counts and consistent health-status generation.
- **`scripts/normalizers/text.py`** - defensive normalisation for APIs that
  return strings, lists or objects inconsistently; currently used by Jobicy.
- **`scripts/normalizers/location.py`** - Unicode-preserving African country,
  city, administrative-area and regional normalisation with confidence and evidence.
- **`scripts/normalizers/multilingual.py`** - conservative English, French,
  Portuguese, Arabic and Swahili extraction for experience, contracts, required
  languages, deadlines and eligibility restrictions.
- **`scripts/refresh_fx.py`** - fetches daily USD exchange rates from
  Frankfurter (free, no API key) and writes `currency_rates.json`.
- **`scripts/collectors/`** - one module per source, including Phase 7 `cornerstone.py`, `successfactors.py`, `oracle_cx.py`, `official_html.py`, and shared `official_common.py`:
  - `reliefweb.py` — humanitarian/NGO jobs via the ReliefWeb API v2.
  - `greenhouse.py` / `lever.py` / `ashby.py` — generic collectors. Their
    targets are loaded from `config/organisations.json`; the old board files
    are generated for compatibility.
  - `adzuna.py` — South-Africa-only (see module docstring for why); also
    extracts years-of-experience/education/contract-type since Adzuna gives
    a real description field to work with.
  - `pinpoint.py` — generic collector for any employer on Pinpoint ATS
    (Sun King's actual ATS, discovered after its Lever guess 404'd); targets
    are loaded from the organisation registry.
  - `_common.py` — shared helpers: location parsing, Africa-relevance filter,
    work-mode/seniority inference, HTML→summary conversion, and the v3
    extraction functions (`extract_years_experience`, 
    `extract_education_requirement`, `extract_languages_required`,
    `extract_contract_type`, `classify_industry`, `normalise_salary`).
- **`config/greenhouse_boards.json`** / **`lever_boards.json`** /
  **`ashby_boards.json`** / **`pinpoint_boards.json`** — generated legacy
  views. Update `config/organisations.json`, then run
  `python3 scripts/generate_legacy_configs.py`.
- **`scripts/phase2_enrichment.py`** - additive registry-backed organisation,
  location, role, thematic, eligibility and source enrichment used by every
  production collector.
- **`scripts/migrate_phase2.py`** - historical Phase 2 migration.
- **`scripts/migrate_phase4.py`** - additive Phase 4 snapshot migration; refuses
  to write if the current Android DTO projection changes.
- **`scripts/migrate_phase6.py`** - additive Phase 6 investment-profile migration with ID/order and Android projection checks.
- **`scripts/migrate_phase7.py`** - additive Phase 7 institution-profile migration with the same stable-ID and Android compatibility checks.
- **`scripts/classifiers/investment.py`** - high-precision investment and DFI role classifier separating role evidence from institution context.
- **`PHASE2_IMPLEMENTATION.md`** - Phase 2 schema, migration, validation and
  compatibility handover record.
- **`PHASE3_IMPLEMENTATION.md`** - Phase 3 collector framework, Jobicy repair,
  web filters, deployment guard and compatibility handover record.
- **`PHASE4_IMPLEMENTATION.md`** - Phase 4 location, multilingual extraction,
  corpus, validation and compatibility handover record.
- **`reports/phase4_summary.json`** - machine-readable Phase 4 results.
- **`PHASE5_CI_HOTFIX.md`** - live-source timestamp, deadline, and taxonomy resilience fixes.
- **`PHASE5_IMPLEMENTATION.md`** - Phase 5 source expansion, deduplication, and
  coverage-gate implementation record.
- **`reports/phase5_summary.json`** - machine-readable Phase 5 results.
- **`PHASE6_IMPLEMENTATION.md`** - Phase 6 taxonomy, classifier, corpus, reporting, site and compatibility handover.
- **`reports/phase6_summary.json`** - machine-readable Phase 6 results.
- **`PHASE7_IMPLEMENTATION.md`** - Phase 7 institution registry, enterprise adapters, reporting, site and compatibility handover.
- **`reports/phase7_summary.json`** - machine-readable Phase 7 results.
- **`PHASE8_IMPLEMENTATION.md`** - Phase 8 NGO/UN registry, PageUp adapter, classifier, reporting and compatibility handover.
- **`reports/phase8_summary.json`** - machine-readable Phase 8 results.
- **`PHASE8_RUN29_HOTFIX.md`** - run #29 location-quality and Himalayas taxonomy correction.
- **`reports/phase8_run29_hotfix_summary.json`** - machine-readable run #29 hotfix results.
- **`reports/phase3_summary.json`** - machine-readable Phase 3 test, filter,
  collector and stable-ID results.
- **`reports/phase2_summary.json`** - migration counts, completeness and
  compatibility digests.
- **`scripts/registry.py`** — registry loaders and deterministic compatibility
  generation helpers.
- **`scripts/validate_registry.py`** — cross-file registry validator.
- **`scripts/generate_legacy_configs.py`** — writes or checks the five
  generated compatibility artifacts.
- **`scripts/generate_registry_report.py`** — produces the registry inventory
  report used in CI and handover review.
- **`scripts/validate_feed.py`** - a real, working validator (run it:
  `python3 scripts/validate_feed.py feed.json --taxonomy taxonomy.json`).
  Checks required fields, enum values (including v3's `contract_type` and
  `education_required`), URL validity, ISO-8601 dates, deadline-after-posted
  ordering, years_experience_min/max sanity bounds, and specifically that
  nothing marked `sample` also claims `source.confidence: official`.
- **`scripts/tests/`** - 223 offline tests covering shared extraction logic,
  source governance, taxonomy mapping, Phase 2 enrichment, Android compatibility,
  reports, mobility filtering, Phase 3 collection isolation and HTTP policy, the
  public filters, Phase 4 multilingual/location coverage, a 582-case
  location corpus, Phase 6's 99-case investment/DFI corpus, and saved-response fixtures and adapter tests across the collector registry. Run them with
  `python3 -m pytest scripts/tests -q`.

## Why source-transparent matters here

Spec §14 is explicit that the app must not present aggregated/scraped info as
official unless it comes directly from an official source, and must never
fabricate data. `config/source_registry.json` is where that decision actually
gets made; `sources.json` is its generated compatibility view. Every collector
you add to `refresh_feed.py` should call
`builder.confidence_for_domain(...)` rather than deciding confidence ad hoc
per listing.

## Stable IDs matter

`id` must stay the same across regenerations for the same underlying listing
(spec §24.4: hash of source URL + title is a reasonable scheme) - it's what
lets a user's save, triage state, and reminder survive a feed refresh.
Changing the ID scheme is a breaking change for every device that has saved
anything.

## GitHub Pages (shareable live site)

`docs/index.html` is a self-contained, branded, front-end job board built
from the current `feed.json` by `scripts/site/build_site.py`. The refresh
workflow regenerates it automatically on every scheduled run, so once Pages
is switched on, the live URL always reflects the current feed - no separate
deploy step needed beyond the one-time setup below.

**One-time setup (do this once, in the GitHub UI):**
1. Go to the repo on GitHub &rarr; **Settings &rarr; Pages**
2. Under **Build and deployment &rarr; Source**, choose **Deploy from a branch**
3. Under **Branch**, choose **main** and **/docs**, then **Save**
4. GitHub will show a URL shortly after, typically
   `https://dansamuka.github.io/kazi-sasa-feed/`

That's it - no further action needed. Every time the refresh workflow runs
(3&times; daily, or manually via **Actions &rarr; Run workflow**), it commits a
fresh `docs/index.html`, and GitHub Pages picks up the change automatically
within a minute or two.

`docs/.nojekyll` disables GitHub's default Jekyll processing for this
folder - `docs/index.html` is a plain static file with embedded JSON data,
and Jekyll's templating could otherwise misinterpret data if a job posting's
text ever happened to contain double-curly-brace template syntax. No content
in the file depends on Jekyll in any way, so disabling it is pure safety
with no downside. (This exact failure mode is why this sentence avoids
writing out the literal characters - Jekyll processes this very README if
Pages is ever pointed at the repo root instead of docs/, and choked on them
the first time this was written literally.)

## Setup

```bash
pip install -r requirements.txt
python3 scripts/validate_registry.py                              # all Phase 1 registry references
python3 scripts/generate_legacy_configs.py --check                    # generated compatibility files current
python3 scripts/validate_sources.py sources.json                      # generated confidence view
python3 -m pytest scripts/tests -q                                    # 287 tests, no network needed
python3 scripts/generate_registry_report.py                           # registry inventory report
python3 scripts/validate_feed.py feed.json --taxonomy taxonomy.json --fail-on-warnings
python3 scripts/generate_reports.py                                   # coverage + health + manifest + dedup + gates
python3 scripts/refresh_fx.py --out currency_rates.json               # needs network, no auth
python3 scripts/refresh_feed.py --list-collectors                     # inspect Phase 3 registry
python3 scripts/refresh_feed.py --only-source jobicy --out tmp/jobicy.json  # independently diagnose one source
python3 scripts/coverage_gates.py --feed feed.json --config config/coverage_gates.json --fail-on-errors
python3 scripts/refresh_feed.py --out feed.json                       # live full refresh
```

## Known limitations, honestly stated

- **Bare "Remote" postings (no country, no region signal) are no longer
  assumed relevant to a Kenyan applicant.** Tightened 2026-07-11 after real
  data showed the old default (treat any unspecified "Remote" role as
  Kenya-relevant) was drowning out genuinely-located African postings under
  a flood of ambiguous US-tech "Remote" listings - 404 of 609 opportunities
  in that snapshot were bare-Remote roles from Ramp/Stripe/Notion/GitLab/
  Linear/PostHog with no actual African signal. Now requires an explicit
  positive signal ("Remote - Africa", "Remote (EMEA)", "Remote - Global",
  etc.) before counting a bare-Remote posting as relevant. This meaningfully
  shrinks total feed size but the remaining set is honestly relevant rather
  than optimistically included - see `_REMOTE_POSITIVE_SIGNAL` in
  `collectors/_common.py`. Only affects Greenhouse/Lever/Ashby/Pinpoint,
  which parse free-text locations; Adzuna and ReliefWeb build their location
  fields from structured API data and are unaffected.
- **"Remote (US)"/"Remote-US" style postings were leaking through despite
  the above fix - now closed.** Two compounding bugs, found from real leaked
  examples in a live feed (2026-07-11): (1) country detection used naive
  substring matching, which never caught short 2-letter codes like "US"/"UK"
  (neither "usa" nor "united states" is a substring of "us"), so these
  postings' location text was silently going undetected as any country at
  all; (2) `collectors/ashby.py` had an override that forced
  `is_remote_from_kenya=True` whenever Ashby's own `isRemote` flag was true
  and no country had been detected - which, combined with bug (1), let every
  undetected "Remote (US)" posting through as if it were genuinely relevant.
  Fixed both: country detection now uses word-boundary regex matching against
  a canonical-name map (catches "US"/"UK" correctly without false-positiving
  on "campus"/"focus"/etc.), and the Ashby override was removed entirely -
  trust `parse_location()`'s own logic instead of second-guessing it.
  A non-African-located posting is now kept only when the description contains
  **role-specific** international mobility evidence. Generic company-wide
  sponsorship or immigration boilerplate no longer makes every vacancy on an
  employer board Africa-relevant.
- **Industry/years-of-experience/education/contract-type are heuristic
  extractions** from unstructured text (except where a source gives a clean
  structured field, like Lever's `categories.level`). They will sometimes be
  null when a human would spot the signal, or occasionally wrong. This is an
  accepted tradeoff, not a bug to chase to zero - see SCHEMA.md.
- **Adzuna covers only South Africa within Africa.** Phase 5 searches multiple
  role lanes, but geographic scope remains South Africa. Other regions come from
  employer boards, ReliefWeb, UN Talent, and future sources.
- **`currency_rates.json` isn't consumed yet.** The infrastructure (fetch,
  normalise) is built and tested, but no collector calls `normalise_salary()`
  on its own output yet - a follow-up task, not a bug.
- **UN Talent is optional and access-controlled.** Configure the approved JSON/RSS
  URL in `UNTALENT_FEED_URL`; the collector cleanly skips when absent. No Tier 3
  scrapers are implemented. See `LEGAL_NOTES.md` for excluded/deferred sources.

### Safe deployment and publication verification

Use `deploy.bat` from the extracted repository folder. It now performs a **source-only deployment**: it clones the current repository, preserves the live `feed.json`, generated Pages site and runtime reports, overlays the new source package, and pushes normally. It does not force-push the bundled offline snapshot.

The refresh workflow then publishes in two stages:

1. It upgrades the current last-known-good feed and Pages site to schema v3.8 and commits that bootstrap immediately.
2. It runs the long live collection into `.runtime/` and promotes the result only after clean validation.

If an upstream collector fails, the Phase 11 bootstrap remains public rather than leaving Pages on v3.6. The site clearly labels this state as last-known-good data and retains the original source-data timestamp. `scripts/verify_published_output.py` continues to reject schema mismatches, missing required profiles, count mismatches and a site built from a different feed.

See [`PHASE11_PUBLICATION_CORRECTION.md`](PHASE11_PUBLICATION_CORRECTION.md).


## Phase 5 run #24 hotfix

See [`PHASE5_RUN24_HOTFIX.md`](PHASE5_RUN24_HOTFIX.md) for the corrected location-quality gate and live taxonomy mappings.


## Phase 8 run #29 hotfix

See [`PHASE8_RUN29_HOTFIX.md`](PHASE8_RUN29_HOTFIX.md) for the official-location-pending quality bucket, targeted multilingual duty-station extraction, and live Himalayas taxonomy mappings.

## Phase 8.1 and Phase 9

Phase 8.1 hardens official NGO, UN and development collection by rejecting generic career/policy pages, preserving valid listing titles when detail pages return anti-bot titles, separating employer context from role function, and filtering unrelated non-African official vacancies.

Phase 9 adds the first government/public-service source pack. Kenya PSC, Tanzania PSRS/Ajira and South Africa DPSA are enabled. Uganda PSC and Rwanda MIFOTRA are registered but intentionally disabled until stable, permitted public endpoints are verified. See [`PHASE8_1_PHASE9_IMPLEMENTATION.md`](PHASE8_1_PHASE9_IMPLEMENTATION.md).

A Phase 9 publication must pass the `--require-phase9` and `--require-phase9-site` guards and generate `reports/government_coverage_report.json`.

## Kenya public institutions and Phase 11 multinationals

The feed is now version **3.8**. The authoritative registries include **60 Kenyan public institutions** across all requested regulatory, development-finance, university, service-commission, utility and state-enterprise categories, plus **100 priority multinational employers** across 17 sectors.

New public adapters cover Workday, SmartRecruiters and Workable, with controlled official-careers-page fallbacks. The board includes filters for Kenya public institutions, public-institution category, multinationals and multinational sector. See [`PHASE10_KENYA_PHASE11_IMPLEMENTATION.md`](PHASE10_KENYA_PHASE11_IMPLEMENTATION.md).

A Phase 11 publication must pass `--require-phase11` and `--require-phase11-site` and must generate both `reports/kenya_public_institutions_report.json` and `reports/multinational_coverage_report.json`.

## Phase 11 publication correction

The source-only deploy, last-known-good bootstrap, legacy DFI/NGO classification repair and staged live-refresh promotion are documented in [`PHASE11_PUBLICATION_CORRECTION.md`](PHASE11_PUBLICATION_CORRECTION.md).

## Africa and eligibility certification

The feed now separates Africa relevance from applicant eligibility. The main
site defaults to the certified/conditional-access subset only. Africa-relevant
roles whose applicant access is still unverified remain available through the
**Certification scope** filter, while `certified_feed.json` contains only roles
with meaningful access evidence. Use the **Certification scope**,
**Africa relevance**, and **African applicant access** filters to inspect the
broader index. Known non-African roles without an Africa remit are rejected and
audited in `reports/rejected_records.json`.


## Phase 12 run #38 compatibility fix

The repository-root `feed.json` is a mutable live publication artifact. Historical 204-record stable-ID and Android compatibility assertions now use `scripts/tests/fixtures/legacy_packaged_feed.json`, while Phase 12 certification is validated by migrating the current root feed in memory. This allows the same test suite to pass against both the bundled snapshot and the live repository feed.
