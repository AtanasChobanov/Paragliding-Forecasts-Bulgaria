# Architecture

## Goals

- Deliver a useful local dashboard early, even while forecast values are mock
  or baseline data.
- Keep product-facing code in TypeScript where practical.
- Isolate Python to data and ML workloads that benefit from its ecosystem.
- Preserve provenance, units, confidence, quality, and data status end to end.
- Start with inspectable local components and defer distributed infrastructure.

## Component boundaries

```text
Browser
  |
  v
React dashboard (apps/web)
  |
  | versioned JSON contracts
  v
Express API (apps/api) ------> SQLite / local forecast store
  ^                                      ^
  |                                      |
  | documented records/files             | derived features and predictions
  |                                      |
Python data + ML pipeline (services/ml) -+
  ^
  |
Flight, weather, reanalysis, and sounding sources
```

`packages/contracts` owns browser-facing runtime schemas and inferred
TypeScript types. It does not force Python to consume TypeScript. The
Python/Node boundary stays language-neutral through documented storage schemas
or serialized records.

## Web dashboard

The dashboard owns presentation and user interaction only. It selects a site
and date, calls the API, and renders forecast values with their status,
confidence, units, provenance, loading state, and error state. It does not read
SQLite or calculate prediction probabilities.

For the initial dashboard, route-level React state owns request orchestration.
It fetches the site catalog once, makes one deduplicated multi-site summary
request for the selected date, and makes one fixed five-day preview request for
the selected site. Presentational cards consume those results as props rather
than issuing per-component requests. The detailed page later owns the existing
single-site/date forecast request.

## Express API

The API is the browser-facing boundary. It validates requests and responses,
reads repository records, and maps them to stable public contracts. Transport
concerns remain separate from domain/service and repository logic so tests can
run without binding ports or depending on live sources.

T-002 adopts a feature-oriented modular structure. Each feature keeps its
controller, service, repository port, and current adapter together; shared HTTP
middleware, startup configuration, and observability remain cross-cutting
folders. `main.ts` is the composition root and wires dependencies manually.
`app.ts` constructs Express without listening, while `server.ts` owns TCP
startup and graceful closure.

This is dependency injection without a container. A container should be added
only if measured composition complexity, scoped lifetimes, or multiple runtime
bindings justify it.

The HTTP boundary uses strict Zod schemas from `packages/contracts`, Pino for
structured/redacted logs and request correlation, and
`application/problem+json` for globally handled errors. The current sites and
forecasts adapters are in-memory/mock implementations for Takt 1 UI work.

The forecast feature exposes three read shapes with intentional missing-data
semantics: a detailed lookup fails with `FORECAST_NOT_FOUND`, batched summaries
keep a missing site item, and the fixed Sofia-calendar preview keeps a missing
metric in its date slot. Repository ports support nullable single reads,
multi-site reads for one date, and inclusive date-range reads for one site.
Pure response mapping lives in a stateless feature module rather than in the
service class or a state-free helper class; the service remains responsible for
use-case orchestration and dependency-backed behavior.

## Python data and ML pipeline

The initial Python component is a batch workflow, not a public microservice. It
collects permitted source data, generates features, trains transparent
baselines, backtests results, and writes versioned predictions. An HTTP service
should be introduced only if a measured runtime requirement justifies it.

## Storage

SQLite remains the MVP direction because it is local, inspectable, and easy to
back up. Repository interfaces in the API prevent storage details from leaking
into HTTP handlers.

T-012 owns the first persistence foundation. It uses a new TypeScript workspace
under `packages/database` for the Drizzle schema, generated/reviewed SQL
migrations, and Node-side database connection primitives. Drizzle/Drizzle Kit
are the sole owners of schema DDL and migration history. The API imports the
schema through repository adapters; it does not expose SQLite details to HTTP
handlers.

T-012 is deliberately limited to the Takt 2 flight-data foundation, not the
whole eventual product schema. It creates only the tables required to persist
validated flight evidence and its relationship to the existing site catalog:

- canonical `sites` records, retaining the current numeric IDs and public
  slugs;
- source-specific site aliases/takeoff mappings for later XCContest matching;
- `ingestion_runs` provenance for an import execution;
- canonical `flight_records` with source identity, raw takeoff evidence,
  canonical site relationship, selected distance, track link, validation, and
  provenance fields.

Exact columns, types, indexes, checks, nullable rules, and migration names are
an explicit T-012 design deliverable. Weather features, soundings, processed
feature sets, model runs, predictions, and alerts are deferred to their owning
tasks; T-012 must not pre-create speculative tables for them.

The physical SQLite schema is a language-neutral boundary. Python batch code
may read/write the migrated file through a non-migrating persistence adapter,
but must not create tables or run a second migration system. A T-013 run has
the following durable flow:

```text
permitted XCContest input/export
  -> immutable raw artifact
  -> source parser
  -> normalized/validated staging record
  -> site matching and duplicate decision
  -> SQLite flight_records transaction
```

Raw acquisition artifacts are not database rows and are not committed. They
enable repeatable parsing, auditability, and reprocessing without another
source request. Canonical accepted flight records are written to SQLite;
ambiguous or rejected candidates remain in ignored interim/quarantine outputs.

The initial project-brief prediction fields map to the T-002 internal
`ForecastPrediction` domain model: numeric site identity/date, generation
timestamp, cloudbase, three XC probability bands, overdevelopment risk,
confidence, and top drivers. This model is neither an ORM/database row nor the
public HTTP DTO. A persisted schema must additionally define probability scale,
cloudbase MSL/AGL semantics, per-output missing/status behavior, provenance,
and source/model version before it can be considered compatible with the
public contract.

Site identity has two explicit forms. A positive integer is the internal ID and
future persistence relationship key; a unique lowercase slug is the public API
lookup key. Slug changes must not require rewriting prediction, weather, or
alert relationships.

The Takt 1 site payload also includes provisional latitude/longitude values for
map placement and is explicitly ordered by numeric ID. It does not contain a
presentation-specific dashboard order. T-009 still owns final coordinate,
alias, and catchment-radius validation.

## Forecast record principles

Every displayed forecast must preserve:

- site and forecast date;
- generation timestamp and source/model version;
- cloudbase with explicit MSL/AGL unit semantics;
- 100+ km, 200+ km, and 300+ km outputs with an explicit probability scale;
- overdevelopment risk and its main drivers;
- confidence and top forecast drivers;
- one explicit data status: `mock`, `manual`, `baseline`, `real`, or `missing`.

Missing values are not zero. Mock or baseline values are not real observations.
Those distinctions must survive ingestion, storage, API serialization, and UI
rendering.

The contract models these states from one canonical five-state Zod enum. Its
available-value subset is derived by excluding `missing` and is used only for
the discriminated-union branch that also requires a value and confidence. The
`missing` branch instead requires `null` value/confidence and an explicit
reason, preventing contradictory combinations at the HTTP boundary.

## Deferred decisions

- Exact external forecast and historical archive providers
- Source-specific ingestion permissions and rate limits
- Final launch coordinates, aliases, and catchment radii
- Exact T-012 physical column types, constraints, indexes, and migration
  details within the accepted Takt 2 persistence scope
- Alert delivery channel
- Deployment or cloud infrastructure

These should be decided in the ticket that has enough evidence to own the
trade-off, not guessed during earlier work.
