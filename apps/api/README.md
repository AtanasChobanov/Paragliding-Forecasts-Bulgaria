# HTTP API

## Status

The API reads the active site catalog and published forecast summaries and
days from the local SQLite database. It also supports an explicit mock mode
for demo forecasts and the current detail route.

## Run locally

From the repository root:

```powershell
npm.cmd run dev:api
```

The watch command builds the contracts and database workspaces and starts on
`http://127.0.0.1:3000` by default. SQLite mode requires an existing migrated
database. Apply migrations through the database workspace during setup. To run compiled output:

```powershell
npm.cmd run start:api
```

## Endpoints

| Method and path                                                            | Dashboard responsibility                                            |
| -------------------------------------------------------------------------- | ------------------------------------------------------------------- |
| `GET /health`                                                              | Service status, version, and current timestamp                      |
| `GET /api/v1/sites`                                                        | Active location-selector/map options, ordered by numeric ID      |
| `GET /api/v1/forecasts?siteSlug=sopot&date=YYYY-MM-DD`                     | Detailed location/date payload used by the routed detail page       |
| `GET /api/v1/forecasts/summaries?date=YYYY-MM-DD&siteSlugs=sopot,zlatitsa` | One batched set of dashboard overview cards for a date              |
| `GET /api/v1/forecasts/days?siteSlug=sopot`                                | Exactly five 100+ km preview slots centered on Sofia's current date |

All request and response payloads are validated with the shared strict Zod
contracts. Malformed, missing, repeated, or unsupported query values return
`400 VALIDATION_ERROR`. Errors use `application/problem+json` and responses
carry `X-Request-Id` for correlation.

### Site catalog

Each site has `{ id, slug, name, latitude, longitude }`. The response is sorted
by `id ASC`. In SQLite mode the coordinates are `sites.latitude_deg` and
`sites.longitude_deg`. These are the catalog positions used in the map.

### Detailed forecast

`/api/v1/forecasts` requires one valid `siteSlug` and one real `YYYY-MM-DD`
calendar date. It returns all five core outputs, per-output confidence/status,
provenance, mock forecast inputs with their source-run metadata/status, and top
drivers when the record exists. An unknown site returns `404 SITE_NOT_FOUND`; a known
site/date with no record returns `404 FORECAST_NOT_FOUND`.

The detail view uses this route in mock mode. In SQLite mode a direct
request for a known site returns `404 FORECAST_NOT_FOUND` with the reason that
details are unavailable. For a mock example,
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
  issue metadata, and the five overview metrics;
- `availability: "missing"` includes identity, date, and an explicit reason.

The reader selects a single publication per site and exact Sofia target date.
Eligible runs use operationally authorized GFS 06Z evidence from a succeeded
ingestion. The newest GFS cycle wins first, then publication timestamp and
numeric identifiers. An earlier cycle can supply that same site/date when
the latest cycle lacks it. A missing metric in the selected publication
retains its missing reason and any notes.

Calculated output values carry `baseline` status. The API converts stored
probabilities to percentages. The cloudbase union distinguishes estimated
cumulus cloudbase, conditional LCL, blue, other cloud, uncertain and missing.
Numeric maxima use the matching hourly record within the winning prediction.
Cloudbase heights use metres MSL and the optional OD score uses 0–100 points.

`generatedAt` is the publication timestamp. SQLite `metadata` supplies the
GFS cycle timestamp in UTC, horizon in Sofia calendar days, XC model, cloudbase
method and OD policy versions. `fromPreviousIssue` marks a future date within
D+1 through D+3 of the latest published cycle when the chosen row comes from
an earlier cycle. A corrupt selected row or incompatible response becomes a
5xx Problem Details error.

### Five-day selected-site preview

`/api/v1/forecasts/days` accepts only `siteSlug`. It intentionally has no date,
anchor, cursor, direction, limit, offset, or pagination parameters.

The response declares `timeZone: "Europe/Sofia"`, identifies `todayDate`, and
always contains these five ordered calendar slots:

```text
today - 2, today - 1, today, today + 1, today + 2
```

Each slot contains `forecastDate`, publication `availability`, and the
`chance100KmPct` metric. A date with no publication carries a `missingReason`
and a missing P100 metric. A date with a publication and missing P100 still
carries `availability: "available"`.

Calendar arithmetic is date-only and DST-safe. The service derives the current
date in `Europe/Sofia`, then shifts calendar dates through UTC construction;
it does not add fixed 24-hour timestamp durations.

## React data-loading boundary

The home route first reads the site catalog and then days for the selected
site. Once an available date is selected, a single deduplicated summary
request supplies both the overview and the comparison cards. The
[web README](../web/README.md#url-selection-behavior) defines URL fallback and
refresh behavior.

## Deliberate missing-data semantics

| Read model        | Missing forecast behavior                         |
| ----------------- | ------------------------------------------------- |
| Detailed forecast | `404 FORECAST_NOT_FOUND`                          |
| Batched summaries | `200` with an `availability: "missing"` item      |
| Five-day preview  | `200` with a fixed slot with `availability: "missing"` |

## Mock snapshot limitation

The in-memory mock repository creates 35 forecast records when the API starts:
seven sites multiplied by the Sofia startup date minus two through plus two.
Its values and `generatedAt` timestamp remain stable for that process. Because
the five-day endpoint derives Sofia's current date per request, a development
server kept running across Sofia midnight can outlive that synthetic snapshot.
Restart the mock API after a local-date rollover.

## Internal structure

```text
apps/api/src/
|-- config/                  # Startup-only environment validation
|-- http/                    # Root router, validation, errors, middleware
|-- modules/
|   |-- forecasts/           # Controller, service, repository port, SQLite and mock adapters
|   |-- health/              # Health transport module
|   `-- sites/               # Controller, service, repository port, SQLite and memory adapters
|-- observability/           # Pino root and HTTP loggers
|-- app.ts                   # Pure Express application factory
|-- bootstrap.ts             # Configured application and data-source lifetime
|-- main.ts                  # Process lifecycle
`-- server.ts                # TCP listen/close lifecycle
```

Controllers validate transport data. The service coordinates catalog,
clock and repository reads. The SQLite adapter shares selection logic for the
summary and days endpoints and executes parameterized batched reads. Startup
prepares the statements to verify the required tables and columns.

## Configuration

The API loads the root `.env` when present and validates only values it uses.

| Variable             | Default                 | Constraint                                                |
| -------------------- | ----------------------- | --------------------------------------------------------- |
| `NODE_ENV`           | `development`           | `development`, `test`, or `production`                    |
| `LOG_LEVEL`          | `info`                  | Pino level or `silent`; `.env.example` uses local `debug` |
| `API_HOST`           | `127.0.0.1`             | Non-empty bind host                                       |
| `API_PORT`           | `3000`                  | Integer from 1 through 65535                              |
| `CORS_ORIGIN`        | `http://localhost:5173` | Exact HTTP(S) origin without path/trailing slash          |
| `FORECAST_DATA_MODE` | `sqlite`                | `sqlite` for published forecasts or explicit `mock` for demo |
| `DATABASE_URL`       | `file:./data/local/paragliding.db` | Repository-relative `file:` URL below `data/` |

The API opens the configured SQLite file read-only and closes it on shutdown.
An invalid path, missing file or missing forecast schema aborts startup.
A correctly migrated database with no publications starts normally. Existing
`.env` files with `FORECAST_DATA_MODE=mock` continue to select mock mode. Set
`FORECAST_DATA_MODE=sqlite` in `.env` or pass it to the command to read local
publications.

CORS allows GET/OPTIONS from the configured dashboard origin and non-browser
requests without an `Origin` header.

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
lifecycle. SQLite integration tests use a temporary migrated database
with deterministic publications. Browser fixtures cover both runtime modes.

## Storage and safety boundaries

Ingestion, inference and publication belong to the
[ML workflow](../../services/ml/README.md#publish-and-retain-operational-forecasts-t-025).
The API reads persisted forecasts independently of the retained GRIB payloads.

The API is decision-support infrastructure, not an aviation weather or safety
service. Mock values must never be presented as observed conditions, model
predictions, or flying guarantees.
