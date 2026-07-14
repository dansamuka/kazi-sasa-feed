# Phase 8.1 quality hotfix and Phase 9 government sources

Implemented on 13 July 2026.

## Phase 8.1 quality corrections

The official NGO, UN, DFI and development-source adapters now apply a vacancy-quality gate before publication.

- Valid listing titles are preserved when a detail page returns an anti-bot or generic browser title such as `JavaScript is disabled`.
- Career landing pages, policy pages, equal-opportunity pages, military-veteran pages, organisation-name-only links and other navigation content are rejected as vacancies.
- Generic HTML pages must contain vacancy-specific evidence such as JobPosting JSON-LD, a requisition/reference, a vacancy-specific URL, dates plus job sections, or multiple job-detail sections.
- Organisation registry defaults are retained as `source_context_specialisations`; they no longer automatically become the vacancy's functional category.
- Generic multilateral institutions are no longer treated as NGO/UN employers solely because of their institution type. UN agencies remain in the NGO/UN discovery group; DFIs and development banks remain in their Phase 7 institution group.
- Support functions at NGOs and UN agencies remain `institutional_support` unless the title or job-specific text supports a programme track.
- Known non-African official duty stations are excluded unless the vacancy has an explicit Africa remit or the source is deliberately configured to allow them. Missing-location official vacancies remain subject to the existing `official_location_pending` quality cap.
- Official-page location extraction remains restricted to structured or labelled duty-station evidence, avoiding false locations inferred from programme descriptions.

## Phase 9 government/public-service source pack

Five Wave 1 portals are registered. Three have active collectors in this release:

| Country | Portal | Status | Collection method |
|---|---|---|---|
| Kenya | Public Service Commission | Active | Official HTML vacancy table |
| Tanzania | Public Service Recruitment Secretariat / Ajira | Active | Official advert index and individual PDF parsing |
| South Africa | DPSA Public Service Vacancy Circular | Active | Latest official circular page and department PDF parsing |
| Uganda | Public Service Commission | Registered, disabled | Automated clients currently receive HTTP 403; no stable permitted endpoint was verified |
| Rwanda | MIFOTRA e-Recruitment | Registered, disabled | JavaScript application; no stable public vacancy API was verified offline |

The disabled entries are explicit in `config/public_portals.json` and the generated registry report. They can be enabled later without changing the feed schema once permitted, stable endpoints are verified.

## Structured government fields

Every opportunity now contains an additive `government_profile`. Government vacancies can populate:

- advert reference;
- public-service grade;
- salary scale;
- number of positions;
- citizenship requirement and eligible nationalities;
- application method and form URL;
- internal-only status;
- county/province/region restriction;
- source circular or advert document URL.

Government jobs use stable IDs based on country, portal, advert reference, title and application URL.

## Collectors and infrastructure

Added:

- `scripts/collectors/government_common.py`
- `scripts/collectors/government_html.py`
- `scripts/collectors/government_pdf.py`
- `scripts/collectors/government_circular.py`
- `scripts/migrate_phase9.py`
- `scripts/tests/test_phase8_1.py`
- `scripts/tests/test_phase9.py`

The government collectors run through the Phase 3 isolated collector runner, shared HTTP client, retry/backoff, cache, timeout and structured health reporting.

PDF parsing uses `pypdf`. Tanzania parsing recognises numbered `Nafasi` headings, Swahili month names, position counts, salary grades and citizenship language. DPSA parsing separates individual `POST` records and extracts references, salary, centre, requirements and closing dates.

## Feed and site

- Feed version: `3.7`
- New metadata: `official_vacancy_quality_version`, `government_source_pack_version`, `government_schema_version`
- New website filters: Government/public service and public-service grade
- New report: `reports/government_coverage_report.json`
- New registry report fields: active/disabled government portals and government collector adapters

## Validation

The packaged snapshot is migrated rather than freshly fetched from the three government sites. Live records will be added by the first successful GitHub Actions refresh.
