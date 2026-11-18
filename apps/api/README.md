# HTTP API

## Status

The API reads the active site catalog, forecast summaries, five-day previews
and detailed forecasts from the local SQLite database. Explicit mock mode
serves synthetic data through the same public contracts.

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
calendar date, including dates outside the five-day preview. Unknown sites
return `404 SITE_NOT_FOUND`; unpublished exact site/dates return
`404 FORECAST_NOT_FOUND`. Missing individual metrics remain a valid response.

The response contains `siteId`, `siteSlug`, `forecastDate`, `generatedAt`,
`metadata`, `outputs`, `forecastInputs`, `explanations` and `cloudbaseHours`.
Outputs and metadata share the summaries' schemas and selection logic. A
late import of an older GFS cycle cannot displace a newer cycle. Selection
pins one prediction ID before any detail joins. A short read transaction
keeps the bounded batch of SQL reads consistent during publication. It never
fills a missing metric from another prediction.

`forecastInputs` retains the snapshot feature contract and the UTC endpoints
of the 10:00–20:00 Sofia window. `xcFeatures` contains all 67 policy fields in
policy order: 43 daily, 11 lower-layer and 13 upper-layer fields. Each row has
its canonical unit, statistic, scope, label, quality, data status, nullable
value, missing reason and eligible exact provenance ID. The static TypeScript
catalogue is checked against the packaged ML policy in tests. Runtime reads
SQLite only. Available real/derived GFS inputs carry `real` status; calculated
forecast outputs retain `baseline` status.

Eleven `hourlyContext` entries separate OD inputs from cloudbase context.
OD rain uses the exact adjacent interval and its end sample; surface-parcel
CAPE/CIN use the start sample. At 20:00 those three inputs say `Outside OD
interval inputs`. Low cloud, humidity and wind retain all eleven hours.
Cloudbase context includes surface fields, separately labelled stored weather
LCL and retained heat-flux intervals. Ambiguous intervals remain missing.
The full consumed T-022 model column is retained only in ML artifacts; the
API does not substitute the older SQL profile for it.

`explanations` contains the five metric groups in P100/P200/P300/OD/cloudbase
order. It preserves up to three drivers in their published ranks, their
metric-specific evidence and ordered input locators. Exact provenance links
must belong to the selected snapshot or its samples and match the named
field and time. Missing FK links retain their name/time and explain that the
exact input is retained in the ML artifact. XC contributions are logits
relative to the training reference. Q200 is the conditional step; pooled
P300 support is stored successes/total. OD points and critical overrides
retain their different meanings.

`cloudbaseHours` contains exactly eleven ordered Sofia hours, with explicit
regime, MSL/model AGL/signed site AGL heights, confidence, original reason code,
readable reason and optional note. Blue/other-cloud/missing hours have no
numeric heights. An indeterminate hour may retain a valid conditional LCL.
Estimated maxima take priority over conditional maxima. Runtime contracts
check actual Sofia/DST hours, metric evidence and daily/hourly consistency.
Broken mandatory graphs, conflicting provenance and corrupt maxima produce
5xx errors. Missing weather values retain their own missing states.

The adapter does not read raw/interim/prediction files, invoke Python or
calculate probabilities. Mock detail inputs and hours are explicitly synthetic.
The browser caches detail by slug/date until manual reload; Retry reissues a
failed request. See [the detail contract decision](../../docs/decisions.md#dec-073---read-published-details-and-exact-weather-evidence-in-one-viewport).

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
summary, detail and days endpoints and executes parameterized batched reads. Startup
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
