# Project Handoff

## Handoff metadata

| Field | Value |
| --- | --- |
| Last updated | 2026-07-22 |
| Current Git branch | `feature/T-003-T-005-dashboard` |
| Branch relationship | Rebased onto `origin/main` at merge commit `d4167ff` after T-002 merged |
| Current tasks | T-003, T-004, and T-005 — `In Progress` |
| Completed scope in this branch | Dashboard API/contracts foundation, accepted implementation direction, and Stage 0 HTTP integration preflight; React UI is not implemented yet |
| Expected working tree after the Stage 0 commit | Clean |

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

No React implementation, database, ORM, new package, environment variable,
weather source, or model was added. Forecast values remain explicitly synthetic
`mock` data and must not be presented as aviation weather or flying advice.

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

## Intended React request ownership

The dashboard route/page should own request orchestration; presentational cards
should receive data rather than fetch independently.

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
- next checkpoint: `T-003-T-005 complete dashboard contract preflight`

The branch was rebased onto the T-002 merge in current `origin/main`. It has not
been pushed and no pull request was created.

## Next implementation step

Stage 0 is complete. Continue with the runnable React/Vite workspace, then the
validated client/query, URL state, visual foundation, overview, Leaflet map,
date strip, hardening, documentation, and validation checkpoints. Derive the
Other Locations order and visual copy from the supplied image, not API ID
order. The confirmed card order is Zlatitsa, Sofia - Vitosha, and Dobrich
region; the dashboard copy is English.

T-003-T-005 remain `In Progress` until the React dashboard and its relevant
validation are implemented. T-008 still owns the browser smoke-test tooling.
