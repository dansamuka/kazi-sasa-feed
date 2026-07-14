# Phase 8 — NGO, UN and development source pack

Phase 8 expands the registry and collection framework for NGO, UN, humanitarian and development-sector roles while preserving the existing Android contract.

## Implemented

- Registered 33 priority NGO/UN/development organisations, including existing direct boards and 27 new official sources.
- Added direct-source targets for UN Careers, UNDP, UNICEF, UNECA, African Union, major humanitarian NGOs, global-health organisations, development implementers, TradeMark Africa and FSD Africa.
- Added a PageUp public-career adapter and source-governance record.
- Added `config/ngo_taxonomy.json` with 20 controlled role tracks.
- Added `scripts/classifiers/ngo.py` and a 28-case reviewed regression corpus.
- Added additive `ngo_profile` metadata to every opportunity.
- Added `reports/ngo_coverage_report.json` and Phase 8 fields to the general coverage report.
- Added NGO/UN and NGO/development-track filters to the GitHub Pages board.
- Added Phase 8 feed and site publication guards.

## Classification principle

Organisation context and role relevance are separate. A software engineer or accountant at UNICEF is tagged as an NGO/UN institutional role but is not presented as a humanitarian or programme role. Strong title or canonical-specialisation evidence is required for programme classification.

## Compatibility

- Feed version: 3.6.
- Existing opportunity IDs and ordering are unchanged.
- Existing Android DTO projection is unchanged.
- New fields are additive and ignored by older app versions.
- The packaged feed is migrated offline; newly registered sources populate during live GitHub Actions refreshes.
