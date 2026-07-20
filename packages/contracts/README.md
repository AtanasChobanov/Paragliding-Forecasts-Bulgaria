# Shared contracts

## Status

Package boundary only. Contract code will be added with the first API and UI
payloads in T-002/T-003.

## Purpose

This TypeScript package is the source of truth for data crossing the HTTP
boundary between the API and web dashboard. It should contain:

- request and response types;
- runtime schemas when a validation library is selected;
- data-status and risk enums/unions;
- stable identifiers and units used in public payloads.

It should not contain React components, Express handlers, database entities,
model-training code, or environment-specific configuration.

## Contract rules

- Version breaking HTTP changes explicitly.
- Include units in field names where ambiguity is possible, for example
  `cloudbaseMslM` rather than `cloudbase`.
- Represent missing values deliberately; do not silently turn them into zero.
- Include provenance, generated time, confidence, and data status with forecast
  values.
- Keep Python integration language-neutral through JSON, SQLite records, or
  documented files rather than importing TypeScript into Python.

## Planned commands

```powershell
npm.cmd run build --workspace @paragliding-forecasts/contracts
npm.cmd run test --workspace @paragliding-forecasts/contracts
```

These become runnable when the first contract source and tooling are added.
