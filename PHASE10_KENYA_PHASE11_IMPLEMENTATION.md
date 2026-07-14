# Kenya Public Institutions + Phase 11 Multinationals

This release extends the Phase 8.1/9 feed with a Kenya-only public-institution source pack and the Phase 11 multinational-employer expansion. It is additive and keeps the current Android DTO contract intact.

## Kenya public-institution registry

`config/kenya_public_institutions.json` contains 60 institutions across all 17 requested categories:

- central bank
- revenue authority
- capital-markets regulator
- insurance regulator
- pensions regulator
- competition authority
- investment-promotion agency
- national development bank
- sovereign/infrastructure fund
- public university
- judicial service
- parliamentary service
- ports
- railways
- electricity utility
- water utility
- major state-owned enterprise

Fifty-nine targets are enabled. The National Infrastructure Fund remains registry-only because the package does not have a verified standalone vacancy portal for it.

## Multinational registry

`config/multinational_targets.json` contains exactly 100 priority multinational employers across 17 sectors and major African cities. Sixty-eight targets are enabled. Disabled records carry an explicit reason and remain available for later endpoint validation.

The source pack introduces public adapters for:

- Workday Candidate Experience
- SmartRecruiters company postings
- Workable apply sites
- controlled official employer career pages

Employer type remains contextual metadata. It does not override the vacancy's actual role family or investment/NGO classification.

## Additive opportunity profiles

Every opportunity now receives:

- `public_institution_profile`
- `multinational_profile`

The feed version is 3.8. No legacy field is removed or renamed.

## Website and reporting

The public board adds filters for:

- Kenya public institutions
- public-institution category
- multinationals
- multinational sector

New reports:

- `reports/kenya_public_institutions_report.json`
- `reports/multinational_coverage_report.json`

## Runtime controls

Registry-driven HTML sources use conservative listing-page extraction with bounded candidate counts and no default detail-page fan-out. Sources without a stable public vacancy surface are disabled rather than fabricated.

## Packaged snapshot

The packaged `feed.json` and `seed.json` are migrated offline snapshots. They contain the new schema profiles but no newly fetched Phase 11 records. The first successful live GitHub Actions refresh will attempt the enabled sources and regenerate reports and the site.
