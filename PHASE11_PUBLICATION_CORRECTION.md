# Phase 11 Publication Correction

This release corrects the deployment state where the repository contained Phase 11 source code while GitHub Pages continued serving the last successful Phase 8 feed.

## Changes

- Replaces force-push deployment with a source-only clone/overlay deployment.
- Preserves the current live `feed.json`, generated site, and runtime reports when source code is deployed.
- Adds a Phase 11 bootstrap migration for the existing last-known-good feed before long live collection begins.
- Repairs legacy DFI/NGO source defaults that had been written into role fields.
- Removes invalid generic official-page titles and clearly non-African official roles from migrated legacy feeds.
- Separates schema migration time from the actual source-data timestamp.
- Shows an honest “last-known-good data” banner if a live refresh fails.
- Runs live collection into `.runtime/` and promotes it only after the collector pipeline succeeds.
- Commits the bootstrapped v3.8 feed/site before the long live refresh, so a later collector failure cannot leave Pages on v3.6.
- Retains diagnostic output from failed live refreshes.

## Deployment behavior

`deploy.bat` now invokes `deploy.ps1`, clones the current repository, preserves generated artifacts, overlays the source package, pushes normally, and triggers or opens the refresh workflow. It never force-pushes the bundled offline snapshot.

## Publication guarantees

1. The live feed is upgraded to v3.8 before collection.
2. The Phase 8.1 NGO/DFI classification repair is applied to the existing feed.
3. Phase 9 and Phase 11 profiles and filters are generated immediately.
4. A fresh live feed replaces the bootstrap only if it validates cleanly.
5. If upstream collection fails, the valid Phase 11 bootstrap remains public and is labelled accurately.
