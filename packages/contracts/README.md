# Shared contracts

## Status

T-002 established the strict Zod browser/API boundary. T-003-T-005 extend it
with map coordinates, batched dashboard summaries, and the fixed five-day
selected-site preview. The package emits ESM JavaScript and declarations for the React workspace
and API.

## Owned contracts

- `HealthResponse`
- numeric site IDs, public site slugs, map coordinates, site records, and
  `SitesResponse`
- forecast query/date validation and `ForecastResponse`
- `ForecastSummariesQuery` and `ForecastSummariesResponse`
- `ForecastDaysQuery` and `ForecastDaysResponse`
- available-versus-missing forecast metrics
- data status, confidence, provenance, and units
- RFC-style `ProblemDetails` error payloads and validation issues

The forecast schema validates real calendar dates, percentage ranges, ISO
timestamps, and the invariant that the 100+ km chance is not below the 200+ km
chance and the 200+ km chance is not below the 300+ km chance. A forecast must
also expose at least one top driver; the richer explainability shape remains
owned by the later model/UI ticket.

The summaries query converts one CSV query value into one through seven unique
site slugs. Its response contains one ID-ordered `available` or `missing` item
per requested site. Available summaries include issue metadata, per-metric
confidence and limitations, and a cloudbase union with estimated and
conditional heights in metres MSL. The days response contains five
`Europe/Sofia` dates from `todayDate - 2` through `todayDate + 2`, with
publication availability independent of the 100+ km metric. The detail
response retains its own outputs schema.

`dataStatusSchema` is the canonical five-state schema: `mock`, `manual`,
`baseline`, `real`, or `missing`. `availableDataStatusSchema` is derived from it
with `dataStatusSchema.exclude(["missing"])`; it is not a second independent
status definition. Numeric and OD metrics use a discriminated union. Available metrics carry
a value and confidence. Missing metrics carry null value and confidence
fields with an explicit reason.

## Contract rules

- Treat the runtime schema as the payload source of truth and infer TypeScript
  types from it.
- Make breaking HTTP changes through an explicit API-version decision.
- Include units in field names and metric metadata where ambiguity is possible.
- Represent missing values deliberately; never silently convert them to zero.
- Keep dashboard summary order deterministic by ascending numeric site ID.
- Keep the date preview fixed at five centered calendar slots; do not add
  pagination fields to this contract.
- Preserve provenance, generation time, confidence, top drivers, and one of
  `mock`, `manual`, `baseline`, `real`, or `missing`.
- Keep Python integration language-neutral through JSON, SQLite records, or
  documented files; Python must not import this TypeScript package.

This package must not contain React components, Express handlers, database
entities, model-training code, or environment-specific configuration.

## Commands

Run from the repository root:

```powershell
npm.cmd run build --workspace @paragliding-forecasts/contracts
npm.cmd run typecheck --workspace @paragliding-forecasts/contracts
npm.cmd run test --workspace @paragliding-forecasts/contracts
npm.cmd run test:coverage --workspace @paragliding-forecasts/contracts
npm.cmd run test:watch --workspace @paragliding-forecasts/contracts
```

The API package builds contracts before its own build, type-check, tests, or
watch startup. The root build and test commands also preserve this ordering.
V8 coverage includes every contract source file and enforces minimum global
thresholds of 95% statements/lines, 90% branches, and 100% functions.
