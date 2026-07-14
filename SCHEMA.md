# feed.json schema

Source of truth: `app/src/main/java/com/kazisasa/app/data/remote/dto/FeedDtos.kt`
in the main Kazi Sasa app repo, and `scripts/validate_feed.py` in this repo
(which enforces this document programmatically). If any of the three
disagree, the Kotlin DTOs win for what the app actually accepts, but
validate_feed.py should be updated to match immediately - a schema doc and a
validator that silently drift apart from the real parser is worse than
having neither.

## Top level

```json
{
  "meta": { ... },
  "profiles": [ ... ],
  "opportunities": [ ... ]
}
```

`profiles` is optional (defaults to `[]`) - only include it if you want to ship
default career profiles with the feed; the app will not overwrite a profile a
user has already customised with the same `id`.

## meta

| field | type | notes |
|---|---|---|
| `feed_version` | string | bump on any breaking schema change |
| `generated_at` | ISO-8601 string | when this file was built |
| `next_expected_update` | ISO-8601 string, nullable | drives the app's staleness UI |
| `opportunity_count` | int | informational; validator warns if it drifts from the real count |
| `source_count` | int | informational |
| `schema_url` | string, nullable | link back to this file |
| `is_sample_data` | bool, default `false` | recommendations doc §20 - set `true` if this *entire* feed is demo/sample content, independent of how the app fetched it |

## opportunities[]

Required: `id`, `title`, `opportunity_type`, `organisation`, `location`, `source`.
Everything else is optional and the app renders around a missing value rather
than breaking (spec §17).

| field | type | allowed values |
|---|---|---|
| `id` | string | stable across regenerations - see README |
| `opportunity_type` | string | `job`, `fellowship`, `grant`, `internship`, `programme` |
| `organisation.type` | string | legacy values remain supported; Phase 2 also permits detailed organisation types such as `dfi`, `development_bank`, `multinational`, `government`, `regulator`, `un_agency`, and others listed in `config/role_taxonomy.json` |
| `location.scope` | string, nullable | `local`, `national`, `regional`, `international` |
| `work_mode` | string, nullable | `onsite`, `hybrid`, `remote_kenya`, `remote_regional`, `remote_global` |
| `seniority` | string, nullable | `entry`, `mid`, `senior`, `leadership` |
| `deadline_confidence` | string | `explicit`, `inferred`, `unknown` |
| `source.confidence` | string | `official`, `aggregated`, `community`, `unverified` |
| `flags[]` | string[] | any of `urgent`, `relocation_worthy`, `ai_relevant`, `hidden_gem`, `eligibility_review`, `sample` |
| `data_quality.deadline_dropped` | string, optional | `before_posted_at` when a stale or unrelated parsed deadline was removed instead of rejecting the entire vacancy |

`flags: ["sample"]` marks one *individual* opportunity as demo content within
an otherwise-live feed - different from `meta.is_sample_data`, which marks the
whole response. **A single opportunity can never carry both `sample` and
`source.confidence: "official"`** - validate_feed.py enforces this; sample
content claiming official provenance is exactly the kind of misleading signal
spec §14 exists to prevent, and it's caught two real instances of this during
this repo's own setup.

`categories` and `skills_required`/`skills_preferred` should use the
canonical `id`s from `taxonomy.json`, not raw source terms - validate_feed.py
warns (doesn't yet hard-fail) when it sees an id that isn't in the taxonomy.

## v3 additions (opportunities[])

Added in the v3 general-search spec. All nullable/optional - a v2 app reading
a v3 feed simply ignores fields it doesn't know about; a v3 app reading an
older v2-shaped opportunity treats every one of these as absent, same as any
other missing optional field (spec §17).

| field | type | notes |
|---|---|---|
| `industry` | string, nullable | single-select, canonical id from `taxonomy.json`'s `industries` list |
| `specialisations[]` | string[] | multi-select, canonical ids from `taxonomy.json`'s `specialisations` list, each tagged to a parent `industry` |
| `years_experience_min` | int, nullable | 0-50, best-effort extraction from description text - see `extract_years_experience()` in `collectors/_common.py` |
| `years_experience_max` | int, nullable | same caveats; `min` must be `<= max` when both present |
| `education_required` | string, nullable | `none`, `secondary`, `diploma`, `bachelor`, `masters`, `phd` - the *highest* qualification mentioned, not necessarily the strict floor |
| `education_field[]` | string[] | best-effort free text (e.g. `"engineering"`, `"economics"`), not a controlled vocabulary - a bonus signal, often empty |
| `languages_required[]` | string[] | lowercase language ids (`english`, `french`, `swahili`, etc.) - only populated when text has clear requirement-context language nearby, not just an incidental mention |
| `contract_type` | string | `permanent`, `contract`, `fixed_term`, `part_time`, `consultant`, `volunteer`, `unknown` - defaults to `unknown` rather than assuming `permanent` |
| `compensation.usd_min` / `compensation.usd_max` | number, nullable | *not yet populated by any collector* - `normalise_salary()` exists and is tested in `_common.py` but isn't wired into `compensation` output yet; a future pass should call it with `currency_rates.json` and add these two fields alongside the existing `min`/`max`/`currency`/`period` |

`years_experience_min`/`max`, `education_required`, `contract_type`, and
`industry` are all heuristic extractions from unstructured text (except
where a source gives a clean structured signal, like Lever's
`categories.level` or a Greenhouse department name that maps cleanly via
`FeedBuilder.map_industry()`). They will sometimes be wrong or absent - that
is an accepted tradeoff per spec §8.2, not a bug to chase to zero. Every
extraction function has unit tests in `scripts/tests/test_common.py`
covering its documented behaviour; extend those tests before changing the
regexes, since false positives here actively mislead the fit engine and
search filters (worse than a missed signal, which just leaves a field null).

All timestamps are ISO-8601 UTC (`2026-07-10T06:00:00Z`). Unrecognised enum
values are not fatal on the app side - it maps them to a safe default and
keeps going (see `enumOrNull` in `OpportunityMappers.kt`) - but
validate_feed.py treats them as hard errors here, because letting a bad enum
value reach the app silently loses a signal the fit engine would otherwise use.

## Phase 2 additive fields (feed version 3.1)

Phase 2 is deliberately additive. No field consumed by the current Android
DTOs was removed or renamed, and the app uses `ignoreUnknownKeys = true`, so
older app builds safely ignore these richer fields. Older v3.0-shaped records
without any Phase 2 field remain valid.

| field | type | notes |
|---|---|---|
| `organisation.id` | string, nullable | Stable ID from `config/organisations.json`; null when the employer is not yet registered. |
| `organisation.type_detail` | string, nullable | Detailed organisation class from `config/role_taxonomy.json`; legacy `organisation.type` is preserved. |
| `organisation.registry_managed` | bool | Whether the organisation was matched to the authoritative registry. |
| `location.city` | string, nullable | Canonical city from `config/african_locations.json`. |
| `location.country_code` | string, nullable | Uppercase ISO-2 country code. |
| `location.country_canonical` | string, nullable | Canonical country name; the legacy `location.country` value is preserved. |
| `location.region_canonical` | string, nullable | Canonical African region. |
| `location.normalisation_confidence` | number | Confidence in `[0,1]`; no guessed city/country is emitted when evidence is insufficient. |
| `role_family` | string, nullable | High-level family from `config/role_taxonomy.json`. |
| `role_subfamily` | string, nullable | Canonical specialisation ID from `taxonomy.json`. |
| `thematic_sectors[]` | string[] | Controlled thematic tags from `config/role_taxonomy.json`. |
| `eligibility.status` | string | `eligible`, `likely_eligible`, `uncertain`, `local_only`, `citizenship_restricted`, `internal_only`, or `ineligible`. |
| `eligibility.confidence` | number | Evidence confidence in `[0,1]`; not a guarantee that an applicant qualifies. |
| `eligibility.citizenship_required` | bool, nullable | True only when explicit evidence is detected; null means unknown, not false. |
| `eligibility.eligible_nationalities[]` | string[] | Explicitly stated nationalities when extractable. |
| `eligibility.work_authorisation_required` | bool, nullable | True only when the listing explicitly requires existing work authorisation. |
| `eligibility.evidence[]` | string[] | Machine-readable reasons supporting the status. |
| `source.id` | string, nullable | Stable source-governance ID from `config/source_registry.json`. |
| `source.kind` | string, nullable | Source class such as `employer_ats` or `commercial_aggregator`. |
| `source.registry_managed` | bool | Whether the source was matched to the authoritative registry. |

The validator is strict when these fields are present but does not require them
for older snapshots. `scripts/migrate_phase2.py` enriches existing snapshots and
verifies that the legacy Android DTO projection has not changed.

## currency_rates.json (v3)

Separate file, refreshed daily by `scripts/refresh_fx.py` against Frankfurter
(`api.frankfurter.dev` - free, no key, ECB daily reference rates). Shape:

```json
{
  "generated_at": "2026-07-11T06:00:00Z",
  "source": "https://api.frankfurter.dev",
  "rates_to_usd": { "USD": 1.0, "KES": 0.0067, "ZAR": 0.055, ... }
}
```

`rates_to_usd[X]` is "1 unit of currency X, in USD" - already inverted from
Frankfurter's own USD-base response so callers don't have to. Not every
African currency is covered (Frankfurter tracks the ~30 ECB-referenced major
currencies) - a missing currency means `normalise_salary()` returns
`(None, None)` rather than guessing, same principle as everywhere else in
this pipeline.

## profiles[]

See spec §25 / `ProfileDto` in `FeedDtos.kt` - `weights` fields are all floats,
nominally in `[0, 1]`, one per fit dimension listed in spec §8.2.

## Phase 4 additive fields (feed version 3.2)

Phase 4 remains additive and preserves every current Android-consumed field.
The current app safely ignores the following metadata until its DTOs expose it.
Older 3.0/3.1 records remain valid.

### `meta`

| field | type | notes |
|---|---|---|
| `supported_languages[]` | string[] | Exact Phase 4 extraction set: `en`, `fr`, `pt`, `ar`, `sw`. |
| `location_registry_version` | string | Version of `config/african_locations.json`; currently `2.0`. |

### `opportunities[].location`

| field | type | notes |
|---|---|---|
| `country_iso3` | string, nullable | Uppercase ISO-3 code when explicit evidence resolves an African country. |
| `admin_area` | string, nullable | Canonical selected province/state/county/region where matched. |
| `coordinates` | object, nullable | Canonical city point as `{lat, lon}`; never geocoded or guessed at runtime. |
| `normalisation_evidence[]` | string[] | Evidence such as `explicit_country_alias`, `explicit_city_alias`, or `country_inferred_from_unique_city`. |
| `matched_location_alias` | string, nullable | Registry alias that produced the strongest match. |
| `location_language` | string | Detected source language: `en`, `fr`, `pt`, `ar`, or `sw`. |
| `is_african` | bool | Whether an explicit African country or regional alias was matched. |

### `opportunities[].eligibility`

| field | type | notes |
|---|---|---|
| `detected_language` | string | Language used for multilingual eligibility extraction. |

Phase 4 also expands the existing legacy extraction fields without changing
their types. `years_experience_min/max`, `languages_required`, `contract_type`,
`work_mode`, `deadline`, `deadline_confidence`, and structured eligibility can
now be extracted conservatively from English, French, Portuguese, Arabic and
Swahili text. Explicit deadlines embedded in descriptions are used only when a
recognised deadline label and a valid date occur together.


## Phase 5 additive metadata (feed version 3.3)

Phase 5 preserves the complete v3.2 opportunity shape and current Android DTO
projection. It adds publication metadata used by operations and CI:

| field | type | notes |
|---|---|---|
| `meta.source_expansion_version` | string | Public-source expansion layer; currently `1.0`. |
| `meta.deduplication_version` | string | Cross-source precedence/deduplication rules; currently `2.0`. |

No opportunity field was removed or renamed. Cross-source duplicate handling is
performed before publication using exact IDs, canonical URLs, and conservative
organisation/title/location evidence. Employer or institution-official records
win over aggregator copies. Generic labels such as `Unknown Employer` are never
used as semantic identity evidence.

The following operational artifacts accompany the feed but are not consumed by
the Android DTOs:

- `reports/deduplication_report.json`
- `reports/coverage_gate_report.json`
- `reports/collector_manifest.json`
- `reports/source_health.json`


## Phase 6 additive investment metadata (feed version 3.4)

Phase 6 preserves the complete v3.3 opportunity shape, stable IDs and current
Android DTO projection. Every newly generated opportunity includes an
`investment_profile` object. Institution type is contextual evidence only; it
does not by itself make a vacancy an investment role.

### Feed metadata

| field | type | notes |
|---|---|---|
| `meta.investment_taxonomy_version` | string | Investment track registry version; currently `1.0`. |
| `meta.investment_classifier_version` | string | Deterministic classifier version; currently `1.0`. |

### `investment_profile`

| field | type | notes |
|---|---|---|
| `classification` | string | `core_investment`, `investment_adjacent`, `institutional_support`, or `not_investment`. |
| `track` | string/null | One of the 26 canonical Phase 6 investment tracks. |
| `canonical_specialisation` | string/null | Canonical `taxonomy.json` specialisation associated with the selected track. |
| `confidence` | number | Classifier confidence from 0 to 1. |
| `evidence[]` | string[] | Machine-readable positive evidence, such as a title phrase or canonical specialisation. |
| `negative_evidence[]` | string[] | False-positive controls applied, such as accounting/control or project-portfolio evidence. |
| `dfi_relevance` | string | `direct_investment`, `institutional_role`, `adjacent_experience`, or `none`. |
| `dfi_confidence` | number | DFI relevance confidence from 0 to 1. |
| `is_investment_role` | boolean | True only for core or investment-adjacent roles with sufficient role evidence. |

When `is_investment_role` is true, the additive `role_family` is `investment`
and `role_subfamily` is the track's canonical specialisation. Existing
`specialisations` and every current Android-consumed field remain unchanged.


## Phase 7 additive institution metadata (feed version 3.5)

Phase 7 preserves the v3.4 opportunity shape and adds registry-backed
DFI/multilateral context. Institution type is independent from
`investment_profile`: a technology, legal or administrative vacancy at a DFI
remains a non-investment role even though it is valuable institutional
experience.

### Feed metadata

| field | type | notes |
|---|---|---|
| `meta.dfi_source_pack_version` | string | Priority DFI/multilateral registry version; currently `1.0`. |
| `meta.enterprise_adapter_version` | string | Public enterprise-career adapter contract; currently `1.0`. |

### `institution_profile`

| field | type | notes |
|---|---|---|
| `is_dfi_or_multilateral` | boolean | True for a registry-backed DFI, development bank, multilateral or investment institution. |
| `institution_type` | string | Canonical organisation type from `config/role_taxonomy.json`. |
| `registry_id` | string/null | Stable organisation registry identifier. |
| `source_pack` | string/null | Source-pack identifier; Phase 7 priority institutions use `phase7_dfi_multilateral`. |
| `phase7_priority_institution` | boolean | True when the employer is one of the 25 Phase 7 priority institutions. |

The new object is additive and ignored by older Android parsers configured to
ignore unknown keys.


## Phase 8 additive NGO/UN metadata (feed version 3.6)

Phase 8 preserves the v3.5 opportunity shape and adds an `ngo_profile` object
for every opportunity. The profile separates employer context from role
classification: a support-function job at an NGO remains an institutional role,
while a programme role can be recognised from title and canonical taxonomy
evidence even outside a registered NGO.

### `ngo_profile`

| field | type | notes |
|---|---|---|
| `is_ngo_or_un` | boolean | True for registered NGOs, UN agencies, foundations and development implementers. Generic multilaterals and development banks remain in the Phase 7 institution profile unless separately registered as UN agencies. |
| `organisation_group` | string | `ngo`, `un_agency`, `regional_or_multilateral`, `foundation`, `development_implementer`, `ngo_or_development`, or `other`. |
| `classification` | string | `humanitarian`, `development`, `technical_programme`, `institutional_support`, or `not_ngo_un`. |
| `track` | string/null | One of the 20 controlled tracks in `config/ngo_taxonomy.json`. |
| `canonical_specialisation` | string/null | Canonical taxonomy specialisation supporting the track. |
| `confidence` | number | 0–1 classification confidence. |
| `evidence` | string[] | Positive title, taxonomy and institution evidence. |
| `negative_evidence` | string[] | Support-function or false-positive evidence. |
| `is_programme_role` | boolean | True only when the role itself has programme/technical evidence. |
| `registry_id` | string/null | Stable organisation-registry identifier. |
| `source_pack` | string/null | Phase 8 priority organisations use `phase8_ngo_un_development`. |
| `phase8_priority_organisation` | boolean | True for the registered Phase 8 source pack. |

## Phase 8.1 official-vacancy quality contract and Phase 9 government metadata (feed version 3.7)

Phase 8.1 does not remove any existing opportunity field. It strengthens source acceptance and records registry defaults as contextual hints rather than treating them as vacancy-level role evidence. Known non-African official duty stations are excluded unless the vacancy explicitly has an Africa remit or the source opts in to international roles.

### Feed metadata

| field | type | notes |
|---|---|---|
| `meta.official_vacancy_quality_version` | string | Official title, vacancy-evidence and Africa-scope quality contract; currently `1.1`. |
| `meta.government_source_pack_version` | string | Wave 1 government portal registry and collector contract; currently `1.0`. |
| `meta.government_schema_version` | string | `government_profile` schema version; currently `1.0`. |

### `government_profile`

Every opportunity has this additive object. Fields are null/false for non-government vacancies.

| field | type | notes |
|---|---|---|
| `is_government_or_public_service` | boolean | True for registry-backed government or public-service vacancies. |
| `institution_type` | string | Canonical organisation type. |
| `registry_id` | string/null | Stable organisation-registry ID. |
| `source_pack` | string/null | Phase 9 sources use `phase9_government_wave1`. |
| `phase9_priority_portal` | boolean | True for a registered Wave 1 portal. |
| `advert_reference` | string/null | Official advert/post reference. |
| `public_service_grade` | string/null | Grade or job scale stated by the source. |
| `salary_scale` | string/null | Published salary or government salary scale. |
| `number_of_positions` | integer/null | Number of advertised posts. |
| `citizenship_required` | boolean/null | Whether citizenship is explicitly required or portal-wide. |
| `eligible_nationalities` | string[] | ISO-2 nationalities where known. |
| `application_method` | string/null | Portal, form or department application instructions. |
| `application_form_url` | string/null | Official application form/portal. |
| `internal_only` | boolean | True for internal-only adverts. |
| `county_or_region_requirement` | string/null | Geographic eligibility restriction. |
| `source_document_url` | string/null | Official circular/PDF containing the vacancy. |

## Kenya public institutions and Phase 11 multinationals (feed version 3.8)

Version 3.8 is additive. Every generated opportunity includes both profiles, including false-valued profiles for records outside the new source packs.

### `public_institution_profile`

| Field | Type | Meaning |
|---|---|---|
| `is_kenya_public_institution` | boolean | True only for a registry-managed Kenyan public institution. |
| `category` | string/null | One of the 17 controlled Kenya public-institution categories. |
| `registry_id` | string/null | Stable organisation registry identifier. |
| `source_pack` | string/null | New records use `phase10_kenya_public_institutions`. |
| `country_code` | string/null | `KE` for a matched Kenyan public institution. |

### `multinational_profile`

| Field | Type | Meaning |
|---|---|---|
| `is_multinational` | boolean | Whether the employer is classified as a multinational. |
| `sector` | string/null | Controlled Phase 11 multinational sector. |
| `registry_id` | string/null | Stable organisation registry identifier. |
| `source_pack` | string/null | Priority targets use `phase11_multinationals`. |
| `phase11_priority_employer` | boolean | True for the 100-employer Phase 11 target registry. |
| `african_city_footprint` | array[string] | Registered major African cities for coverage analysis. |

### Feed metadata

Version 3.8 adds:

- `kenya_public_institutions_version: "1.0"`
- `multinational_source_pack_version: "1.0"`
- `multinational_adapter_version: "1.0"`

## Africa relevance and African-applicant access certification

Every generated opportunity includes two independent profiles.

### `africa_relevance`

This describes the geographic relationship of the vacancy to Africa. It does
not claim that an African applicant is eligible.

```json
{
  "status": "africa_based_confirmed",
  "confidence": 0.99,
  "evidence": ["physical_duty_station_in_africa"],
  "certification_level": "certified",
  "default_visible": true,
  "known_country_code": "KE",
  "known_country_name": "Kenya"
}
```

Valid statuses are:

- `africa_based_confirmed`
- `africa_regional`
- `remote_confirmed_open_to_africa`
- `africa_remit_non_african_location`
- `official_location_pending`
- `global_access_unconfirmed`
- `non_african`
- `unresolved`

Known non-African duty stations without an explicit Africa remit are rejected
from the published Africa feed and retained in `reports/rejected_records.json`.

### `african_applicant_access`

This describes what the source actually proves about access for African
applicants. An African duty station alone is not eligibility evidence.

```json
{
  "status": "confirmed_specific_african_nationality",
  "confidence": 0.99,
  "evidence": ["structured_government_citizenship_requirement"],
  "evidence_strength": "structured_source",
  "eligible_nationalities": ["KE"],
  "citizenship_required": true,
  "work_authorisation_required": null,
  "certification_level": "certified"
}
```

Valid statuses are:

- `confirmed_any_african_national`
- `confirmed_specific_african_nationality`
- `confirmed_international_recruitment`
- `likely_open`
- `work_authorisation_required`
- `local_only`
- `internal_only`
- `unknown`
- `not_open`

Structured government citizenship fields take precedence over text inference.
The legacy `eligibility` object remains for Android compatibility and is
produced from this profile.

### Certified subset

`certified_feed.json` contains only opportunities with confirmed or conditional
Africa relevance and meaningful applicant-access evidence. `feed.json` remains
the broader audited index. The public board defaults to the certified/conditional-access subset. Users may explicitly opt into Africa-relevant roles with unverified applicant access or the broader location-pending index.
