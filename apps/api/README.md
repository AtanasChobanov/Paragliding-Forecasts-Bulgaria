# HTTP API

## Status

Directory scaffold only. The runnable Node.js + Express + TypeScript server is
the scope of **T-002**.

## Responsibilities

- Expose versioned HTTP endpoints for sites, dates, forecasts, and health.
- Validate request parameters and response payloads.
- Read forecast, provenance, and prediction records from the MVP store.
- Preserve data-status and confidence metadata for the UI.
- Provide structured errors and local observability.

The API must not contain React presentation logic or Python model-training
code. Its public payload shapes belong in `@paragliding-forecasts/contracts`.

## Planned stack

- Node.js
- Express
- TypeScript in strict mode
- SQLite for the MVP repository layer
- A runtime schema validator selected during API implementation

## Planned first endpoints

```text
GET /health
GET /api/v1/sites
GET /api/v1/forecasts?siteId=...&date=YYYY-MM-DD
```

The exact forecast response must include provenance and a status such as
`mock`, `manual`, `baseline`, `real`, or `missing` alongside the values.

## Planned layout

```text
apps/api/src/
|-- config/
|-- http/
|-- modules/forecast/
|-- repositories/
|-- app.ts
`-- server.ts
```

Keep `app.ts` free of the listen call so HTTP behavior can be tested without
binding a real port. Put process startup in `server.ts`.

## Commands after T-002

Run from the repository root:

```powershell
npm.cmd run dev:api
npm.cmd run build --workspace @paragliding-forecasts/api
npm.cmd run test --workspace @paragliding-forecasts/api
```

Until T-002 adds Express, an entry point, and package scripts, these are
documentation targets rather than working server commands.

## Configuration

- `API_PORT` - local HTTP port
- `CORS_ORIGIN` - allowed local dashboard origin
- `DATABASE_URL` - SQLite connection location for the MVP
- `LOG_LEVEL` - local logging verbosity
- `FORECAST_DATA_MODE` - explicit source/status for early forecast values

## Testing expectations

- Health endpoint test.
- Request-validation and error-shape tests.
- Repository tests using temporary or in-memory storage.
- Contract tests proving the API matches the shared response schema.
