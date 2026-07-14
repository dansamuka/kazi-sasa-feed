# Legal and ToS notes per source

Per spec §0.4: every source in this pipeline must fall into one of (1) a
public documented API, (2) a public RSS/Atom feed intended for redistribution,
or (3) a direct partnership. This file tracks the actual basis for each
source currently wired into `scripts/collectors/`, so that basis is checked
and recorded once, not re-litigated per pull request.

## Tier 1 — Public APIs (implemented)

### ReliefWeb (`collectors/reliefweb.py`)
- **Basis:** Public documented API, https://apidoc.reliefweb.int/
- **Auth:** Pre-approved `appname` required as of 1 Nov 2025 (request via the
  form linked from the docs page above)
- **ToS position:** Explicitly built for third-party consumption; UN OCHA
  publishes and maintains developer documentation for exactly this use case.
- **Collection pattern:** Phase 5 batches the 54 African ISO-3 country filters
  into a small number of paginated requests and uses the shared retry, throttle,
  and cache layer.

### Greenhouse (`collectors/greenhouse.py`)
- **Basis:** Public, unauthenticated per-company Job Board API,
  https://developers.greenhouse.io/job-board.html
- **Auth:** None required for GET endpoints (Greenhouse's own docs: "Job
  Board data is publicly available, so authentication is not required for
  any GET endpoints")
- **ToS position:** Explicitly documented for third-party integration,
  including custom job boards and job aggregators.
- **Rate limits:** Not documented as constrained; this collector fetches
  once per configured company per run (currently ~30 companies).

### Lever (`collectors/lever.py`)
- **Basis:** Public Postings API, https://github.com/lever/postings-api
  (Lever's own repo, explicitly documents this endpoint for third-party use)
- **Auth:** None
- **ToS position:** Lever's own docs state "all job postings in the
  published state are publicly viewable. These jobs may be scraped by third
  parties." - the most explicit permission of any source here.

### Ashby (`collectors/ashby.py`)
- **Basis:** Public Job Postings API,
  https://developers.ashbyhq.com/docs/public-job-posting-api
- **Auth:** None for the posting-api endpoint
- **ToS position:** Ashby's own docs describe this endpoint as intended for
  "partner job feeds (LinkedIn, Indeed, Otta, Built In, ZipRecruiter,
  Levels.fyi)" - explicitly built for this exact use case.


### Recruitee (`collectors/recruitee.py`) — added Phase 5
- **Basis:** Public unauthenticated Careers Site API, documented by Recruitee.
- **Auth:** None for published offers.
- **ToS position:** The endpoint is intended to power public careers pages and
  third-party careers-site integrations. Collection is per configured employer.

### UN Talent (`collectors/untalent.py`) — added Phase 5
- **Basis:** JSON/RSS access offered for fair use with attribution.
- **Auth:** Access URL must be requested/configured as `UNTALENT_FEED_URL`; an
  optional bearer token is supported where supplied.
- **ToS position:** The collector is disabled unless an approved feed URL is
  configured. It does not scrape the public website.

### Adzuna (`collectors/adzuna.py`)
- **Basis:** Public Search API, https://developer.adzuna.com/
- **Auth:** Free `app_id` + `app_key`, self-registered
- **ToS position:** Adzuna's developer terms permit this use; standard
  registered-API-key access, not scraping.
- **Scope limitation:** Only South Africa ("za") is used - Adzuna's 12-country
  coverage does not include any other African country. Do not extend to
  other African country codes; see `collectors/adzuna.py`'s module docstring.

### Pinpoint (`collectors/pinpoint.py`) — added Phase 2
- **Basis:** Public per-company JSON endpoint,
  https://help.pinpoint.support/en/articles/5878344-how-to-list-pinpoint-jobs-on-any-website
- **Auth:** None
- **ToS position:** Pinpoint's own help docs explicitly describe this
  endpoint as the intended solution for "how to list Pinpoint jobs on any
  website" - built for exactly this third-party use.
- **Why added:** Sun King (flagged as directly relevant to Sir's Nithio
  securitization work) was originally guessed to be on Lever; that guess
  404'd. Web search confirmed Sun King is actually on Pinpoint
  (sunking.pinpointhq.com). Worth checking Pinpoint for any other African
  climate/PAYGo/fintech company that doesn't resolve on Greenhouse/Lever/Ashby
  before assuming no public feed exists at all.

### Himalayas (`collectors/himalayas.py`) — added Phase 2
- **Basis:** Public JSON API, https://himalayas.app/jobs/api, documented at
  https://himalayas.app/docs/remote-jobs-api with an OpenAPI 3.1 spec
- **Auth:** None
- **ToS position:** Explicitly free and documented for third-party use;
  requires linking back to Himalayas and crediting it as source, and not
  redistributing to competing aggregators (Jooble, Google Jobs, LinkedIn
  Jobs) - neither restriction affects a first-party app like this one.
- **Verified directly against Himalayas's own docs** before building,
  not taken on faith from a third-party "free APIs" list.

### Remotive (`collectors/remotive.py`) — added Phase 2
- **Basis:** Public JSON API, https://remotive.com/api/remote-jobs,
  officially documented at https://github.com/remotive-com/remote-jobs-api
  (Remotive's own repo)
- **Auth:** None
- **ToS position:** Same attribution/no-redistribution terms as Himalayas.
  Jobs are intentionally delayed 24h on Remotive's side before appearing via
  the API - no benefit to polling more than once a day.

### Jobicy (`collectors/jobicy.py`) — added Phase 2
- **Basis:** Public JSON API, https://jobicy.com/api/v2/remote-jobs,
  officially documented at https://github.com/Jobicy/remote-jobs-api
- **Auth:** None
- **ToS position:** Same attribution/no-redistribution terms. 6h publication
  delay on Jobicy's side; their own docs note most listings skew
  Americas/Europe-EMEA, so expect thinner African-relevant coverage here
  than the other four - included anyway since it's genuinely free and adds
  some volume.

### RemoteOK (`collectors/remoteok.py`) — added Phase 2
- **Basis:** Public JSON API, https://remoteok.com/api - long-established,
  widely documented, stable for years
- **Auth:** None
- **ToS position:** No explicit redistribution restriction found in the same
  way as Himalayas/Remotive/Jobicy, but treated with the same courtesy
  (attribution via source.confidence="aggregated", not "official"). Response
  is a JSON array whose first element is a legal/attribution notice, not a
  job - handled by checking each element's shape rather than assuming a
  fixed position.

### Arbeitnow (`collectors/arbeitnow.py`) — added Phase 2
- **Basis:** Public JSON API, https://www.arbeitnow.com/api/job-board-api,
  documented at https://www.arbeitnow.com/blog/job-board-api
- **Auth:** None, CORS-enabled
- **ToS position:** No explicit redistribution restriction found; primarily
  Europe/DACH-focused with visa sponsorship as a core theme, which lines up
  with this pipeline's sponsorship-override logic (see `has_sponsorship_signal()`
  in `_common.py`).

## Checked and explicitly rejected/deferred, Phase 2 continued

**Workday - rejected, despite appearing in a third-party "free APIs" list as
"completely free, no API key."** Checked directly (2026-07-11): there is no
sanctioned public Workday jobs API. What exists is an undocumented internal
endpoint (`/wday/cxs/{tenant}/{site}/jobs`) that each tenant's own career-site
frontend calls internally - POST-based, varies per tenant, and actively
protected by Akamai bot detection. This is a materially different risk
profile from Greenhouse/Lever/Ashby/Pinpoint's genuinely-published public
APIs - closer to Tier 3 scraping (undocumented, defended, fragile) than
Tier 1 API access. Not added.

**Apify-hosted scrapers of any kind - rejected as a category.** Apify itself
is a paid platform ("$5/month free credits" is a limited trial, not
sustainable); several of the specific Apify actors surveyed also scrape
BrighterMonday, which directly conflicts with the explicit ToS prohibition
already documented above - running a third party's scraper doesn't change
whose data-use obligations apply. Several others just wrap free APIs we
already call directly (Remotive, RemoteOK) at a markup for no benefit.

**Techmap API / jobdatafeeds.com (covers Jobberman, BrighterMonday, Job Mail,
HotNigerianJobs, Jobsora, Careerjet) - deferred, not rejected.** "100
queries/month, up to 1,000 free postings/month" is a limited free tier of a
commercial product, not an open public API like the others in this file.
Worth checking its actual terms directly before committing, not assumed safe
from a third-party summary.

**Jooble API - deferred, not rejected.** Real and substantial (2M+ active
jobs), but requires a free-to-obtain API key (registration step), same
effort class as Adzuna/ReliefWeb. Worth doing as a follow-up, not bundled
into this pass.

**WeWorkRemotely - deferred, needs direct verification.** A third-party list
claimed a "Public API," but WWR is understood to be primarily RSS-based, not
a JSON API like Himalayas/Remotive/Jobicy. Needs a direct check against
WWR's own documentation before building anything, not an assumption.

**@jobdatalake / NextJobz MCP servers - different integration model,
deferred.** These are MCP (Model Context Protocol) servers, built for AI
assistants to call directly - not REST APIs a Python `requests.get()` script
can use the same way as everything else in this file. Worth investigating
separately whether either also exposes a plain REST endpoint underneath.

**Rise Jobs API - deferred, too vague to act on.** No endpoint given even in
the source list that mentioned it; nothing to verify against.

## Tier 2 — RSS/Atom feeds

- **UN Talent** is implemented through an approved JSON/RSS URL as described above.
- **UN Careers (careers.un.org)** - checked 2026-07-11. The RSS feed
  advertised at `careers.un.org/lbw/jobfeed.aspx` no longer functions as a
  real feed; the site has moved to a JavaScript-rendered Angular app that
  returns an empty shell to a plain HTTP fetch. No working feed URL found.
  Re-check periodically in case UN Careers restores a real feed.
- **UNDP (jobs.undp.org)** - checked 2026-07-11. `jobs.undp.org/cj_rss_feed.cfm`
  and its per-programme/per-country feeds (e.g. UNIFEM, UNCDF) are real RSS
  feeds, but **UNDP's own robots.txt disallows automated access**. Correctly
  excluded per spec §0.4 - do not scrape around this.

## Tier 3 — Scrapers

**BrighterMonday - explicitly excluded, checked 2026-07-11.** Their own
Terms and Conditions state: *"You may not use data mining, robots, screen
scraping, or similar data gathering and extraction tools on this Site."*
This is a direct contractual ToS prohibition, not just a robots.txt
technicality - stronger grounds for exclusion than most sources checked here.
Do not revisit this without a direct partnership agreement from BrighterMonday.

**None currently implemented.** Per spec §0.4/§3.3, a Tier 3 scraper may only
be added after confirming:
1. robots.txt permits automated access to the specific pages being fetched
2. ToS does not prohibit automated collection for this use case
3. A monitoring/health-check mechanism exists before the scraper ships (spec §8.4)

Candidates under consideration, **not yet cleared for implementation**:
- MyJobMag - robots.txt/ToS not yet checked

Do not implement a Tier 3 scraper without first adding a dated entry to this
file recording the robots.txt check and ToS review.

## Explicitly excluded

- **LinkedIn Jobs** - ToS explicitly prohibits automated scraping; aggressive
  anti-bot enforcement. No unofficial access path exists. Would require
  LinkedIn Talent Solutions partner status, which is a business development
  effort, not an engineering one.
- **Indeed** - Publisher API deprecated 2023; not accepting new applicants
  as of this writing. Re-check periodically in case this changes.
- **Fuzu** - No public API. Deferred to Phase 6 partnership outreach
  (spec §3.4) rather than scraped.
- **IMPACTPOOL** - Same as Fuzu.

## Currency data

### Frankfurter (`scripts/refresh_fx.py`)
- **Basis:** Free, open-source, no-API-key exchange rate API,
  https://api.frankfurter.dev
- **ToS position:** Explicitly built for zero-friction free use; no
  attribution requirement found in their docs (unlike some competitors, e.g.
  ExchangeRate-API's free tier requires attribution - Frankfurter does not).
- **Rate limits:** None documented for normal use; this workflow calls it
  once per day.

## Phase 7 DFI and multilateral sources

Phase 7 uses only public, employer- or institution-controlled career surfaces.
It does not authenticate into recruiting tenants, bypass access controls, submit
applications, or collect candidate data.

| Adapter | Access basis | Guardrail |
|---|---|---|
| Cornerstone/CSOD | Public career-site page and the read-only requisition search used by that page | Public token only; no tenant/customer API credentials |
| SAP SuccessFactors | Public Career Site Builder pages and public vacancy links | No permissioned OData or tenant API access |
| Oracle Candidate Experience | Public `recruitingCEJobRequisitions` resource used by the candidate site, with official HTML fallback | Read-only public requisitions; no candidate or HR endpoints |
| Official HTML/JSON-LD | Institution careers pages, structured `JobPosting` data and linked vacancy documents | Rate-limited, public-only, no login or anti-bot bypass |

Each institution remains independently configurable and can be disabled if its
terms, robots policy, or public technical interface changes. Source-health
reports expose failures rather than silently substituting unverified copies.
