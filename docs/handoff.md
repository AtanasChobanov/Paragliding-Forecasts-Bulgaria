# Project Handoff

## Handoff metadata

| Field | Value |
| --- | --- |
| Last updated | 2026-07-22 |
| Current Git branch | `feature/T-003-T-005-dashboard` |
| Branch relationship | Created from rebased `feature/T-002-local-server-skeleton` at `ab81a70`; intentionally stacked until T-002 is merged |
| Current tasks | T-003, T-004, and T-005 — `In Progress` |
| Completed scope in this branch | Dashboard API/contracts foundation; React UI is not implemented yet |
| Expected working tree after the response-mapper commit | Clean |

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
2. Store selected site slug and date in dashboard state.
3. Deduplicate the selected site plus the default Other Locations slugs and
   fetch them through one summaries request.
4. Index summaries by slug because the API sorts by ID, not request order. If
   the selected site is also a default card, reuse the same summary in both
   positions.
5. Fetch `/api/v1/forecasts/days` when the selected site changes.
6. Navigate the detailed button with selected slug/date; the detailed page
   later owns `/api/v1/forecasts`.

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

Accepted design decisions are recorded as DEC-015 and DEC-016 in
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

## Git checkpoints

This branch contains these reviewable commits after the T-002 base:

- `54bd271 T-004 add provisional site map coordinates`
- `4acc6b1 T-003-T-005 define dashboard forecast contracts`
- `bb18bfd T-003-T-005 add date-aware forecast fixtures`
- `58841d5 T-003-T-005 add forecast summary endpoint`
- `bf7192c T-005 add five-day forecast preview endpoint`
- `3180131 T-003-T-005 harden dashboard API implementation`
- `518e1fb T-003-T-005 document dashboard API foundation`
- final `T-003-T-005 extract forecast response mapper` commit containing this
  handoff

No branch was pushed and no pull request was created. After T-002 is merged,
fetch and rebase this branch onto the updated `origin/main`; do not use a stale
local `main` as the rebase target.

## Next implementation step

Continue T-003-T-005 in `apps/web`:

- turn the React/Vite scaffold into a runnable dashboard workspace;
- implement route-level query/state ownership described above;
- build the header, selected forecast overview, map/location selector, default
  Other Locations cards, and five-card date strip from the approved mockup;
- label `mock` and missing data clearly and implement loading/error/empty states;
- keep the detailed forecast destination outside this dashboard slice;
- add the real web commands and their documentation in the same UI change.

T-003-T-005 remain `In Progress` until the React dashboard and its relevant
validation are implemented. T-008 still owns the browser smoke-test tooling.
