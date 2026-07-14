# Phase 6 implementation — investment and DFI taxonomy

## Objective

Phase 6 makes investment and development-finance roles a first-class, explainable
classification rather than relying on the broad `financial_services` industry or
the word “investment” appearing anywhere in a vacancy.

The implementation separates:

1. **Role evidence** — title phrases, canonical specialisations and specific job-description evidence.
2. **Institution context** — DFI, development bank, private-equity, venture-capital, asset-management or multilateral employer type.

Institution context can identify valuable institutional experience, but cannot by
itself convert an accountant, engineer, HR professional or administrator into an
investment professional.

## Implemented components

### Authoritative taxonomy

- Added `config/investment_taxonomy.json`.
- Added 26 investment tracks covering investment analysis and operations,
  portfolio management and value creation, PE/VC, project and infrastructure
  finance, climate and blended finance, trade and structured finance, capital
  markets, transaction advisory, origination, syndications, guarantees,
  upstream project development, financial institutions, credit, treasury,
  impact, ESG/safeguards and resource mobilisation.
- Added 21 canonical specialisations to `taxonomy.json`; the total canonical
  specialisation count is now 155.
- Updated `config/role_taxonomy.json` so every canonical specialisation remains
  fully mapped to a role family and thematic sectors.

### Deterministic classifier

- Added `scripts/classifiers/investment.py`.
- Strong title evidence outranks body-text mentions.
- Canonical source taxonomy is accepted as strong evidence.
- Verified investment/DFI institution type raises confidence only after actual
  role evidence is present.
- Accounting, control, payroll, tax, audit and administrative titles are
  protected against false positives.
- Technical, product and project portfolio titles are not confused with
  investment portfolio roles.
- English, French, Portuguese and Arabic title phrases are included.

### Published schema

The feed is now version `3.4`. Every generated opportunity includes:

```json
{
  "investment_profile": {
    "classification": "core_investment",
    "track": "project_finance",
    "canonical_specialisation": "project_finance",
    "confidence": 0.96,
    "evidence": ["title_phrase:project_finance"],
    "negative_evidence": [],
    "dfi_relevance": "adjacent_experience",
    "dfi_confidence": 0.76,
    "is_investment_role": true
  }
}
```

The four classifications are:

- `core_investment`
- `investment_adjacent`
- `institutional_support`
- `not_investment`

DFI relevance is separately classified as:

- `direct_investment`
- `institutional_role`
- `adjacent_experience`
- `none`

### Public website

The GitHub Pages board now exposes:

- **Investment relevance** filter
- **Investment track** filter
- Investment classification, track, DFI relevance and confidence in expanded details
- Investment-track badges on relevant cards

### Reporting and deployment

- Added `reports/investment_coverage_report.json`.
- Coverage reporting now includes investment classification, track, confidence
  and DFI relevance distributions.
- Registry reporting now includes Phase 6 taxonomy and corpus counts.
- GitHub Actions verifies all Phase 6 metadata and every opportunity profile.
- Publication fails when the generated site omits the Phase 6 filters or payload fields.

## Regression corpus

`config/investment_test_cases.json` contains 99 reviewed cases, including:

- All 26 tracks
- French, Portuguese and Arabic titles
- Generic and specialised investment titles
- Canonical-specialisation evidence
- Description evidence within verified DFI/investment institutions
- Accounting and financial-control false positives
- Technology, legal, HR and administration roles at DFIs
- Technical/project/product portfolio false positives

All cases produce the expected classification and track.

## Packaged snapshot results

The packaged 204-record snapshot is intentionally the older offline fixture,
not a fresh copy of the 721-record live feed. After Phase 6 migration it contains:

- 204/204 opportunities with complete `investment_profile` objects
- 1 investment-adjacent role (`treasury`)
- 203 roles classified as not investment
- 27 records with explicit false-positive evidence
- 0 direct DFI investment roles because no DFI source pack has yet been onboarded

The bundled 10-record seed contains one core investment role, two adjacent roles,
two institutional-support roles and five non-investment roles.

The next live scheduled refresh will apply Phase 6 to the full current source set.
Phase 7 remains responsible for onboarding major DFIs and multilaterals.

## Compatibility

- All 204 packaged opportunity IDs and their ordering are unchanged.
- The current Android DTO projection is unchanged.
- Existing `specialisations` are not rewritten by title-based classification.
- `role_family`, `role_subfamily` and `investment_profile` are additive metadata.
- v3.0–v3.3-shaped feeds remain valid because Phase 6 fields are optional for historical snapshots.

## Validation

- 206/206 offline tests pass.
- Registry validation: 0 errors.
- `feed.json`: 0 errors, 0 warnings.
- `seed.json`: 0 errors, 0 warnings.
- Generated compatibility registries are current.
- Workflow YAML, JavaScript and Python syntax checks pass.
- Phase 2, 4, 5 and 6 publication guards pass.
