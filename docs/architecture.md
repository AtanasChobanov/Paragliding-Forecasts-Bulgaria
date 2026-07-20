# Architecture

## Goals

- Deliver a useful local dashboard early, even while forecast values are mock
  or baseline data.
- Keep product-facing code in TypeScript where practical.
- Isolate Python to data and ML workloads that benefit from its ecosystem.
- Preserve provenance, units, confidence, and data status end to end.
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

`packages/contracts` owns browser-facing request/response shapes. It does not
force Python to consume TypeScript. The Python/Node boundary stays
language-neutral through documented storage schemas or serialized records.

## Web dashboard

The dashboard owns presentation and user interaction only. It selects a site
and date, calls the API, and renders forecast values with their status,
confidence, units, provenance, loading state, and error state.

## Express API

The API is the browser-facing boundary. It validates requests, reads forecast
and prediction records, and maps them to stable public contracts. It must keep
transport concerns separate from repository/storage logic so tests can run
without binding ports or depending on live data sources.

## Python data and ML pipeline

The initial Python component is a batch workflow, not a public microservice. It
collects permitted source data, generates features, trains transparent
baselines, backtests results, and writes versioned predictions. An HTTP service
should be introduced only if a measured runtime requirement justifies it.

## Storage

SQLite is the MVP default because it is local, inspectable, and easy to back up.
Repository interfaces in the API should prevent SQLite details from leaking
into HTTP handlers. PostgreSQL or dedicated artifact storage can be evaluated
later using observed data size and concurrency needs.

## Forecast record principles

Every displayed forecast must preserve:

- site and forecast date;
- generation timestamp and source/model version;
- cloudbase with explicit MSL/AGL unit semantics;
- 100+ km, 200+ km, and 300+ km outputs;
- overdevelopment risk and its main drivers;
- confidence or quality notes;
- one explicit data status: mock, manual, baseline, real, or missing.

Missing values are not zero. Mock or baseline values are not real observations.
Those distinctions must survive ingestion, storage, API serialization, and UI
rendering.

## Deferred decisions

- Exact external forecast and historical archive providers
- Source-specific ingestion permissions and rate limits
- Final launch coordinates, aliases, and catchment radii
- Runtime schema-validation library for TypeScript contracts
- ORM/query layer for SQLite
- Alert delivery channel
- Deployment or cloud infrastructure

These should be decided in the ticket that has enough evidence to own the
trade-off, not guessed during repository scaffolding.
