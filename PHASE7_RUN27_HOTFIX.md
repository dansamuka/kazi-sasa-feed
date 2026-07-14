# Phase 7 run #27 hotfix

This hotfix addresses the live GitHub Actions failure observed in `Refresh feed #27`.

## Root cause

The Phase 7 institution registry used `development_finance` as a default role
specialisation for several DFI sources, but that value had not been registered
in the canonical legacy taxonomy. The official-page collectors copied registry
defaults directly into `categories` and `specialisations`, allowing a registry
configuration mistake to reach the generated feed and fail strict validation.

The same registry audit also found two latent non-canonical defaults:

- `guarantees_political_risk`
- `project_development`

## Corrections

- Added canonical `development_finance` under the `financial_services`
  industry.
- Mapped it to the broad `development_programmes` role family and to the
  `finance`, `development`, and `public_sector` thematic sectors.
- Deliberately did **not** add it as a Phase 6 investment track. A role needs
  title/description evidence to become a genuine investment role.
- Migrated `guarantees_political_risk` to the existing canonical
  `guarantees_risk_insurance` track.
- Migrated `project_development` to the existing canonical
  `upstream_project_development` track.
- Routed all Phase 7 official-source defaults through
  `FeedBuilder.map_specialisations()` before publication.
- Extended registry validation so every configured `default_specialisations`
  value must be canonical.
- Added mappings or intentional ignores for every new Himalayas term observed
  in run #27.

## Regression protection

`test_phase7_run27_hotfix.py` reproduces the run #27 conditions and verifies:

- canonical DFI defaults;
- no false investment classification for generic DFI support roles;
- clean feed validation;
- clean registry validation;
- warning-free handling of the observed Himalayas labels.

The feed contract remains version `3.5`; this is a backward-compatible Phase 7
hotfix.
