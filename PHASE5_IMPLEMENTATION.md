# Phase 5 implementation — public APIs and official feeds

## Status

Complete. Feed schema is **3.3** and remains backward-compatible with Phase 4.
The packaged snapshot contains 204 opportunities because this release did not
perform a live upstream refresh.

## Implemented source expansion

- Added a public Recruitee careers-site collector and five verified registry boards.
- Expanded ReliefWeb from a Kenya-only request to batched coverage of all 54 African countries.
- Added optional UN Talent JSON and RSS ingestion through `UNTALENT_FEED_URL`.
- Expanded Adzuna South Africa into seven role-search lanes, including investment,
  project finance, climate finance, development, NGO, and public-sector terms.
- Increased the executable collector registry from 11 to 13 sources.

## Cross-source quality controls

- Added canonical-URL, exact-ID, and conservative semantic deduplication.
- Employer/institution-official records replace aggregator copies.
- Different cities remain separate.
- Generic employers such as `Unknown Employer` cannot trigger semantic merging.
- Added a machine-readable deduplication report.

## Coverage gates

Publication now enforces baseline regression floors for African regions,
unknown-country share, source concentration, country concentration, and official
application-link counts. Higher Phase 5 targets are reported as warnings so the
current baseline can publish while geographic gaps remain visible.

## Validation

- 187 offline tests
- 13 collector contracts represented in the manifest
- Clean registry validation
- Clean `feed.json` and `seed.json` validation
- Coverage regression gates pass
- Phase 5 publication metadata verified
- Existing 204 opportunity IDs and Android DTO projection preserved

## Runtime configuration

- `RELIEFWEB_APPNAME` enables Africa-wide ReliefWeb collection.
- `UNTALENT_FEED_URL` enables UN Talent JSON/RSS collection.
- `UNTALENT_API_TOKEN` is optional when the supplied endpoint requires it.
- Existing Adzuna credentials continue to enable its South Africa portfolio.

## Scope boundary

Phase 5 adds free/public source adapters, source precedence, deduplication, and
coverage controls. Investment-specific taxonomy and DFI enterprise-platform
adapters remain Phase 6 and Phase 7 work.
