# HTTP API

## Status

The API foundation for T-003-T-007 is implemented on top of the T-002 local
server. It exposes a map-ready site catalog, detailed per-site forecasts, a
batched dashboard summary read model, and a fixed five-day preview for the
selected site. All current forecast values are deterministic `mock` fixtures;
there is no SQLite or weather/model integration yet.

## Run locally

From the repository root:

```powershell
npm.cmd run dev:api
```

The watch process builds `@paragliding-forecasts/contracts` first and starts on
`http://127.0.0.1:3000` by default. To run compiled output:

```powershell
npm.cmd run start:api
```

## Endpoints

| Method and path                                                            | Dashboard responsibility                                            |
| -------------------------------------------------------------------------- | ------------------------------------------------------------------- |
| `GET /health`                                                              | Service status, version, and current timestamp                      |
| `GET /api/v1/sites`                                                        | All seven location-selector/map options, ordered by numeric ID      |
| `GET /api/v1/forecasts?siteSlug=sopot&date=YYYY-MM-DD`                     | Detailed location/date payload used by the routed detail page       |
| `GET /api/v1/forecasts/summaries?date=YYYY-MM-DD&siteSlugs=sopot,zlatitsa` | One batched set of dashboard overview cards for a date              |
| `GET /api/v1/forecasts/days?siteSlug=sopot`                                | Exactly five 100+ km preview slots centered on Sofia's current date |

All request and response payloads are validated with the shared strict Zod
contracts. Malformed, missing, repeated, or unsupported query values return
`400 VALIDATION_ERROR`. Errors use `application/problem+json` and responses
carry `X-Request-Id` for correlation.

### Site catalog

Each site has `{ id, slug, name, latitude, longitude }`. There is deliberately
no `dashboardOrder`: the response is always sorted by `id ASC`. The coordinates were confirmed in T-009. The corrected location name is `Pastrina`, with slug `pastrina`
and the existing numeric ID `6`.

### Detailed forecast

`/api/v1/forecasts` requires one valid `siteSlug` and one real `YYYY-MM-DD`
calendar date. It returns all five core outputs, per-output confidence/status,
provenance, mock forecast inputs with their source-run metadata/status, and top
drivers when the record exists. An unknown site returns `404 SITE_NOT_FOUND`; a known
site/date with no record returns `404 FORECAST_NOT_FOUND`.

This route is the data source for `/forecast?site=<slug>&date=YYYY-MM-DD`. The
dashboard does not fetch it once per card; its selected action and comparison
cards navigate to the detail route instead. For an available mock example,
first call `/api/v1/forecasts/days?siteSlug=sopot` and use one of the returned
`forecastDate` values; the finite fixture window moves with API startup date.

### Dashboard summaries

`/api/v1/forecasts/summaries` accepts:

- `date`: one real `YYYY-MM-DD` calendar date;
- `siteSlugs`: one comma-separated string containing one through seven unique
  site slugs.

Empty segments, duplicate slugs, repeated `siteSlugs` query keys, more than
seven slugs, and unknown query fields are rejected. Every site is resolved
before forecast storage is queried; one valid but unknown slug therefore
returns `404 SITE_NOT_FOUND` for the request.

Successful summaries are sorted by `siteId ASC`, regardless of request order.
Each requested site produces exactly one item:

- `availability: "available"` includes identity, date, generation time,
  provenance, and the five overview metrics;
- `availability: "missing"` includes identity, date, and an explicit reason.

A missing forecast does not fail the batch. The route returns `200` so the
dashboard can render available and unavailable cards together. Metric-level
`dataStatus` and confidence remain the source of truth; there is no duplicate
top-level data-status field.

### Five-day selected-site preview

`/api/v1/forecasts/days` accepts only `siteSlug`. It intentionally has no date,
anchor, cursor, direction, limit, offset, or pagination parameters.

The response declares `timeZone: "Europe/Sofia"`, identifies `todayDate`, and
always contains these five ordered calendar slots:

```text
today - 2, today - 1, today, today + 1, today + 2
```

Each slot contains only `forecastDate` and the existing `chance100KmPct` metric
union. The metric preserves the numeric percentage,
`mock`/`manual`/`baseline`/`real` status, and confidence when available. If a
date has no prediction, the slot stays in place with a `missing` metric rather
than disappearing, shifting, or becoming zero. A known site therefore receives
`200` with five slots even when some forecast records are absent.

Calendar arithmetic is date-only and DST-safe. The service derives the current
date in `Europe/Sofia`, then shifts calendar dates through UTC construction;
it does not add fixed 24-hour timestamp durations.

## React data-loading boundary

The initial dashboard should coordinate requests at the route/page level and
pass data to presentational components. Individual cards should not perform
their own independent fetches.

1. Fetch `/api/v1/sites` once for the location selector and map pins.
2. Keep selected site slug and selected date in dashboard state.
3. Form one deduplicated slug set from the selected overview site plus the
   default Other Locations cards, then make one summaries request.
4. Index returned summaries by `siteSlug`; responses are ID-ordered, not
   request-ordered. Reuse the same item if the selected site is also one of the
   default cards.
5. Fetch `/api/v1/forecasts/days` when the selected site changes. The date
   cards use only its five returned slots and do not paginate.
6. The detailed-forecast button and Other Locations cards navigate with the
   selected slug/date; the destination page owns its detailed forecast request.

This produces two forecast requests for the dashboard state—one batched
summary request and one five-day preview request—rather than one request per UI
component.

## Deliberate missing-data semantics

| Read model        | Missing forecast behavior                         |
| ----------------- | ------------------------------------------------- |
| Detailed forecast | `404 FORECAST_NOT_FOUND`                          |
| Batched summaries | `200` with an `availability: "missing"` item      |
| Five-day preview  | `200` with a fixed slot whose metric is `missing` |

## Mock snapshot limitation

The in-memory mock repository creates 35 forecast records when the API starts:
seven sites multiplied by the Sofia startup date minus two through plus two.
Its values and `generatedAt` timestamp remain stable for that process. Because
the five-day endpoint derives Sofia's current date per request, a development
server kept running across Sofia midnight can outlive that synthetic snapshot.
Restart the API after a local-date rollover. This limitation disappears when a
date-aware persisted prediction repository replaces the mock adapter.

## Internal structure

```text
apps/api/src/
|-- config/                  # Startup-only environment validation
|-- http/                    # Root router, validation, errors, middleware
|-- modules/
|   |-- forecasts/           # Controller, service, repository port, mock adapter
|   |-- health/              # Health transport module
|   `-- sites/               # Controller, service, repository port, memory adapter
|-- observability/           # Pino root and HTTP loggers
|-- app.ts                   # Pure Express application factory
|-- main.ts                  # Composition root and process lifecycle
`-- server.ts                # TCP listen/close lifecycle
```

Controllers validate transport data, the service orchestrates site lookup,
clock, and repository reads, and stateless mapper functions translate internal
predictions into browser-facing response models. The repository port owns
single, batched, and inclusive-range prediction reads. Services construct
response order independently of repository result order. Dependencies remain
manually wired in `main.ts`; no DI container or storage library is needed for
the current scope.

## Configuration

The API loads the root `.env` when present and validates only values it uses.

| Variable             | Default                 | Constraint                                                |
| -------------------- | ----------------------- | --------------------------------------------------------- |
| `NODE_ENV`           | `development`           | `development`, `test`, or `production`                    |
| `LOG_LEVEL`          | `info`                  | Pino level or `silent`; `.env.example` uses local `debug` |
| `API_HOST`           | `127.0.0.1`             | Non-empty bind host                                       |
| `API_PORT`           | `3000`                  | Integer from 1 through 65535                              |
| `CORS_ORIGIN`        | `http://localhost:5173` | Exact HTTP(S) origin without path/trailing slash          |
| `FORECAST_DATA_MODE` | `mock`                  | The current API accepts only `mock`                       |

`DATABASE_URL` and `MODEL_ARTIFACT_DIR` remain reserved and unused. CORS allows
GET/OPTIONS from the configured dashboard origin and non-browser requests
without an `Origin` header; credentials are disabled.

## Commands and tests

From the repository root:

```powershell
npm.cmd run build --workspace @paragliding-forecasts/api
npm.cmd run typecheck --workspace @paragliding-forecasts/api
npm.cmd run test --workspace @paragliding-forecasts/api
npm.cmd run test:coverage --workspace @paragliding-forecasts/api
npm.cmd run test:watch --workspace @paragliding-forecasts/api
```

Tests cover shared contracts, Sofia timezone/calendar boundaries, repository
batch/range reads, missing records and slots, request ordering, strict query
validation through Express, globally handled errors, logging, and real server
lifecycle. Database component tests and browser tests remain deferred to their
own implementation tickets.

## Storage and safety boundaries

No database, migration, ORM/query builder, live weather source, or trained
model is implemented. A future adapter must preserve explicit units, missing
states, status, confidence, provenance, and source/model version when replacing
the mock repository.

The API is decision-support infrastructure, not an aviation weather or safety
service. Mock values must never be presented as observed conditions, model
predictions, or flying guarantees.
