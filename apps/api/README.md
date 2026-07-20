# HTTP API

## Status

T-002 provides a runnable Node.js 24, Express 5, and strict TypeScript API. It
serves health, site-catalog, and deterministic per-site mock values for the next
dashboard tickets. Response timestamps reflect request time. The API does not
connect to SQLite or any weather/model source yet.

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

| Method and path | Result |
| --- | --- |
| `GET /health` | Service status, version, and current timestamp |
| `GET /api/v1/sites` | Numeric IDs, unique public slugs, and display names for the seven initial areas |
| `GET /api/v1/forecasts?siteSlug=sopot&date=2026-07-18` | Contract-validated forecast selected by slug with deterministic per-site mock values |

The forecast query requires one syntactically valid `siteSlug` and one real
calendar date in `YYYY-MM-DD` format. A valid but unknown slug returns `404`;
malformed or missing query data returns `400`. Site IDs are positive safe
integers reserved for internal identity and future persistence relationships;
slugs are the stable human-readable API lookup key.

Every forecast output is a value/status object. Present values include
`dataStatus` and confidence; units are explicit in field names. Forecast-level
provenance identifies the source/version, and missing values are represented
explicitly rather than coerced to zero. The T-002 repository always returns
`mock` values; `dataStatus` and `confidence.note` identify the payload as
non-operational development data.

The shared contract defines one canonical five-state `dataStatusSchema` and
derives its non-missing subset for metrics that contain a value. A `missing`
metric cannot contain a numeric/category value or confidence and must provide a
reason; the current mock adapter only emits the non-missing `mock` branch.

Errors use `application/problem+json` and a stable problem-details contract.
Responses include an `X-Request-Id`, accepting a safe incoming value or
generating one for correlation.

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

The structure is feature-oriented with explicit layers inside features. This
keeps related code together as the project grows while preserving transport,
business, and persistence boundaries. Dependencies are wired manually in
`main.ts`; a dependency-injection container would add complexity without a
current lifecycle or binding requirement.

`app.ts` never binds a port, so integration tests can exercise the complete
HTTP pipeline in memory. Repository interfaces let later SQLite adapters
replace the current in-memory/mock adapters without changing controllers.

## Configuration

The API loads the root `.env` when present, validates only values it consumes,
and otherwise uses safe local defaults.

| Variable | Default | Constraint |
| --- | --- | --- |
| `NODE_ENV` | `development` | `development`, `test`, or `production` |
| `LOG_LEVEL` | `info` | Pino level or `silent`; `.env.example` explicitly uses local `debug` |
| `API_HOST` | `127.0.0.1` | Non-empty bind host |
| `API_PORT` | `3000` | Integer from 1 through 65535 |
| `CORS_ORIGIN` | `http://localhost:5173` | Exact HTTP(S) origin, without path or trailing slash |
| `FORECAST_DATA_MODE` | `mock` | T-002 accepts only `mock` |

`DATABASE_URL` and `MODEL_ARTIFACT_DIR` remain in `.env.example` as future
repository/model settings. T-002 deliberately does not validate or consume
them because it does not implement persistence.

CORS allows GET/OPTIONS from the configured dashboard origin and non-browser
requests without an `Origin` header. Credentials are disabled.

## Logging and shutdown

Pino emits structured logs; `pino-http` adds request/response records and
correlation IDs. Authorization, cookie, and set-cookie fields are redacted.
Development output is pretty-printed; production remains JSON. The process
handles `SIGINT` and `SIGTERM`, stops accepting connections, and force-closes
remaining connections after the grace period.

## Commands and tests

From the repository root:

```powershell
npm.cmd run build --workspace @paragliding-forecasts/api
npm.cmd run typecheck --workspace @paragliding-forecasts/api
npm.cmd run test --workspace @paragliding-forecasts/api
npm.cmd run test:coverage --workspace @paragliding-forecasts/api
npm.cmd run test:watch --workspace @paragliding-forecasts/api
```

The suite includes focused unit tests, in-memory HTTP integration tests, shared
response-contract checks, a real `pino-http` credential-redaction test, and an
ephemeral-port server smoke test. V8 coverage includes every `src/**/*.ts` file
and enforces minimum global thresholds of 70% statements/lines/functions and
75% branches. Database component tests and end-to-end browser tests are deferred
until their owning persistence and dashboard tickets exist.

## Storage compatibility and limits

The mock repository returns an internal `ForecastPrediction` domain model
aligned with the initial `predictions` proposal in `docs/project-brief.md`:
numeric site identity, date, generation time, cloudbase, three probability
bands, overdevelopment risk, confidence, and top drivers. It is deliberately
not a database row or the public HTTP DTO. The service mapper adds the public
site slug and explicit units/status structure required at the browser boundary.

No database, migrations, ORM/query builder, or persistence adapter is part of
T-002. Before a real prediction schema is implemented, its owning ticket must
make probability scale, cloudbase reference (`MSL` versus `AGL`), per-output
missing/status semantics, provenance, and source/model version explicit rather
than inferring them from the current draft table. A future `sites` table should
use the numeric ID as its primary key and enforce a unique slug; forecast lookup
continues to use the slug at the HTTP boundary.

The current internal mock prediction requires every output and its repository
port always returns a prediction. A future real adapter must refine that
boundary for a missing site/date record and mixed per-output missing states;
the public contract already represents missing metrics explicitly.

## Responsibilities

The API may validate browser requests and map repository records to stable
contracts. It must not contain React presentation logic or Python training
logic, and it must not present current mock values as observed or operational
forecast data.
