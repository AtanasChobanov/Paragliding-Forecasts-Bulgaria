# Project Handoff

## Handoff metadata

| Field | Value |
| --- | --- |
| Last updated | 2026-08-02 |
| Current Git branch | `feature/T-008-browser-smoke-test` |
| Branch relationship | Extends `feature/T-006-T007-forecast-details-page` at `922ceef`, which extends the dashboard implementation at `e744bc5` |
| Current tasks | T-009 through T-012 — `Review` |
| Completed scope in this branch | Dashboard/detail implementation plus Playwright Chromium smoke-test configuration, dashboard and detail smoke scenarios, commands, and documentation |
| Current working tree note | T-009–T-011 and the five T-012 foundation checkpoints are committed; local database files remain ignored |

## T-010 and T-011 flight-source research - read before T-012/T-013

T-010 research is complete and the report is available at
`T-010-xccontest-research-report.md` (updated 2026-07-28). Treat its result as
**Review**, not as permission to implement a collector.

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
`T-011-skynomad-research-report.md` (2026-07-28). Its status is **Review**.
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

| Read model | Behavior |
| --- | --- |
| Detailed | `404 FORECAST_NOT_FOUND` |
| Summaries | `200` missing item |
| Days | `200` fixed slot with missing p100 metric |

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

## Git checkpoints

This branch contains these reviewable commits after the T-002 base:

- `3c7283b T-004 add provisional site map coordinates`
- `34dabe5 T-003-T-005 define dashboard forecast contracts`
- `e0d07e8 T-003-T-005 add date-aware forecast fixtures`
- `035ba8e T-003-T-005 add forecast summary endpoint`
- `af54e88 T-005 add five-day forecast preview endpoint`
- `5aa3250 T-003-T-005 harden dashboard API implementation`
- `1519111 T-003-T-005 document dashboard API foundation`
- `6eb8352 T-003-T-005 extract forecast response mapper`
- `ac6adf9 T-003-T-005 complete dashboard contract preflight`
- `9cea79b T-003 scaffold runnable React dashboard workspace`
- `5abe401 T-003-T-005 add validated dashboard API queries`
- `71bbc4f T-003-T-005 coordinate dashboard URL state`
- `ce068f8 T-003 establish dashboard visual foundation`
- `ee517d5 T-003 render dashboard forecast overview`
- `3d362a8 T-004 add interactive Leaflet site selector`
- `3fe4557 T-005 add five-day forecast selector`
- `9644d30 T-003-T-005 harden dashboard states and accessibility`
- final checkpoint: `T-003-T-005 document dashboard setup and limitations`

The branch was rebased onto the T-002 merge in current `origin/main`. It has not
been pushed and no pull request was created.

## Next implementation step

The browser smoke suite has passed; rerun it when making later UI
changes or when validating a clean checkout.
Manual review still owns desktop/narrow visual fidelity, copied URLs/history,
real Leaflet tiles/pan/zoom/labels, focus appearance, degraded requests/tiles,
and the browser console.

T-012 can proceed with a source-neutral schema that preserves
permission/provenance/validation status, but its 100+/200+/300+ distance rule
must be confirmed before sample labels are final.
