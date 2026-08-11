# Project Handoff

## Handoff metadata

| Field                          | Value                                                                                                                                                      |
| ------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Last updated                   | 2026-08-10                                                                                                                                                 |
| Current Git branch             | `feature/T-013-xccontest-collector`                                                                                                                         |
| Branch relationship            | Extends the completed T-008 baseline at `e67bd5b` (`origin/main`) with T-009 through T-012 work                                                            |
| Current tasks                  | T-001 through T-011 — `Done`; T-012 — `Review`; T-013 — `In Progress`                                                                                     |
| Completed scope in this branch | T-009 coordinate/source research and the reviewed, migrated T-012 SQLite flight-data foundation, in addition to the completed dashboard/browser-smoke work |
| Current working tree note      | Contains T-013 collector, parser, reviewed site-mapping, and approved-only validation boundaries; local raw data, staging, and databases remain ignored            |

## T-013 collector slice - current (2026-08-04)

This section supersedes the older T-013 availability/blocking statements below
for the explicitly allowed XCContest flights-page browser workflow. T-013 is
**In Progress** on `feature/T-013-xccontest-collector`; T-012 remains in
`Review`. The task is not complete: this change implements the collector
boundary only, not the parser/import pipeline or a validated stored flight
sample.

The project owner confirmed normal, low-volume browser use of
`https://www.xcontest.org/world/en/flights/` for this work. The collector uses
Playwright only through visible rendered controls: selected season, `BG`
country, `FAI3` (`PG *`) glider category, exact solo-PG category controls,
source-offered dates, and table sorting. It does not activate the pager,
construct page-offset URLs, or call an undocumented backend endpoint. It waits
at least three seconds between source state transitions, captures exact rendered
`#flights` fragments as ignored immutable raw artifacts, and expands a
saturated first page through exact categories and only then dates. An individual
category/date that remains saturated after alternate sort orders is reported as
incomplete coverage rather than silently treated as exhaustive. A raw page may
contain shorter rows; the later parser must discard those from accepted records.

Command contract:

```powershell
uv sync --project services/ml
uv run --project services/ml xccontest-collect --season 2025
uv run --project services/ml xccontest-collect --season 2025 --season 2024
uv run --project services/ml xccontest-collect --season 2025 --headed
```

It is headless by default; `--headed` and `--slow-mo-ms` are local inspection
fallbacks. There is deliberately no `--permission-reference` argument and no
permission value in the raw manifest. A later database-import slice owns the
`ingestion_runs` placeholder required by the accepted schema.

Implemented files live in
`services/ml/src/paragliding_forecasts_ml/ingestion/xccontest/`. The collector
writes under ignored `data/raw/xccontest/<run-key>/` and
`data/interim/xccontest/<run-key>/`. It does not parse/normalize records, match
sites, decide canonical duplicates, persist SQLite rows, retain pilot identity,
or download IGC/track files. Those T-013 responsibilities require their own
follow-up plan; canonical duplicate/source traceability remains T-014 and
sanitized frozen parser fixtures remain T-015.

Verification: `uv run --project services/ml ruff format --check`,
`uv run --project services/ml ruff check`, and `uv run --project services/ml
pytest` pass (10 tests). `xccontest-collect --help` passes. Chromium is
installed locally, but two allowed headless 2025 live attempts did not render
a visible `#flights` table and timed out before writing an artifact. This is an
unverified browser-environment limitation, not a successful collection. A
developer must manually run the permitted `--headed` command in a normal
desktop environment, check the selected controls/table/pager and only follow
ordinary consent/login/challenge flow; do not bypass any of them.


## T-013 collector strategy update (2026-08-06)

This section supersedes the older pager and `--max-pages` wording above. The
source-provided pager is not part of the current collector flow, because in a
permitted headed browser run XCContest changed the fragment URL but did not
refresh the rendered table. Do not construct an offset URL or bypass an
interstitial/challenge.

For each requested season, the collector uses the rendered controls to select
`BG`, begins with `PG *` and descending distance, then only expands saturated
first-page views. It partitions with exact `CCC`, `EN D`, `EN C`, `EN B`, and
`EN A` categories. A saturated exact category is evaluated once for every date
provided by the source date selector. A saturated `category + date` then gets
pilot, points, and airtime, each in ascending and descending source order. It
is sequential, paced by at least three seconds, does not use parallel tabs, and
writes separate nonempty raw fragments with category/date/sort metadata.

The command uses `--max-views` rather than `--max-pages`, with a fail-closed
cap of 2,000 rendered views per run. A run is `incomplete` if any category/date
view remains saturated after the six supplementary sort views; those views may
find additional records but do not prove full coverage. The manifest and
interim checkpoint explicitly record those unresolved scopes. Tests are offline
fake-driver tests and must not be mistaken for a live-data validation. Manual
headed verification remains required before treating a real collected sample as
validated.

XCContest seasons span two calendar years. For a selected season `Y`, the date
control is valid from `Y-1-10-01` through `Y-09-30`; collector validation must
use this range rather than requiring every source-offered date to begin with
`Y-`.

## T-013 collector data-contract audit - current (2026-08-06)

The completed local run
`fe8a32a0-03c7-4963-8931-1dc7c614c451` was compared against the accepted
T-012 Drizzle schema and every representative XCContest list-row field. Each
of its six 100-row raw fragments contains numeric flight ID, displayed date and
takeoff time, UTC offset, launch name/country/search URL (including the source
point token), route label, scored distance, duration, and canonical detail URL.
The list page does not provide a separate permitted track download URL; the
T-012 `track_url` column is nullable.

Future collector runs now keep those values as optional raw
`RowObservation` fields without normalizing or accepting them. Short rows
remain collectable and must be rejected or quarantined by the parser. The
versioned raw manifest now carries source URL, collector version, start/end
times, completion/coverage status, per-artifact row/threshold counts, and
run-wide observed/distinct/repeated flight-ID counts. The collection report
returns the repository-relative manifest path and SHA-256 needed by
`ingestion_runs`; checkpoint and failure state include the available counters.
Existing ignored manifests are immutable and are not rewritten.

The inspected run has 600 row observations / 500 distinct IDs / 100 repeated
observations. At the 100 km threshold it has 324 observations / 224 distinct
IDs / 100 repeated observations. The 100 repeats are the expected overlap
between the initial PG umbrella view and the exact-category partitions.
Collector artifacts therefore remain untouched. The next T-013
parser/normalizer must collapse same-run rows by numeric XCContest
`source_flight_id` before site matching and preserve all contributing artifact
references. T-014 then hardens cross-run idempotency, conflicting-duplicate
handling, and persisted traceability.

Schema-to-pipeline ownership remains:

- parser/normalizer derives `takeoff_at_utc` from raw date/time/offset, parses
  launch point/name evidence, maps route and duration, applies the 100 km
  threshold, and canonicalizes the detail URL;
- validation accepts only approved `source_site_mappings` for priority sites
  and quarantines unknown or ambiguous launch evidence;
- persistence supplies source/method/permission policy, usage flags, full
  pipeline version, validation timestamps/notes and database timestamps, then
  writes one `ingestion_runs` row plus accepted `flight_records` in a
  transaction with outcome counters;
- no permission basis/reference may be invented from the collector manifest.
  A truthful value matching the T-012 enum remains a required import gate.

Verification passed: Ruff formatting and lint; 19 Python tests; an offline
Playwright DOM smoke over the saved 100-row primary fragment; collector CLI
help; repository Prettier check; repository structure check; and
`git diff --check`. No new live source request was made.


## T-013 DB-driven multi-country collection - current (2026-08-06)

This section supersedes the remaining hard-coded `BG` collector wording above. Before
browser or artifact creation, the CLI reads distinct, sorted ISO2 codes from every `sites`
row in the Drizzle-migrated SQLite database, including inactive sites. Python uses only
read-only standard-library `sqlite3`; it neither runs migrations nor creates a file or table.
The accepted URL precedence is `--database-url`, `DATABASE_URL`, then
`file:./data/local/paragliding.db`; only relative `file:` paths inside repository `data/`
are allowed. Missing schema, empty scope, invalid ISO2 code, or unavailable database fail
closed before any source interaction or raw output.

Each requested `season × country` target runs sequentially in one browser session. The
visible country filter and all row launch countries are verified for the current target; the
2,000-view cap remains global for the whole run. The current local database returns only
`BG`, while adding a site in another country intentionally expands a later run automatically.

Use the root `.env` without adding a dotenv dependency:

```powershell
uv sync --project services/ml
uv run --env-file .env --project services/ml xccontest-collect --season 2025
```

Manifest schema is now v2 and `collector_version` is `xccontest-collector/2`. Scope records
`country_codes`, `requested_seasons`, and `country_scope_source: "all_sites"`; target
statuses, checkpoint records, artifact metadata, and fragment filenames include country, for
example `season-2025-country-BG-category-pg-...html`. Existing ignored raw manifests are
immutable; future parser work must support legacy BG-only and v2 country-aware manifests.

Version policy is durable in DEC-024 and `services/ml/README.md`: any change to collector
behaviour, browser/source interaction, raw evidence, run metadata, or CLI contract must
increase `collector_version`; any change to manifest fields, shape, semantics, or
compatibility must also increase `manifest_schema_version`. The corresponding tests and
documentation updates are required for a complete collector change.

Verification for this change: `uv run --project services/ml ruff format --check`, Ruff
lint, and all 41 Python tests pass; `uv run --env-file .env --project services/ml
xccontest-collect --help`, repository Prettier/structure checks, and `git diff --check`
also pass. No live XCContest request was made.

## T-013 parser/normalizer v2 - current (2026-08-07)

This section supersedes the v1 snapshot below. Parser v1 nominally accepted
manifest schema v2 but its canonical detail URL rule rejected every current
2026 row because XCContest now emits `/world/en/flights/detail:...` without the
archived season path prefix. The real complete run
`f1032827-a98d-4c01-969e-e67b4885f90d` therefore exposed only the 2025 records
in parser-v1 staging.

Parser v2 accepts both archived `/<season>/world/en/flights/detail:...` and
current `/world/en/flights/detail:...` canonical URLs. It remains backward
compatible with the existing legacy BG-only manifest and strictly validates
complete manifest-v2 scope, target statuses, per-artifact row/qualifying
counters, run-wide observation/distinct/repeat counters, paths, and SHA-256
hashes. Versioned outputs are non-overwriting under
`data/interim/xccontest/<run-key>/parser-v2/`; existing parser-v1 output is not
modified.

The exact raw HTML plus manifest is the durable collector-to-parser interface.
Collector `RowObservation` now retains only flight ID, distance, and launch
country for collection control and counters. `CollectionReport` is now a compact
CLI summary only: manifest relative path/hash, lifecycle, scope totals, and aggregate
counters. Artifact/target detail remains solely in the immutable manifest. Version
identifiers are centralized in `versions.py`; parser staging directory derives from its
parser revision. Parser and browser DOM selectors share `selectors.py`; parser
normalization still reads the saved HTML offline.
Separate commands intentionally support resume/replay without another source
request. A later one-command ingestion wrapper may orchestrate the slices, but
must pass run keys and durable artifacts/staging outputs rather than transient
Python objects. DEC-025 records this boundary and the rule that parser
compatibility, selector, normalization, output, staging, or CLI changes require
a parser version increment plus a new `parser-vN` directory.

Real offline verification:

- manifest-v2 run `f1032827-a98d-4c01-969e-e67b4885f90d`: 1,200 observations
  across seasons 2025 and 2026; 536 qualifying observations; 336 unique
  candidates (224 for 2025, 112 for 2026); 200 duplicate observations removed;
  zero conflicts; 664 below-threshold rejections; all v2 counters verified;
- legacy run `fe8a32a0-03c7-4963-8931-1dc7c614c451`: 600 observations; 324
  qualifying observations; 224 candidates; 100 repeats removed; zero conflicts;
  276 below-threshold rejections.

Validation passes: Ruff formatting/lint, all 47 Python tests,
`xccontest-parse --help`, repository Prettier/structure checks, and
`git diff --check`. No live source request was made during parser verification.
T-013 remains **In Progress** for validation/site matching and persistence;
T-015 still owns sanitized frozen source fixtures.

## T-013 validation/site-mapping slice - current (2026-08-08)

The offline validation/site-mapping boundary is implemented; T-013 remains
**In Progress** because human mapping review and the persistence/orchestration
slice are still outstanding. DEC-026 gives each `launch_area` a 5 km catchment
and retains the 30 km Dobrich region catchment. The new reviewed custom Drizzle
migration applies those six values to existing or fresh local databases without
editing prior T-012 migrations.

Use only existing parser-v2 staging and a migrated local database:

```powershell
uv run --env-file .env --project services/ml xccontest-site-mappings propose --run-key <uuid>
uv run --env-file .env --project services/ml xccontest-site-mappings apply --review-file <mapping-decisions.jsonl>
uv run --env-file .env --project services/ml xccontest-validate --run-key <uuid>
```

`propose` is read-only against SQLite and writes non-overwriting grouped
`site-mapping-v2/mapping-proposals.jsonl`. It derives exact XCContest site-token,
normalized-name, or source-point evidence; coordinate suggestions use inclusive
Haversine distance against every same-country site with a non-null radius, not
`site_type`. A unique catchment is only a proposal. `apply` is the only command
that writes `source_site_mappings`, in one transaction after a human provides a
site and, for approval, a verification reference. `provisional` and `retired`
rows never accept flights.

`xccontest-validate` reads parser-v2 JSONL and only approved mappings, then
writes non-overwriting `validation-v1/<mapping-snapshot-sha256>/`
`accepted-flights.jsonl`, `site-quarantine.jsonl`, and `validation-report.json`.
It records parser/raw/mapping hashes and reconciles seen, rejected, deduplicated,
accepted, and quarantined counters. It neither calls XCContest nor writes
`ingestion_runs` or `flight_records`.

Offline validation of the real complete run
`f1032827-a98d-4c01-969e-e67b4885f90d` made no source request. With the current
empty mapping table it produced 45 grouped v2 proposals and safely accepted zero
records: 336 candidates were quarantined, alongside 664 parser rejections and
200 duplicate observations, reconciling to 1,200 observations. A reviewer must
now approve mappings before a subsequent mapping-snapshot validation can emit
accepted candidates. T-014 still owns cross-run idempotency/traceability and
T-015 owns sanitized frozen source fixtures.

Verification passed: database migration metadata and 16 database tests; Ruff
format/lint and all 54 ML tests; the mapping/validator CLI help; offline
proposal and validation on the existing real run; and the root build, typecheck,
lint, format, and repository checks. The Vite build retains its pre-existing
chunk-size advisory.

The ML README now contains the complete human-review procedure for source-site
mappings: proposal and review-file locations, JSONL rules, the valid decision values
and required fields, an audit-reference template, ready-to-apply
approved/provisional/rejected examples, transaction behavior, and the current
retirement limitation.

## T-013 parser/normalizer slice - superseded v1 snapshot (2026-08-06)

The offline parser/normalizer boundary is implemented; T-013 remains **In
Progress** because validation/site matching and persistence are still separate
slices. Use an existing immutable raw run only:

```powershell
uv run --project services/ml xccontest-parse --run-key <uuid>
```

The command makes no browser or network request, opens no SQLite database, and
does not read, propose, approve, or write `source_site_mappings`. It supports
legacy BG-only manifests and manifest v2, verifies the manifest source/run key,
constrains artifacts to the matching raw run, and checks every SHA-256 before
parsing. It then writes non-overwritable ignored outputs under
`data/interim/xccontest/<run-key>/parser-v1/`:
`normalized-flights.jsonl`, `parse-rejections.jsonl`, and `parse-report.json`.

Each normalized candidate carries numeric XCContest flight ID, launch name,
country, point token and coordinates when available, UTC takeoff timestamp,
route type/raw label, scored kilometres, duration seconds, canonical detail URL,
and all contributing artifact references. Pilot identity is not emitted.
Candidates below 100 km, above 2,000 km, or malformed are rejected. Identical
same-run IDs produce exactly one normalized record; conflicting same-ID
observations produce one `conflicted` candidate with all variants and fields in
conflict, without choosing a value. Cross-run idempotency remains T-014.

Validation: `uv run --project services/ml ruff format --check`, Ruff lint, and
all 46 Python tests pass; `xccontest-parse --help`, repository Prettier and
structure checks, and `git diff --check` pass. The parser completed an offline
legacy-manifest run `fe8a32a0-03c7-4963-8931-1dc7c614c451`: 600 observations,
324 qualifying normalized observations, 224 unique candidates, 100 duplicate
observations removed, zero conflicts, and 276 below-threshold rejections. No
new live source request was made. T-015 still owns sanitized frozen fixtures.
## T-010 and T-011 flight-source research - read before T-012/T-013

T-010 research is complete and the report is available at
`T-010-xccontest-research-report.md` (updated 2026-07-28). Its status is **Done**; this is not permission to implement a collector.

Key decisions and constraints:

- XCContest is still the strongest candidate for historical positive XC labels,
  but automated collection is blocked pending written permission, an official
  API/export, or an explicitly authorised low-rate workflow.
- The dynamic public flights table is populated by internal query-string
  requests (for example `/api/data/?flights/world/<year>...`). These are not a
  documented public API and fall under the current `robots.txt` rule
  `Disallow: /*?`. Playwright that merely waits for/reads the rendered table
  still makes those XHR/fetch requests; it is not a policy workaround.
- Do not hard-code, publish or reuse browser session keys/cookies/tokens. Do
  not bypass login, verification challenges, Cloudflare or CAPTCHA.
- Anonymising display names is desirable data minimisation, but it does not
  create reuse rights or necessarily make dated coordinate/track data anonymous.
  A future paid product must not rely on a bulk-scraped XCContest dataset
  without written permission/licensing and focused IP/GDPR review.
- `airspace.xcontest.org` is a separate documented API for current airspace
  geometry and activations (NOTAM, TMA/CTR, danger areas, TRA). It has no
  historical flights, tracks, launch/landing points, distance, duration or
  100+/200+/300+ labels, so it cannot replace XCContest or SkyNomad for Takt 2.
  If later added, expose it as a distinct operational/safety constraint rather
  than changing meteorological XC potential. Its current API has no documented
  historical activation archive for backtesting.

### T-011 completed result - SkyNomad

T-011 is complete and the report is available at
`T-011-skynomad-research-report.md` (2026-07-28). Its status is **Done**.
It established that SkyNomad has three materially different surfaces:

- `www.skynomad.com` is a live WordPress site. Its public unauthenticated REST
  API and sitemap are usable at low volume for discovery and manual
  corroboration of articles, aliases, dates, named locations, route narratives
  and links to flight records. This is not a complete flight database, and
  WordPress posts are not flight counts.
- `forum.skynomad.net` has a phpBB forum, which is potentially useful only as
  unstructured narrative/context evidence.
- `forum.skynomad.net/leonardo/` is the important potential structured source:
  the Leonardo GPS flight database. SkyNomad's current WordPress articles link
  to Leonardo flight IDs in 2025, so it must not be treated as a dead archive.
  The Leonardo open-source code documents likely flight/list/detail fields,
  URL patterns, filters and candidate selectors, but these are **not** a
  confirmed contract for SkyNomad's deployed version.

Live access and policy decision:

- Automated requests to the forum and Leonardo host currently receive a
  Cloudflare managed JavaScript/cookie challenge (`403`) before content can be
  inspected. Do not bypass Cloudflare, CAPTCHA, login or session controls.
- Forum `robots.txt` allows `/`, but its content signals specify
  `ai-train=no` and `use=reference`. It has no `Crawl-delay` and no published
  numeric quota. `Allow: /` is not permission to collect flight records for
  ML training.
- No verified public SkyNomad developer API, data licence, bulk export, terms
  authorising ML reuse, registration requirement, or request-rate limit was
  found. No load testing was performed or should be performed to infer a limit.
- Therefore **do not implement, schedule or run a Leonardo scraper, automated
  IGC/KML download, or ML-training import**. T-011 intentionally contains no
  scraper implementation. The preferred next action is a written request to
  SkyNomad for a project-specific licence/permission, supported export or API,
  approved endpoints, rate/concurrency, attribution and retention/privacy
  conditions.

T-013 decision and data contract implications:

- SkyNomad may support only a small manually validated, cited **reference**
  sample while the present policy remains in effect. It is not a cleared
  training-data fallback. It can become one only with explicit written
  permission or an owner-provided/licensed export; otherwise the product owner
  must expressly limit any sample to non-training validation use.
- After permission, discover records primarily by authoritative T-009 takeoff
  IDs/aliases, paraglider category, date range and minimum optimized/scored
  distance. Use a permitted coordinate-radius query only if SkyNomad confirms
  its endpoint and private-record behaviour. Do not rely only on free text or
  fixed place categories.
- T-012 must be able to represent source/provenance and validation fields in
  addition to the base flight record: `source_system`, `source_flight_id`,
  canonical/source URLs, flight date/time/duration, takeoff ID/name and
  coordinates, optimized/scored and linear distances separately, route type,
  PG category, track links/availability, validation notes/status, retrieval
  time, `permission_basis`, and optional raw-artifact hash. Pilot identity is
  not an ML feature and must not be retained unless the permission explicitly
  allows it.
- Use optimized/scored Leonardo `FLIGHT_KM`/OLC distance for the proposed
  100-199 / 200-299 / 300+ bands while preserving other distance measures;
  product-owner and T-012 confirmation is still required before labels freeze.
- Raw external responses, IGC/KML files and unsanitized HARs stay outside Git;
  only sanitized, permitted fixtures may be committed. Web/API request handlers
  must never scrape SkyNomad.

Before any future collector is built, manually verify normal browser access,
registration/free-account requirements, public-versus-private records, one
list/search result and several detail pages, category/distance/date filters,
track-download authorization, and a sanitized HAR/screenshots without cookies,
tokens or account identifiers. Replace source-code-derived selectors/endpoints
only with this approved live evidence. T-009 still owns authoritative location
coordinates, aliases and radii; T-012 owns the persistence schema.

## T-012 persistence planning decision - read before implementation

DEC-020 accepts a deliberately phased persistence approach. T-012 must **not**
create every table named in the initial project brief. Its scope is only the
Takt 2 foundation required to store and audit validated flight evidence:

- canonical `sites`, preserving current numeric IDs and public slugs;
- source-specific site aliases/takeoff mappings for XCContest matching;
- `ingestion_runs` for import provenance;
- canonical `flight_records` for accepted records.

T-012 owns Drizzle/Drizzle Kit setup in a new `packages/database` workspace,
the first reviewed SQL migrations, database-path configuration, and tests that
prove an empty local database can be migrated. It does not implement a source
client, scraper, parser, normalizer, Python writer, real sample import, or
browser/API persistence switch. The formerly open physical design is now
accepted in the task handoff; implement and test it rather than
reopening its field set.

The Takt 2 ingestion flow is fixed conceptually:

```text
permitted XCContest input/export
  -> data/raw/xccontest/<run-id>/ exact immutable input + metadata
  -> T-013 source parser and normalized staging
  -> validation, site match, duplicate decision
  -> accepted record written to data/local/paragliding.db
  -> rejected/ambiguous record kept under data/interim/xccontest/<run-id>/
```

The raw artifact is not browser cache or a database replacement. It is the
unaltered evidence received from the source, kept so a parser can be retested
or corrected without another source request. A new retrieval creates a new
artifact instead of overwriting the old one. T-013 implements the pipeline and
persists an accepted sample; T-014 proves idempotency and traceability; T-015
adds small committed sanitized fixtures for offline parser tests.

For site assignment, do not choose between a string and a foreign key.
`flight_records` must preserve the source takeoff name/ID exactly as received
and, once successfully matched, reference canonical `sites.id`. Match priority
is source takeoff ID, then approved alias, then approved geographic catchment,
then manual review. Canonical accepted flight records require a site relation;
ambiguous candidates are quarantined rather than assigned a guessed ID.

The selected Takt 2 source is XCContest. Its storage remains source-neutral so
future sources do not force a second flight table. The current access decision
still prohibits an unapproved automated collector: T-013 may use a permitted
manual export/capture first, and can add an approved XCContest client later
without changing the downstream pipeline.

## T-012 final implementation plan — read before coding

The complete accepted plan was supplied in the task handoff, with the accepted ERD in [`T-012-flight-schema.drawio`](T-012-flight-schema.drawio).
This supersedes earlier handoff wording that treated physical T-012 fields as
open design work.

The first foundation has five tables: `flight_sources`, `sites`,
`source_site_mappings`, `ingestion_runs`, and `flight_records`. It is strictly
normalised: mappings preserve source identity/evidence and point to canonical
sites; accepted flights point to one mapping and do not duplicate site, source
takeoff name/token, match method/distance, or distance band.

The final flight time is `takeoff_at_utc`; do not add local date/time or UTC
offset columns. Convert for display/weather grouping with the linked site's
IANA timezone. `scored_distance_km` is the only stored distance metric for
T-012. There is no `track_status`; the nullable `track_url` records a captured
link. Validation levels are `metadata` and `track`.

`source_id` remains on `flight_records` with the unique external identity
`(source_id, source_flight_id)`, because a uniqueness constraint cannot reach
the source through `ingestion_runs` in SQLite. Composite foreign keys enforce
that the flight, mapping, and two provenance runs share the same source.

Ingestion provenance stores a raw manifest path/hash, permission evidence,
pipeline version, lifecycle, and counters. Per-file retrieval times and ETags
belong in the manifest, not in `ingestion_runs`. Raw inputs stay under
`data/raw/<source>/<run-key>/`; canonical accepted records later go to the
ignored local SQLite file, while rejected/ambiguous candidates remain in
`data/interim/`.

Implementation uses generated/reviewed Drizzle migrations only: first create
the foundation, then seed the seven sites and XCContest source. Do not use
`drizzle-kit push`, modify an applied migration, or add Python migrations.

## T-012 verified migration foundation

The reviewed T-012 SQL migrations were explicitly approved before execution and
applied twice to a fresh ignored SQLite file; the second run recorded no
additional migration work. The foundation defines only `flight_sources`,
`sites`, `source_site_mappings`, `ingestion_runs`, and `flight_records`, then
seeds XCContest and the seven canonical sites. Composite foreign keys guarantee
that each flight, its source mapping, and both provenance runs share one source;
the supporting `(id, source_id)` unique keys exist solely because SQLite requires
an exact unique parent key for such foreign keys.

The implementation is ready for review. Verified on 2026-08-02:

- database coverage: 4 files / 16 tests; 100% statements, functions, and lines;
  96.66% branches;
- root typecheck, build, lint, format check, and repository structure check;
- root coverage: database 16, contracts 15, API 82, and web 121 tests.

Do not use `drizzle-kit push`, edit an applied migration, or add another DDL
owner. T-013 remains blocked until a permitted XCContest input/export method is
available; it owns importing real records, not altering this foundation.

## Current outcome

T-006/T-007 now implement `/forecast?site=<slug>&date=YYYY-MM-DD`. It uses
the existing site/date URL state, auto-fetches one detailed forecast on selector
or map selection, and returns to the dashboard through `All sites` while
preserving selection. The dashboard's selected action and all Other Locations
cards are working links to that route. No browser or screenshot automation was
run by explicit user instruction; manual visual review is still required.

T-008 now adds `@playwright/test` in the web workspace and a Chromium smoke
suite. It starts the compiled API and Vite as separately readiness-checked local
processes on the normal `3000` and `5173` ports. One test asserts the dashboard
location selector, five dates, five required forecast metrics, and mock status;
the second follows the detailed-forecast action, checks detailed outputs,
inputs, drivers, and `All sites` return navigation. OSM tile requests are
blocked so the core local smoke does not depend on the public tile service.
Use `npm.cmd run test:browser` by default, `test:browser:headed` to see
Chromium, and `test:browser:ui` for interactive debugging after installing the
matching binary once with `test:browser:install`. The first local
`test:browser` execution successfully started the compiled API, Vite, and
Chromium and reached the dashboard API calls. After correcting the non-exact
`getByLabel("Location")` locator and the dashboard action's prefix-matching
`getByRole("link")` locator, the user reran the suite on 2026-07-25. Both
Chromium scenarios passed (`2 passed (8.8s)`): the dashboard forecast-card
assertions and the dashboard-to-detail return-navigation flow. T-008 is
therefore in `Review`.

The Playwright-managed API and Vite processes now receive explicit test
environment values for the fixed API host/port, web port, CORS origin, browser
API base URL, mock data mode, and `NODE_ENV=test`. Local `.env` or shell
overrides therefore cannot move the processes away from Playwright's fixed
readiness URLs.

Validation on 2026-07-29 passed `format:check`, the web workspace typecheck,
`repo:check`, and Playwright test discovery. Both Chromium scenarios reached
`ok` in Codex, but its managed command did not exit while closing Vite. The
same `npm.cmd run test:browser` command was then run from a normal PowerShell
terminal with no listeners on ports 3000/5173: it completed successfully with
`2 passed (19.4s)` and returned to the prompt. Treat the Codex-only teardown
hang as an execution-wrapper limitation, not a failing T-008 browser test.

`npm.cmd audit` on 2026-07-25 reports three high advisories in the existing
dependency graph: direct `react-router-dom`/`react-router` and transitive
`brace-expansion`. The report does not name Playwright. Its suggested router
change is a semver-major downgrade, so T-008 deliberately does not make that
unrelated dependency change; address it in a dedicated dependency/security
ticket.

The detailed response now includes strict mock `forecastInputs`: source-run
metadata plus explicit-status temperature, boundary-layer, wind, humidity,
instability, cloud, precipitation, pressure, and convergence values. Each of
the five outputs retains its own confidence/status. Top drivers remain strings,
and the five `Unchanged` previous-run entries are deliberately static UI rather
than API data. DEC-018 records that this is a provisional read model, not the
final T-017/persistence weather-feature schema.

The API now supplies the data shapes required by the approved dashboard design
without changing the detailed-page contract into a dashboard endpoint. It adds
provisional map metadata for all seven locations, batched forecast summaries
for one selected date, and a fixed selected-site date preview covering Sofia
today minus two through today plus two.

Pure conversion from internal `ForecastPrediction` values to detailed,
summary, and day-preview response shapes now lives in
`forecast-response.mapper.ts`. `ForecastService` contains only the three public
use cases, site resolution, clock use, repository access, ordering, and missing
record decisions. No state-free helper class was introduced.

The dashboard implementation plan is supplied outside the repository with the
implementation task. DEC-017 records its durable accepted technology choices;
the repository deliberately does not contain a separate dashboard-plan file.

A minimal React root, strict browser/Node TypeScript configs, Vite production
build, runtime API-base validation, strict configurable development port, and
supervised API/web development command now exist. The browser also has a
shared-schema-validated fetch client, classified errors, TanStack Query
provider/options, URL-owned Browser Router dashboard orchestration, and real
Vitest/jsdom/RTL/MSW tests. The visual foundation adds self-hosted Inter with
Cyrillic coverage, CSS theme tokens, a responsive viewport layout, a semantic
application header, four stable dashboard regions, and reusable panel/content-
state primitives. Forecast values remain explicitly synthetic `mock` data and
must not be presented as aviation weather or flying advice.

The selected overview now renders the five contracted metrics with explicit
units plus generated-at, provenance, confidence, and data-status context. The
Other Locations region renders the three catalog entries after the minimum-ID
default in ascending ID order without filtering a duplicate selected site. Summary-level
missing data, omitted content, partial missing metrics, and fully missing
metrics remain visibly distinct and never become numeric zero.

The location region now lazy-loads a Leaflet map, fits all seven provisional API
coordinates, renders permanent labels, distinguishes the selected pin by shape,
size, border, and colour, and routes pin selection through the same URL callback
as the native selector. OpenStreetMap attribution stays visible. Scroll-wheel
zoom and map keyboard navigation are disabled; visible zoom controls remain,
and the native select is the complete keyboard path. A tile error leaves the
selector, labels, forecast content, and an explicit degraded-map explanation.

The date region now renders exactly the five ordered API slots with no arrows or
pagination. API `todayDate` and URL selection are represented independently,
date-only labels cannot shift through local timezone parsing, and each card
retains explicit metric status/confidence context. A missing 100+ kilometre
metric remains selectable in place with its reason and never becomes zero.

The 2026-07-23 manual-review iteration rebuilt the wide dashboard around a
single `100dvh` canvas. Header, overview, Other Locations, the full-height map,
and the five-day strip now share one fixed viewport without page scrolling.
The header spans the viewport independently of the dashboard body, which now
uses a fluid `90vw` width, fractional columns, and viewport-relative rows
without a fixed maximum. The location selector has a deliberate gap above the
map, overview and comparison content are denser, and compact-height rules
preserve the single-screen composition on shorter desktop viewports. Narrow
stacked layouts continue to scroll normally.

Cross-cutting hardening now distinguishes retryable request failures from API
compatibility failures. HTTP Problem Details request IDs are visible, retry is
offered only for network/5xx paths, and sites, days, and shared summaries each
recover in place without disabling unrelated successful regions. The shared
summary failure emits one alert; the Other Locations panel shows restrained
context instead of repeated alert spam. Native controls, focus rings, live
selection announcements, reduced motion, larger map controls/pin targets, and
long-content wrapping are covered by the implementation and tests.

## Web workspace

- `npm.cmd run dev:web` starts Vite on `http://localhost:5173` by default.
- `npm.cmd run dev` supervises API and web processes and stops the sibling when
  either process exits.
- `WEB_PORT` is validated as an integer from 1 through 65535 with
  `strictPort: true`; a changed port requires the identical `CORS_ORIGIN`.
- `VITE_API_BASE_URL` is validated before React renders as an absolute HTTP(S)
  URL and normalized without a trailing slash.
- Root build, typecheck, lint, format, and structure checks now include web.
- Standalone web commands build shared contracts before compiling or testing;
  the combined supervisor builds them once before starting raw watchers.
- Browser requests classify network, HTTP Problem Details, and invalid-success
  failures, propagate cancellation, and retry only the first network/5xx
  failure.
- Web coverage counts all maintained TS/TSX source with enforced 80%
  statement/line/function and 75% branch minimums.
- `site` and `date` URL parameters are the sole dashboard selection state;
  invalid defaults use history replace and deliberate changes use history push.
- Sites, five-day previews, and batched summaries retain independent loading,
  error, retry, missing, and response-correlation behavior.
- The visual shell keeps Overview, Other Locations, Site Selector, and Date
  Selector mounted across request states so content changes do not reconstruct
  the page hierarchy.
- The header now follows the supplied visual reference with a bell mark while
  retaining `Decision support only` and `Not aviation weather` as accessible
  context.
- Forecast date-only labels are formatted with UTC calendar parts, while
  generation instants are rendered in `Europe/Sofia`; no naive date-only parse
  can move the visible forecast to a different day.
- The dashboard's full-width detailed-forecast action is a working link, and
  every Other Locations card is a whole-card link for its site/current date.
- Leaflet is loaded through a separate production chunk. OSM Standard is a
  runtime internet dependency with no offline or SLA guarantee; the provider
  URL, linked attribution, maximum zoom, and policy URL are centralized.
- The five-card strip uses `aria-current="date"` for API today and
  `aria-pressed` for the URL-selected date. It has no hidden date expansion,
  arrows, qualitative weather labels, or invented iconography. The separate
  year and weekday rows are no longer visible; cards show `Today` or day/month.
- Request failures preserve Problem Details support identifiers. Invalid JSON,
  schema failures, and correlation mismatches are compatibility errors; their
  untrusted payloads are not rendered and retry is not presented as a fix.

## HTTP surface

```text
GET /health
GET /api/v1/sites
GET /api/v1/forecasts?siteSlug=...&date=YYYY-MM-DD
GET /api/v1/forecasts/summaries?date=YYYY-MM-DD&siteSlugs=slug-1,slug-2
GET /api/v1/forecasts/days?siteSlug=...
```

### Sites

- Returns `{ id, slug, name, latitude, longitude }` for seven sites.
- Sorts explicitly by `id ASC`; there is no `dashboardOrder`.
- Uses the corrected `Pastrina` / `pastrina` name and preserves numeric ID 6.
- Coordinates are provisional map points. T-009 still owns authoritative
  coordinate, alias, and catchment-radius confirmation.

### Detailed forecast

- Powers `/forecast?site=<slug>&date=YYYY-MM-DD` through one detailed request.
- Returns full outputs, per-output confidence/status, provenance, top drivers,
  and strict mock forecast inputs with separate provenance/source-run time.
- Returns `404 SITE_NOT_FOUND` for an unknown site and
  `404 FORECAST_NOT_FOUND` for a known site/date without a record.

### Dashboard summaries

- Accepts one real date and one CSV string containing one through seven unique
  slugs.
- Rejects duplicate/empty slugs, repeated query keys, unknown parameters, and
  more than seven slugs with `400 VALIDATION_ERROR`.
- Resolves all sites before forecast storage; an unknown valid slug makes the
  request `404 SITE_NOT_FOUND`.
- Returns exactly one summary per requested site, sorted by numeric site ID.
- An available item contains generation time, provenance, and all five overview
  metrics. A missing record remains a `200` item with
  `availability: "missing"` and a reason.
- Metric statuses/confidence remain canonical; there is no duplicate summary-
  level `dataStatus`.

### Five-day preview

- Accepts only `siteSlug`; there are no arrows, date, limit, offset, cursor,
  anchor, direction, pagination, or historical-navigation fields.
- Derives `todayDate` in `Europe/Sofia` and returns exactly five consecutive
  calendar slots: today -2, -1, today, +1, and +2.
- Each slot contains only its date and the existing `chance100KmPct` metric.
- Missing predictions do not shift or shorten the strip; the fixed slot carries
  a `missing` metric with an explicit reason.
- Date calculation uses Sofia calendar extraction and UTC calendar arithmetic,
  avoiding fixed-duration DST errors.

## React request ownership

The dashboard route owns request orchestration; presentational cards receive
data rather than fetching independently.

1. Fetch `/api/v1/sites` once for the map and location selector.
2. Derive selected site slug and date from canonical URL search parameters.
3. Select the three catalog entries after the minimum-ID default for Other
   Locations, deduplicate them with the selected site, and fetch them through
   one summaries request.
4. Index summaries by slug because the API sorts by ID, not request order. If
   the selected site is also a default card, reuse the same summary in both
   positions.
5. Fetch `/api/v1/forecasts/days` when the selected site changes.
6. The dashboard action and Other Locations cards link to the detail route;
   that route owns `/api/v1/forecasts` while dashboard cards retain their
   summary/day-preview requests.

This means the forecast portion of one dashboard state needs two requests, not
one request per component.

## Mock repository behavior and limitation

The mock adapter creates 35 records at API construction time: seven sites
multiplied by the Sofia startup date minus two through plus two. Day offsets
have deterministic variations so date cards do not all show identical values.
The repository supports nullable single reads, batched site/date reads, and
inclusive site/date-range reads and returns defensive copies.

The five-day service uses the live request clock while the synthetic catalog is
anchored at startup. A development process kept running across Sofia midnight
can therefore outlive its mock snapshot; restart the API after the local date
rolls over. A persisted date-aware prediction adapter must replace this behavior
before real model output is connected.

## Contracts and missing semantics

`@paragliding-forecasts/contracts` now owns reusable output schemas plus:

- `ForecastSummariesQuery`, `ForecastSummary`, and
  `ForecastSummariesResponse`;
- `ForecastDaysQuery`, `ForecastDay`, and `ForecastDaysResponse`;
- `FORECAST_NOT_FOUND` Problem Details metadata;
- required bounded latitude/longitude fields for `Site`.

Missing records deliberately differ by read model:

| Read model | Behavior                                  |
| ---------- | ----------------------------------------- |
| Detailed   | `404 FORECAST_NOT_FOUND`                  |
| Summaries  | `200` missing item                        |
| Days       | `200` fixed slot with missing p100 metric |

Accepted design decisions are recorded as DEC-015 through DEC-018 in
[`decisions.md`](decisions.md).

## Validation

Final verification on 2026-07-22 passed:

- `npm.cmd run build`
- `npm.cmd run typecheck`
- `npm.cmd run lint`
- `npm.cmd run format:check`
- `npm.cmd run repo:check`
- `npm.cmd test`: contracts 2 files / 15 tests; API 16 files / 76 tests
- `npm.cmd run test:coverage`:
  - contracts: 98.82% statements/lines, 97.22% branches, 100% functions;
  - API: 80.24% statements, 81.11% branches, 82.35% functions, 80.50% lines.

Coverage remains above all configured workspace thresholds. Tests include real
Express/Supertest query parsing, summary ordering and partial missing data,
fixed missing date slots, timezone/calendar boundaries, repository batch/range
behavior, and existing server/logging/error behavior.

The Stage 0 contracts/API gate was rerun and extended on 2026-07-22:

- contracts build and typecheck passed;
- contracts tests: 2 files / 15 tests;
- contracts coverage: 98.82% statements/lines, 97.22% branches, 100% functions;
- API build and typecheck passed;
- API tests: 16 files / 82 tests;
- API coverage: 80.24% statements, 81.11% branches, 82.35% functions, 80.50% lines.

The new HTTP cases cover exact site names, the seven-site summary upper bound,
strict missing/repeated parameters, exact batch membership, correlated Problem
Details, mixed available/missing summaries, and a fixed missing day slot.

The Stage 1 workspace checkpoint passed:

- `npm.cmd run build` (including the Vite production bundle);
- `npm.cmd run typecheck`;
- `npm.cmd run lint`;
- `npm.cmd run format:check`;
- `npm.cmd run repo:check`;
- `npm.cmd audit --omit=dev`: 0 vulnerabilities;
- full `npm.cmd audit`: 0 vulnerabilities; the unsuitable third-party process
  supervisor dependency was removed in favor of the repository-owned script.

Manual command checks also proved that the combined development command served
API and web responses together, an invalid `WEB_PORT` failed nonzero and left
no API listener behind, and a second Vite process failed rather than falling
through from occupied port 5173.

The Stage 2 browser query checkpoint passed:

- web build and typecheck passed, including the production Vite bundle;
- web tests: 4 files / 32 tests;
- web coverage: 87.93% statements, 88.46% branches, 94.11% functions, and
  88.49% lines;
- repository lint, formatting, structure, and `git diff --check` passed.

Tests cover base-path-safe URL/query encoding, all three response schemas,
validated Problem Details, safe non-JSON HTTP fallback, network failure,
cancellation, malformed successful responses, stable query keys/signals, and
retry/freshness/provider defaults.

The Stage 3 URL orchestration checkpoint passed:

- web build and typecheck passed, including the production Vite bundle;
- web tests: 6 files / 76 tests;
- web coverage: 93.43% statements, 91.55% branches, 95.18% functions, and
  93.52% lines;
- repository lint, formatting, structure, and `git diff --check` passed.

Tests cover strict/default URL normalization, valid-date concurrency, API-
defined today fallback, out-of-strip correction, Back/Forward and production
BrowserRouter deep links, same-selection no-ops, numeric-ID request ordering,
selected-site deduplication, partial/empty catalogs, omitted summary content,
independent failures, stale-data prevention, and response correlation. Vite
reported a non-blocking 560.27 kB minified main-chunk warning; later visual/map
work should keep code-splitting in view without inventing a premature route.

The Stage 4 visual-foundation checkpoint passed:

- web build and typecheck passed, including the production Vite bundle;
- web tests: 9 files / 82 tests;
- web coverage: 94.55% statements, 91.08% branches, 95.78% functions, and
  94.68% lines;
- the responsive shell, semantic panel headings, scoped loading/error/empty
  states, and application header have component/integration coverage;
- repository lint, formatting, structure, and `git diff --check` passed after
  the final gate.

Screenshot generation and automated pixel comparison were deliberately not
performed at the user's request. Final visual inspection remains a manual user
check; the automated gate covers structure, semantics, behavior, and build
integrity.

The Stage 5 forecast-presentation checkpoint passed:

- web build and typecheck passed, including the production Vite bundle;
- web tests: 12 files / 95 tests;
- web coverage: 94.73% statements, 87.50% branches, 96.92% functions, and
  94.72% lines;
- tests cover exact units and formatting, Sofia generation time, all five data
  statuses, homogeneous/mixed/unavailable confidence, partial/full missing
  metrics, summary-level missing and omitted content, ID-derived Other
  Locations order versus response-map order, and a selected site retained as a
  card;
- repository lint, formatting, structure, and `git diff --check` passed after
  the final gate.

The Stage 6 Leaflet selector checkpoint passed:

- web build and typecheck passed; Vite emitted a separate 157.38 kB minified
  `SiteMap` chunk instead of adding Leaflet to the initial dashboard chunk;
- web tests: 15 files / 101 tests;
- web coverage: 95.17% statements, 87.50% branches, 96.83% functions, and
  95.13% lines;
- tests cover native-selector ordering/selection, fitted API bounds, OSM URL and
  linked attribution, seven permanent names, non-tabbable pointer pins, shared
  selection callback, disabled scroll-wheel/map keyboard handling, selected-
  site viewport updates, reduced motion, and the tile-failure explanation;
- dependency audit reported 0 vulnerabilities; repository lint, formatting,
  structure, and `git diff --check` passed after the final gate.

No real-browser map interaction or visual comparison was performed. This is an
explicit manual user check, and T-008 still owns automated browser proof; jsdom
component tests do not prove real tile rendering, zoom, pan, or label collision
behavior.

The Stage 7 five-day selector checkpoint passed:

- web build and typecheck passed, including the production Vite bundle;
- web tests: 16 files / 104 tests;
- web coverage: 95.30% statements, 87.67% branches, 96.93% functions, and
  95.28% lines;
- tests cover exactly five ordered slots, API-owned today versus URL-owned
  selection, UTC-safe day/month/weekday/year labels, callback selection, absent
  arrows and weather images, explicit accessible descriptions, and a missing
  slot that stays selectable without zero substitution;
- repository lint, formatting, structure, and `git diff --check` passed after
  the final gate.

The Stage 8 state/accessibility-hardening checkpoint passed:

- web build and typecheck passed; Vite kept Leaflet in a separate 157.36 kB
  minified `SiteMap` chunk and reported the existing non-blocking 588.73 kB
  initial dashboard chunk warning;
- web tests: 17 files / 112 tests;
- web coverage: 96.04% statements, 88.92% branches, 98.78% functions, and
  96.05% lines;
- tests cover correlated request IDs, retry recovery for sites/days/summaries,
  non-retryable compatibility errors, a single summary alert, live selected
  forecast announcements, keyboard date activation, and the existing
  reduced-motion, tile-failure, stale-data, empty, and missing-data behavior;
- repository lint, formatting, structure, and `git diff --check` passed after
  the final gate.

No real-browser keyboard, narrow-screen, or visual inspection was performed at
the user's request. Automated checks cover the rendered semantics and
interactions but do not prove pixel layout, real-browser focus appearance, map
tiles, or label collisions.

The final repository-wide dashboard gate passed on 2026-07-23:

- `npm.cmd run build`
- `npm.cmd run typecheck`
- `npm.cmd run lint`
- `npm.cmd run format:check`
- `npm.cmd run test`
- `npm.cmd run test:coverage`
- `npm.cmd run repo:check`
- `git diff --check`

Test counts were contracts 2 files / 15 tests, API 16 files / 82 tests, and web
17 files / 112 tests. Coverage remained above every configured threshold:

- contracts: 98.82% statements/lines, 97.22% branches, 100% functions;
- API: 80.24% statements, 81.11% branches, 82.35% functions, 80.50% lines;
- web: 96.04% statements, 88.92% branches, 98.78% functions, 96.05% lines.

The production build succeeded with Leaflet in its separate 157.36 kB minified
chunk and the documented non-blocking 588.73 kB initial dashboard chunk
warning. A combined `npm.cmd run dev` HTTP smoke returned 200 JSON from
`/health` and `/api/v1/sites` plus 200 HTML containing the React root from a
dashboard URL with site/date parameters; both listeners stopped afterward.
This did not execute browser navigation or React rendering.

No screenshot, automated pixel comparison, or real-browser manual check was
performed, as requested by the user. The remaining manual review is
desktop/narrow visual fidelity, copied URL and browser history behavior,
Leaflet tiles/pan/zoom/labels, keyboard focus, degraded requests/tiles, and the
browser console.

The follow-up visual iteration on 2026-07-23 also used no browser automation or
captured output. Verified changes include the fixed-height wide shell,
full-height map region, full-width independent header, fluid `90vw` dashboard,
selector/map spacing, denser overview/comparison cards, a disabled visual
detailed-forecast action, reference-style confidence segments in the date
cards, and removal of the visible year. Web build, typecheck, lint, formatting,
and all 17 web test files / 112 tests passed. Web coverage passed at 96.10%
statements, 88.99% branches, 98.80% functions, and 96.12% lines. Manual visual
acceptance is still pending.

The T-006/T-007 implementation validation on 2026-07-24 passed:

- `npm.cmd run build`
- `npm.cmd run typecheck`
- `npm.cmd run lint`
- `npm.cmd run format:check`
- `npm.cmd run repo:check`
- `npm.cmd test`: contracts 15 tests, API 82 tests, web 120 tests
- `npm.cmd run test:coverage`: web 95.67% statements, 85.30% branches,
  97.34% functions, and 95.65% lines.

The Vite build retained Leaflet as a separate 158.66 kB minified chunk and
reported the existing non-blocking main-chunk-size warning. No headless browser,
visual screenshot, or manual browser interaction was performed by design.

The latest visual refinement gives Forecast Overview a larger fractional share
of the left column than Other Locations, with separate tall- and short-viewport
ratios and a `20vh` date row instead of fixed panel heights. The selector stays
on the same row as its heading, uses a shorter fluid height, and preserves a
fluid gap before the map. Each overview metric now has its own line icon above
the value. Comparison cards keep their existing chance treatment but use a
compact, borderless icon-and-value row for cloudbase and overdevelopment risk,
retain a compact confidence footer, and use right-pointing chevrons. Web build,
typecheck, lint, formatting, repository structure validation, and all 17 web
test files / 112 tests passed. Web coverage passed at 96.17% statements, 88.85%
branches, 98.84% functions, and 96.19% lines. Manual visual acceptance remains
pending.

The 2026-07-24 follow-up removed the hard-coded comparison-location slugs.
Other Locations now sorts the API catalog by numeric ID, leaves the minimum-ID
entry as the default Overview location, and renders the following three catalog
entries. The summaries request deduplicates those three against the current
selection before sorting by ID. Comparison-card title-to-percentage spacing is
controlled by `--location-title-metric-gap` in
`LocationSummaryCard.module.scss`. The compact confidence meter was subsequently
restored below the cloudbase/overdevelopment row on each available comparison
card. A short-height wide-screen media query now reduces the comparison-card
title-to-metric gap for laptop-height viewports while preserving the large
monitor value. The location-panel heading is vertically centered against the
selector on wide layouts through a panel-specific header class. Web typecheck,
all 17 test files / 112 tests, production build, lint, formatting, and
repository structure validation passed. No browser automation or captured
output was used.

The map-pin follow-up rotates the CSS teardrop into the upright orientation and
centers its inner dot geometrically for both idle and selected states. Sofia -
Vitosha now places its permanent label below the pin and Zlatitsa places its
label above the pin to reduce overlap at the fitted overview zoom. The focused
map tests, all 17 web test files / 112 tests, typecheck, production build, lint,
and formatting passed without browser automation.

The matching pin inside the accessible location selector now uses the same
upright orientation and geometric inner-dot centering as the map markers.

The Forecast Inputs detail panel now keeps its fixed desktop layout while
placing the full input table inside a keyboard-focusable, vertically scrollable
region. This prevents long input rows from escaping the panel and preserves the
single-screen composition. Web tests (120), typecheck, and formatting checks
passed; no browser automation was run.

The detail date selector now shares the location selector's primary-colour
border. Forecast Inputs provenance metadata uses the same small muted treatment
as the generated-at detail metadata, and its scroll region is flex-bounded with
the panel body so the table ends above the panel's existing bottom padding.
Previous-run comparison now lists Cloudbase first. Web tests (120), typecheck,
and formatting checks passed.

The 2026-07-25 semantic and responsive pass removes generic visually hidden page
`h1` elements: the visible selected `site · date` is now the single page-level
heading in both Dashboard Overview and Forecast Details. The detail layout now
stacks below the shared wide breakpoint and, on wide screens, uses one shared
column-track definition plus viewport-height-specific row ratios; constrained
summary content can no longer overlap the lower panels. The reusable `SiteMap`
always renders one compass on both dashboard and detail maps, with contrasting
north and south pointers. Web build, lint, formatting, and all 22 web test files
/ 121 tests passed; no browser or screenshot automation was run.

The detail-page `h1` also follows Dashboard Overview's short-viewport override
of `1.45rem`, so the selected site/date heading remains the same size on laptop
and large-monitor layouts.

The 2026-07-24 detail-page refinement keeps `ConfidenceIndicator` as the one
shared meter while making its visible label and supplementary note configurable.
Forecast Overview and the main detail chance now say `Model confidence`; compact
date and comparison cards say `Conf.`. Each detailed output has the compact
meter in a separate subdued footer, matching the Other Locations treatment.
The primary chance label is now class-scoped, so it cannot override the
teal data-status badge colour. Web typecheck, lint, formatting, production
build, and all 22 web test files / 120 tests passed. No browser automation or
visual capture was run by request; manual visual acceptance remains pending.

## Current branch checkpoints

`feature/T-012-flight-schema` tracks
`origin/feature/T-012-flight-schema`. The committed T-009 through T-012 work is:

- `8923525 T-009-T-011 confirm site references and source research`
- `2a5d7e4 T-012 add Drizzle SQLite workspace`
- `6e5ff3f T-012 define flight foundation schema`
- `d04dd97 T-012 add initial flight database migrations`
- `fa07b87 T-012 verify flight migration foundation`
- `522db8d T-012 document database migration workflow`

## Next implementation step

Prepare T-013; do not implement or run an automated collector yet. Start by
reading this handoff, T-013 in `docs/tasks.md`, the T-010 XCContest report, and
the current decisions. Confirm a permitted input/export method and its allowed
scope before making source requests or retaining raw records.

When permission and a permitted sample are available, use the existing
`packages/database` schema and the local database selected by `DATABASE_URL`.
Keep raw inputs and rejected/ambiguous candidates out of Git, preserve
permission/provenance, and leave Drizzle as the sole DDL and migration owner.
T-012 is verified and awaiting review; do not alter its applied migrations.


## T-013 persistence slice - current (2026-08-11)

T-013 is now Review. Validation v2 records SHA-256/path pairs for accepted and quarantine JSONL. The new xccontest-persist command verifies raw/parser/validation artifacts and the current approved mapping snapshot, then writes one succeeded ingestion run and its accepted flights in a single transaction. It records browser_ui; existing run keys or source flights fail and rollback, leaving T-014 to own retry/upsert policy.

Verified first import: run f1032827-a98d-4c01-969e-e67b4885f90d, validation snapshot 94b4e0b6307d7ba6de6c0a0e180dad0d377f0ed7d4435b26092f6427b5a9d508, one succeeded run and 267 metadata-level flights. Counters: 1200 seen, 267 accepted, 664 rejected, 69 quarantined, 200 deduplicated. The policy, SQLite database, and artifacts remain ignored.
