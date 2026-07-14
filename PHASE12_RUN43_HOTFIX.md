# Phase 12 Run #43 Hotfix

Run #43 failed because the safe deployment script correctly preserved the live
`docs/index.html`, while the mobile UI regression test ran before the workflow
rebuilt that page from the new source template. The workflow now rebuilds the
site from the preserved live `feed.json` before running the offline tests.

This preserves live data, exercises the new mobile filter controls against the
current feed, and keeps the later bootstrap and final publication builds intact.
