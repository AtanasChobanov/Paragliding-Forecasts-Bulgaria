# Project Handoff

## Handoff metadata

| Field | Value |
| --- | --- |
| Last updated | 2026-07-23 |
| Current Git branch | `feature/T-003-T-005-dashboard` |
| Branch relationship | Rebased onto `origin/main` at merge commit `d4167ff` after T-002 merged |
| Current tasks | T-003, T-004, and T-005 — `In Progress` |
| Completed scope in this branch | Dashboard API/contracts foundation, Stage 0 preflight, runnable React/Vite workspace, validated queries/URL orchestration, responsive visual foundation, forecast overview/comparison cards, Leaflet site selector, and five-day date selector |
| Expected working tree after the Stage 7 commit | Clean |

## Current outcome

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
Cyrillic coverage, CSS theme tokens, a responsive framed layout, a semantic
application header, four stable dashboard regions, and reusable panel/content-
state primitives. Forecast values remain explicitly synthetic `mock` data and
must not be presented as aviation weather or flying advice.

The selected overview now renders the five contracted metrics with explicit
units plus generated-at, provenance, confidence, and data-status context. The
Other Locations region renders Zlatitsa, Sofia - Vitosha, and Dobrich region in
that fixed UI order without filtering a duplicate selected site. Summary-level
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
- The visible header states `Decision support only` and `Not aviation weather`;
  it intentionally omits the reference image's decorative bell and any broken
  detailed-forecast action.
- Forecast date-only labels are formatted with UTC calendar parts, while
  generation instants are rendered in `Europe/Sofia`; no naive date-only parse
  can move the visible forecast to a different day.
- The dashboard does not render the reference image's detailed-forecast button.
  T-006 owns both the real route and its action, so this checkpoint does not
  ship a disabled or misleading control.
- Leaflet is loaded through a separate production chunk. OSM Standard is a
  runtime internet dependency with no offline or SLA guarantee; the provider
  URL, linked attribution, maximum zoom, and policy URL are centralized.
- The five-card strip uses `aria-current="date"` for API today and
  `aria-pressed` for the URL-selected date. It has no hidden date expansion,
  arrows, qualitative weather labels, or invented iconography.

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

- Remains the single-site/date payload intended for the later detailed page.
- Returns full outputs, provenance, and top drivers for a present fixture.
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
3. Deduplicate the selected site plus the default Other Locations slugs and
   fetch them through one summaries request.
4. Index summaries by slug because the API sorts by ID, not request order. If
   the selected site is also a default card, reuse the same summary in both
   positions.
5. Fetch `/api/v1/forecasts/days` when the selected site changes.
6. Omit the detailed action in T-003-T-005. T-006 adds the control together
   with its real route and later owns `/api/v1/forecasts`; do not ship a broken,
   disabled, or placeholder dashboard control now.

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

Accepted design decisions are recorded as DEC-015 through DEC-017 in
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
  metrics, summary-level missing and omitted content, explicit Other Locations
  order versus response-map order, and a selected site retained as a card;
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
- next checkpoint: `T-005 add five-day forecast selector`

The branch was rebased onto the T-002 merge in current `origin/main`. It has not
been pushed and no pull request was created.

## Next implementation step

Harden cross-cutting dashboard states and accessibility: actionable scoped
errors with request IDs when available, stable loading/empty/missing regions,
restrained live announcements, keyboard/focus behavior, and narrow-screen
overflow protection. Then finish documentation and the full validation gate.

T-003-T-005 remain `In Progress` until the React dashboard and its relevant
validation are implemented. T-008 still owns the browser smoke-test tooling.
