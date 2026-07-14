# Phase 5 CI hotfix — live source date and taxonomy resilience

This patch addresses the live-data failures reported by GitHub Actions run #23.
It does not change the Phase 5 feed schema version or current Android contract.

## Fixed failures

### Recruitee timestamps

Recruitee live boards returned timestamps such as:

```text
2026-07-06 07:30:06 UTC
```

The collector now converts these to the feed contract:

```text
2026-07-06T07:30:06Z
```

The shared temporal normaliser also accepts ISO timestamps, date-only values,
RFC-style dates and Unix seconds/milliseconds.

### Impossible Adzuna deadlines

One Adzuna description contained a closing date earlier than the job's posting
date. Description extraction is best-effort and can encounter stale template
text. The pipeline now retains the job, removes the impossible deadline, resets
`deadline_confidence` to `unknown`, and records:

```json
{"data_quality": {"deadline_dropped": "before_posted_at"}}
```

### HTML-escaped Jobicy taxonomy

Source category values are now HTML-decoded before mapping. The following live
values have explicit mappings:

- `Legal & Compliance` → `compliance`
- `Finance & Accounting` → `general_finance`
- `Product & Operations` → `product_management`

RemoteOK's `dev` and `photoshop` tags are mapped, while `digital nomad` and the
overly broad `education` tag are intentionally ignored.

## Regression protection

Five new offline tests reproduce the exact live failure shapes. The complete
suite now contains 187 passing tests.
