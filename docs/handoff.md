# Project Handoff

## Handoff metadata

| Field | Value |
| --- | --- |
| Last updated | 2026-07-17 |
| Current Git branch | `feature/T-002-local-server-skeleton` |
| Branch relationship | Deliberately stacked on unmerged `feature/t-001-repository-scaffold`; `main` was not changed |
| Current/recent task | `T-002 - Create local server skeleton` - status `Review` |
| Next intended task | `T-003 - Create initial dashboard route` - status `To Do` |
| Latest implementation commit | `75387d4 T-002 add mock forecast endpoint` |
| Expected working tree after handoff commit | Clean; verify before starting new work |

## Current outcome

T-002 is implemented as a real local API rather than a placeholder. It adds a
Node.js 24, Express 5, strict TypeScript server with documented watch and
compiled startup commands. Shared executable contracts, structured
observability, global errors, seven sites, and per-site mock forecast values
are in place for the Takt 1 dashboard tasks.

No database was added. SQLite remains the accepted MVP direction, but schema,
migrations, access tooling, and a real prediction adapter belong to later work.
The current API uses repository ports with in-memory/mock adapters.

## Implemented behavior

### HTTP surface

```text
GET /health
GET /api/v1/sites
GET /api/v1/forecasts?siteId=...&date=YYYY-MM-DD
```

- `/health` returns service identity, version, and an ISO timestamp.
- `/api/v1/sites` returns stable IDs and names for Sofia - Vitosha (Kominite),
  Zlatitsa, Sopot, Nevsha, Shumen, Pastrona, and Dobrich region.
- `/api/v1/forecasts` validates a slug site ID and a real ISO calendar date,
  rejects unknown sites with `404`, and returns deterministic per-site mock
  values with a request-time `generatedAt`.
- Forecast payloads include explicit `Pct`/`MslM` unit semantics, per-output
  status and confidence, forecast-level provenance, top drivers, and quality
  notes. The mock adapter never presents values as real forecasts.
- Errors use `application/problem+json`; unexpected exceptions are logged but
  not exposed. `X-Request-Id` correlates responses and structured logs.
- CORS allows GET/OPTIONS for the configured exact dashboard origin, with
  credentials disabled.

### Internal architecture

- Feature-oriented modules keep each feature's controller, service, repository
  port, and adapter together.
- `main.ts` is the manual dependency-injection composition root.
- `app.ts` creates Express without listening, enabling in-memory integration
  tests.
- `server.ts` owns real TCP startup, idempotent shutdown, and a bounded graceful
  close period.
- Pino/`pino-http` provide structured logs, request IDs, and credential-header
  redaction; no application `console.log` calls were introduced.
- Zod schemas in `@paragliding-forecasts/contracts` are the runtime payload
  source of truth and emit both ESM JavaScript and declarations.

Accepted T-002 choices are recorded as DEC-010 through DEC-013 in
[`decisions.md`](decisions.md).

## Commands

From the repository root:

```powershell
npm.cmd run dev:api
npm.cmd run start:api
npm.cmd run build
npm.cmd run typecheck
npm.cmd run lint
npm.cmd run format:check
npm.cmd test
npm.cmd run repo:check
```

The API reads the root `.env` when present and validates only `NODE_ENV`,
`LOG_LEVEL`, `API_HOST`, `API_PORT`, `CORS_ORIGIN`, and
`FORECAST_DATA_MODE=mock`. It has safe local defaults. `DATABASE_URL` and
`MODEL_ARTIFACT_DIR` are reserved and unused by T-002.

## Test strategy and validation

The selected levels are proportionate to this API ticket:

- contract tests for runtime schemas, ranges, dates, missing states, and XC
  probability ordering;
- unit tests for configuration, logging/redaction, request IDs, site service,
  and forecast mapping;
- in-memory HTTP integration tests for health, CORS, errors, request/response
  contracts, sites, forecasts, and validation;
- a real ephemeral-port server smoke test for listen/fetch/close behavior;
- manual probes of both documented process commands through the real
  composition root.

Component/browser E2E tests are not applicable to T-002. Browser smoke coverage
is owned by T-008 after the dashboard exists. Database component tests are
deferred with the database implementation.

Final verification on 2026-07-17:

- **Passed:** `npm.cmd ci` - lockfile-exact install, 273 packages audited, zero
  reported vulnerabilities.
- **Passed:** `npm.cmd ls --depth=0` - workspace and direct dependency tree;
  the API resolves `@types/node@24.13.3` for its Node.js 24 runtime contract.
- **Passed:** `npm.cmd run build`.
- **Passed:** `npm.cmd run typecheck`.
- **Passed:** `npm.cmd run lint`.
- **Passed:** `npm.cmd run format:check`.
- **Passed:** `npm.cmd test` - contracts: 1 file/6 tests; API: 9 files/42 tests.
- **Passed:** `npm.cmd run repo:check`.
- **Passed:** real `npm.cmd run dev:api` probe - health `ok`, 7 sites, Sopot
  forecast status `mock`, 100+ km value `65`.
- **Passed:** real `npm.cmd run start:api` probe - compiled service health `ok`.
- Both probe processes were stopped and their listening ports checked for
  cleanup.

Run `git diff --check` and a clean-tree/status check again after the handoff
commit; their final result cannot be recorded before that commit exists.

## Git checkpoints

The branch was created from T-001 without merging T-001 into `main`, as
explicitly requested. T-002 work was split into reviewable commits:

- `5d94ed2 T-002 add project context documentation`
- `4087b72 T-002 define shared API contracts`
- `43421bb T-002 add API server foundation`
- `0f475ea T-002 add site catalog endpoint`
- `75387d4 T-002 add mock forecast endpoint`
- final operation/decision/handoff documentation checkpoint (the commit that
  contains this file)

No branch was pushed and no pull request or merge was created in this session.

## Compatibility with the project brief

The internal mock `ForecastRecord` deliberately mirrors the draft
`predictions` fields: date/site, generation timestamp, cloudbase, probabilities
for 100/200/300+ km, overdevelopment risk, confidence, and top drivers. The
public contract adds the status/provenance/quality semantics required by the
brief and architecture.

Before persistence is implemented, its owner must define:

- whether stored probabilities use `0..1` or `0..100`;
- whether cloudbase is MSL or AGL;
- per-output missing/status/confidence representation;
- provenance and quality metadata;
- behavior when no prediction exists for a site/date.

The current internal mock record requires all outputs and its repository port
always returns a record. A real adapter will need to refine that boundary for
no-record and mixed-missing cases; the public contract already supports missing
metrics.

## Known follow-ups and boundaries

- The backlog has no explicit task for the persisted prediction schema and the
  SQLite forecast adapter that will replace T-002's mock repository. Assign an
  owner before wiring T-022-T-024 model outputs into the API.
- The project brief requires visibility of underlying forecast inputs and a
  high/medium/low signal label, but T-003-T-007 and T-025 do not clearly own
  both requirements. Add/clarify backlog ownership before claiming them done.
- T-009 still owns exact coordinates, aliases, and catchment radii. T-002
  therefore exposes only reviewed names/IDs, not guessed geographic data.
- The real composition-root startup is manually probed but not yet automated as
  a child-process test. The automated real-socket smoke covers server lifecycle
  through a test composition root.
- The earlier local `uv sync` cache/interpreter issue was not part of T-002 and
  was not retested. The committed ML lockfile is unchanged.
- `docs/tasks.md` still contains spreadsheet serial dates and a mis-encoded
  euro heading inherited from its source. T-002 changes only its own status.
- Source access, weather providers, browser tooling, alert channel, deployment,
  and repository license remain open in `decisions.md`.

## Quick start for the next Codex session

> Read root `AGENTS.md`, this handoff, T-003 in `tasks.md`, and only the relevant
> dashboard sections of `project-brief.md` and `architecture.md`. Inspect Git
> branch/status/log first. T-002 is stacked on unmerged T-001, so review/merge
> dependencies in order or explicitly agree another stacked branch; do not
> silently merge or rebase. For T-003, implement the initial forecast dashboard
> route and its real Vite run/build/test commands without absorbing T-004's site
> selector, T-005's date selector, T-006's forecast cards, or T-008's browser
> smoke test unless the user explicitly broadens scope.
