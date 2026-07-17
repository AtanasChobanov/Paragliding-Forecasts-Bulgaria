# Shared contracts

## Status

T-002 implements the first browser/API contracts as strict Zod runtime schemas
with TypeScript types inferred from those schemas. The package emits ESM
JavaScript and declarations so later workspaces consume one executable source
of truth rather than copying interfaces.

## Owned contracts

- `HealthResponse`
- site IDs, site records, and `SitesResponse`
- forecast query/date validation and `ForecastResponse`
- available-versus-missing forecast metrics
- data status, confidence, provenance, and units
- RFC-style `ProblemDetails` error payloads and validation issues

The forecast schema validates real calendar dates, percentage ranges, ISO
timestamps, and the invariant that the 100+ km chance is not below the 200+ km
chance and the 200+ km chance is not below the 300+ km chance.

## Contract rules

- Treat the runtime schema as the payload source of truth and infer TypeScript
  types from it.
- Make breaking HTTP changes through an explicit API-version decision.
- Include units in field names and metric metadata where ambiguity is possible.
- Represent missing values deliberately; never silently convert them to zero.
- Preserve provenance, generation time, confidence, quality information, and
  one of `mock`, `manual`, `baseline`, `real`, or `missing`.
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
npm.cmd run test:watch --workspace @paragliding-forecasts/contracts
```

The API package builds contracts before its own build, type-check, tests, or
watch startup. The root build and test commands also preserve this ordering.
