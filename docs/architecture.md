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

## Python data and ML pipeline

The initial Python component is a batch workflow, not a public microservice. It
collects permitted source data, generates features, trains transparent
baselines, backtests results, and writes versioned predictions. An HTTP service
should be introduced only if a measured runtime requirement justifies it.

## Storage

SQLite remains the MVP direction because it is local, inspectable, and easy to
back up, but T-002 does not implement a database. Repository interfaces in the
API prevent storage details from leaking into HTTP handlers. The first owning
schema/persistence ticket must select an access and migration approach with
evidence; no ORM has been chosen implicitly.

The initial project-brief prediction fields map to the T-002 internal forecast
record: site/date, generation timestamp, cloudbase, three XC probability
bands, overdevelopment risk, confidence, and top drivers. A persisted schema
must additionally define probability scale, cloudbase MSL/AGL semantics,
per-output missing/status behavior, provenance, and quality metadata before it
can be considered compatible with the public contract.

## Forecast record principles

Every displayed forecast must preserve:

- site and forecast date;
- generation timestamp and source/model version;
- cloudbase with explicit MSL/AGL unit semantics;
- 100+ km, 200+ km, and 300+ km outputs with an explicit probability scale;
- overdevelopment risk and its main drivers;
- confidence and quality notes;
- one explicit data status: `mock`, `manual`, `baseline`, `real`, or `missing`.

Missing values are not zero. Mock or baseline values are not real observations.
Those distinctions must survive ingestion, storage, API serialization, and UI
rendering.

## Deferred decisions

- Exact external forecast and historical archive providers
- Source-specific ingestion permissions and rate limits
- Final launch coordinates, aliases, and catchment radii
- SQLite schema, migration, and ORM/query approach
- Alert delivery channel
- Deployment or cloud infrastructure

These should be decided in the ticket that has enough evidence to own the
trade-off, not guessed during earlier work.
