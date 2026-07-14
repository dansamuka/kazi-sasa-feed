# Phase 5 GitHub Actions Run #24 Hotfix

This hotfix resolves the coverage-gate failure and remaining taxonomy noise observed in live workflow run #24.

## Coverage-gate correction

Country-neutral opportunities with explicit evidence such as **Remote**, **Worldwide**, **EMEA**, **Africa-wide**, or an international/regional scope are now classified as `location_neutral`. They no longer inflate the unresolved-location rate. Records with neither a country nor explicit country-neutral evidence remain `unknown` and are still subject to the strict 10% regression gate.

The coverage report now publishes `physical_country`, `location_neutral`, and `unresolved` location-resolution counts.

## Taxonomy additions

The live Himalayas, Remotive, and Jobicy labels from run #24 are now either mapped to canonical Kazi Sasa specialisations or intentionally ignored where they represent seniority/broad industry rather than a useful specialisation. Raw labels are never published.

## Compatibility

The feed remains schema version 3.3. No opportunity field or existing ID is changed by this hotfix.
