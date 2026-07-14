# Phase 8 run #29 hotfix

This hotfix addresses the live GitHub Actions failure observed in `Refresh feed #29`.

## Root cause

The Phase 5 location-quality gate placed every vacancy without a canonical country into the same `unresolved` bucket. Phase 7 and Phase 8 added many real vacancies from official DFI, UN, NGO and PageUp career sites. Some of those official sites publish a vacancy-specific detail page but omit the duty station from the listing card or from machine-readable metadata.

That caused the feed's unresolved-location share to rise to 21.5%, even though a material part of the increase consisted of verified official vacancies rather than malformed aggregator records.

The live run also introduced new Himalayas category labels that were not yet mapped or intentionally ignored.

## Corrections

### Targeted official-page location extraction

The official-career extractor now looks for location evidence only in controlled structures:

- schema-like `jobLocation` attributes;
- PageUp-style location elements;
- definition lists and table label/value pairs;
- explicit multilingual labels such as `Duty station`, `Lieu d’affectation`, `Localização`, `مكان العمل`, and `Mahali pa kazi`;
- listing-card context scoped to a single vacancy;
- vacancy titles that explicitly contain a canonical place.

It does not scan an entire programme description for country names, because NGO and multilateral descriptions often mention many countries unrelated to the duty station.

### Separate official-location-pending bucket

Location quality now distinguishes four states:

1. `physical_country`
2. `location_neutral`
3. `official_location_pending`
4. `unresolved`

A record qualifies as `official_location_pending` only when it has:

- a verified organisation;
- an official application link;
- an institution-controlled source;
- a vacancy-specific detail URL;
- a non-generic vacancy title.

This bucket is still capped at 25% of the feed and has a 15% target warning. It is not treated as complete location data.

Commercial aggregators, community sources and unverified vacancies with no location remain in the strict unresolved bucket, which still has a 10% failure threshold.

### Himalayas taxonomy cleanup

Added mappings for the run #29 labels covering:

- full-stack engineering;
- brand leadership;
- graphic/design leadership;
- data, analytics and platform engineering.

Broad labels such as `Tech` and `Automotive` are intentionally ignored rather than published as misleading specialisations.

## Regression protection

`test_phase8_run29_hotfix.py` verifies:

- English and multilingual location-label extraction;
- end-to-end official vacancy location extraction;
- separate handling of official location-pending records;
- continued failure for unresolved aggregator records;
- the cap on official location-pending records;
- warning-free handling of every Himalayas term observed in run #29.

The feed contract remains version `3.6`; this is a backward-compatible Phase 8 hotfix.
