# Phase 7 implementation — DFI and multilateral source pack

Phase 7 adds the first registry-backed DFI and multilateral collection pack to
the Phase 6 feed without changing existing opportunity IDs or Android fields.

## Scope implemented

- Registered 25 priority institutions, bringing the organisation registry to
  51 organisations and 52 source connections.
- Added public-career adapters for Cornerstone/CSOD, SAP SuccessFactors,
  Oracle Candidate Experience, and official HTML/JSON-LD career pages.
- Added conservative generic-page rejection so careers landing pages are not
  published as vacancies.
- Added `institution_profile` to every generated opportunity.
- Added DFI/multilateral and DFI-relevance filters to the static board.
- Added `reports/dfi_coverage_report.json` and Phase 7 publication guards.
- Extended source-health reporting through the existing isolated runner.

## Priority institutions

The registry includes World Bank Group/IFC/MIGA, AfDB, Afreximbank, AFC, TDB,
Africa50, Shelter Afrique Development Bank, African Guarantee Fund, DBSA, IDC,
IsDB, EIB, EBRD, Green Climate Fund, BII, FMO, Proparco, DEG, Norfund,
Swedfund, Finnfund, DFC, PIDG, GuarantCo and InfraCo Africa.

## Compatibility

The migration is additive. It verifies stable ID order and hashes the complete
legacy Android projection before and after enrichment. The packaged snapshot is
an offline 204-record fixture; live source counts are produced by the first
successful GitHub Actions refresh.
