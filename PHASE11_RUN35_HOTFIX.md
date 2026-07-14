# Phase 11 — Refresh run #35 hotfix

This hotfix addresses the exact live validation failures from GitHub Actions run #35.

## Corrections

- Kenya PSC ASP.NET `javascript:__doPostBack(...)` controls are no longer emitted as application URLs.
- A real relative HTTP(S) detail link is preferred when present.
- When a row contains only a browser postback control, the opportunity points to the official PSC application portal.
- Government vacancies now use the canonical `public_sector` industry rather than the non-canonical `government_public_sector` value.
- New Himalayas healthcare, referral and home-health labels are mapped to controlled specialisations.
- Jobicy's broad `Healthcare & Medical` label maps to the healthcare industry but is deliberately ignored as a role specialisation.

## Safety behavior

The advert reference remains part of each government opportunity's stable ID, so multiple PSC vacancies can safely share the official portal URL without being collapsed.
