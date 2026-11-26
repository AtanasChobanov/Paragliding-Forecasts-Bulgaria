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
chance and the 200+ km chance is not below the 300+ km chance. Detail
explanations have five metric groups, each with zero through three
ranked published drivers. An available metric may have no distinct driver.

The summaries query converts one CSV query value into one through seven unique
site slugs. Its response contains one ID-ordered `available` or `missing` item
per requested site. Available summaries include issue metadata, per-metric
confidence and limitations, and a cloudbase union with estimated and
conditional heights in metres MSL. The days response contains five
`Europe/Sofia` dates from `todayDate - 2` through `todayDate + 2`, with
publication availability independent of the 100+ km metric. The detail response
reuses the summaries' outputs and metadata schemas.

`dataStatusSchema` is the canonical five-state schema: `mock`, `manual`,
`baseline`, `real`, or `missing`. `availableDataStatusSchema` is derived from it
with `dataStatusSchema.exclude(["missing"])`; it is not a second independent
status definition. Numeric and OD metrics use a discriminated union. Available metrics carry
a value and confidence. Missing metrics carry null value and confidence
fields with an explicit reason.

## Published detail shape (T-025)

`ForecastResponse` contains identity/date, `generatedAt`, `metadata`, `outputs`,
`forecastInputs`, `explanations` and `cloudbaseHours`. The owner-approved
[DEC-073](../../docs/decisions.md#dec-073---read-published-details-and-exact-weather-evidence-in-one-viewport)
replaces the provisional mock detail shape in the existing local `/api/v1`
endpoint; API and browser upgrade together.

`ForecastInputs` / `ForecastDetailInputs` now describe the fixed 67-row XC
inventory and eleven hourly OD/cloudbase contexts. Rows preserve canonical
units, statistics, quality, exact provenance, optional layer/interval bounds
and explicit missing reasons. Policy-parity tests verify the static inventory;
the runtime package does not read Python policy files.

Structured drivers preserve kind, code, message, rank, conditional XC stage,
direction/logit contribution, OD score points or pooled conversion counts where
applicable. Their ordered inputs have either the resolved exact field or an
unavailable explanation. Each metric's confidence and limitations match its
output. Zero drivers is valid; no synthetic explanation is required.

Hourly cloudbase validates complete height triples for cumulus, optional
conditional triples for indeterminate, and null heights for other regimes.
Model AGL is nonnegative; site AGL is signed. Missing hours have null confidence.
A conditional level outside the profile has no usable height. The response
checks exactly eleven ordered 10:00–20:00 Sofia hours on the target date,
including DST transitions, and maxima from those same hours. Available
estimated heights take priority even if a conditional hour is higher.

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
