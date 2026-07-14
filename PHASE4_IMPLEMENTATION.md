# Phase 4 implementation

## Scope completed

Phase 4 adds the African geographic and multilingual extraction foundation on
top of the Phase 3 registry-driven pipeline.

### Geographic registry

- 54 African countries with ISO-2/ISO-3 codes and canonical regions.
- 155 major cities across all countries.
- 70 selected high-value administrative areas.
- 111 stored city coordinates.
- Country/city/regional aliases across English, French, Portuguese, Arabic and
  Swahili, including accented and Arabic-script forms.
- 582 realistic regression cases covering country, city, alias,
  administrative-area and regional formats.

### Runtime normalisation

`scripts/normalizers/location.py` provides Unicode-preserving matching,
country/city/admin-area resolution, ISO codes, coordinates, source-language
recognition, confidence scoring and machine-readable evidence. It never emits a
country or city without explicit alias, ISO, city or administrative evidence.

### Multilingual extraction

`scripts/normalizers/multilingual.py` and all description-bearing collectors now
support conservative extraction of:

- years of experience;
- contract type;
- required languages;
- explicit application deadlines;
- local, citizenship, work-authorisation and internal-only restrictions;
- remote/hybrid work signals.

Supported posting languages are English, French, Portuguese, Arabic and
Swahili.

### Compatibility

- Feed version: 3.2.
- Opportunity count: 204.
- Stable IDs: unchanged.
- Current Android DTO projection: unchanged for both `feed.json` and
  `seed.json`.
- Phase 4 fields are additive and ignored by current Android builds.

### Quality gates

CI validates the Phase 4 registry, runs the full test suite, checks the
published feed for Phase 4 fields and refuses to publish a stale or incomplete
root feed/site pair.
