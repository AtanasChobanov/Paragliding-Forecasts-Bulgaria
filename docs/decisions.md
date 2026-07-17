# Project Decisions

## Purpose

This document records durable project decisions, their rationale, and their
consequences. Temporary progress and Git state belong in
[`handoff.md`](handoff.md); full system design belongs in
[`architecture.md`](architecture.md); requirements belong in
[`project-brief.md`](project-brief.md); implementation work and status belong in
[`tasks.md`](tasks.md).

## Decision index

| Decision ID | Title | Status | Date |
| --- | --- | --- | --- |
| DEC-001 | Use one repository with bounded subprojects | Accepted | 2026-07-15 |
| DEC-002 | Use npm workspaces for TypeScript and uv for Python | Accepted | 2026-07-15 |
| DEC-003 | Use TypeScript by default and limit Python to data/ML work | Accepted | 2026-07-15 |
| DEC-004 | Use React/Vite for web and Node.js/Express for the public API | Accepted | 2026-07-15 |
| DEC-005 | Share browser/API contracts in TypeScript and keep Python language-neutral | Accepted | 2026-07-15 |
| DEC-006 | Use a local-first MVP and SQLite storage direction | Accepted | 2026-07-15 |
| DEC-007 | Preserve explicit forecast status, provenance, units, and safety semantics | Accepted | 2026-07-15 |
| DEC-008 | Keep generated/local data out of Git with a controlled fixture exception | Accepted | 2026-07-15 |
| DEC-009 | Use short-lived ticket branches and pull-request review | Accepted | 2026-07-15 |
| DEC-010 | Organize the API by feature with manual dependency injection | Accepted | 2026-07-17 |
| DEC-011 | Use Zod as the runtime browser/API contract validator | Accepted | 2026-07-17 |
| DEC-012 | Use TSX and Vitest for the initial API development loop | Accepted | 2026-07-17 |
| DEC-013 | Use Pino logging and Problem Details HTTP errors | Accepted | 2026-07-17 |

## Individual decisions

### DEC-001 — Use one repository with bounded subprojects

**Status:** Accepted

**Date:** 2026-07-15

**Context:** The product needs coordinated web, API, shared-contract, and Python
data/ML work while remaining easy to set up and hand over as a small project.

**Decision:** Keep all components in one repository with explicit boundaries:
`apps/web`, `apps/api`, `packages/contracts`, and `services/ml`, plus shared
`docs`, `data`, and `scripts` areas.

**Rationale:** A single repository keeps cross-component changes, setup,
documentation, and review visible together while directory/package boundaries
prevent responsibilities from collapsing into one application.

**Alternatives considered:** Not formally recorded.

**Consequences:** Cross-component changes can use one branch and PR. Each real
subproject must keep its own responsibilities and local documentation clear;
future agents must not bypass the boundaries for convenience.

**Related files:** [`../README.md`](../README.md),
[`architecture.md`](architecture.md), [`../package.json`](../package.json).

### DEC-002 — Use npm workspaces for TypeScript and uv for Python

**Status:** Accepted

**Date:** 2026-07-15

**Context:** The repository contains both TypeScript and Python concerns and
needs reproducible, unambiguous dependency ownership.

**Decision:** Manage `apps/*` and `packages/*` with npm workspaces from the root,
and manage only `services/ml` with uv and Python 3.12. Commit both
`package-lock.json` and `services/ml/uv.lock`.

**Rationale:** npm matches the requested TypeScript-first stack and provides one
workspace lockfile; uv provides fast, reproducible Python environment management
without mixing ecosystems.

**Alternatives considered:** Yarn and pnpm for JavaScript, and requirements
files, Poetry, or manually managed virtual environments for Python are
explicitly excluded unless an approved migration is recorded.

**Consequences:** Dependencies must be installed into their owning workspace or
uv project. Root npm dependencies are reserved for truly shared tooling. Two
lockfiles are intentional and must remain current.

**Related files:** [`development.md`](development.md),
[`../package.json`](../package.json),
[`../services/ml/pyproject.toml`](../services/ml/pyproject.toml),
[`../services/ml/uv.lock`](../services/ml/uv.lock).

### DEC-003 — Use TypeScript by default and limit Python to data/ML work

**Status:** Accepted

**Date:** 2026-07-15

**Context:** The project prefers as much TypeScript as practical but requires
scientific tooling for weather data, atmospheric features, model training, and
validation.

**Decision:** Use strict TypeScript for product-facing web, API, and shared
contracts. Use Python only where its data/scientific ecosystem provides clear
value: ingestion, feature engineering, atmospheric data, experiments, training,
backtesting, and batch prediction.

**Rationale:** This maximizes one application language without rejecting the
Python ecosystem required for pandas/xarray/NetCDF/modeling workflows.

**Alternatives considered:** An all-TypeScript implementation was discussed as
a preference but not chosen for data/ML work; using Python for the public API
was suggested in the original brief but not selected for the current design.

**Consequences:** Business-facing HTTP and UI logic stays out of Python. Python
code must not absorb Express/API responsibilities without a new decision, and
TypeScript should not reimplement scientific tooling solely for language
uniformity.

**Related files:** [`../README.md`](../README.md),
[`architecture.md`](architecture.md),
[`../services/ml/README.md`](../services/ml/README.md).

### DEC-004 — Use React/Vite for web and Node.js/Express for the public API

**Status:** Accepted

**Date:** 2026-07-15

**Context:** The brief allowed multiple frontend and backend directions, while
the implementation needed a concrete TypeScript-first choice before scaffolding
Takt 1.

**Decision:** Build the dashboard with React, Vite, and TypeScript. Build the
browser-facing local API with Node.js, Express, and TypeScript. The Express API
is the single public backend boundary; the Python component begins as a batch
pipeline rather than another HTTP service.

**Rationale:** These choices support fast local dashboard work, maximize shared
TypeScript knowledge/contracts, and keep model/data responsibilities separate
from browser transport.

**Alternatives considered:** The project brief documented Python FastAPI or a
similar API and allowed Svelte or a lightweight server-rendered UI. Those remain
historical alternatives, not the selected implementation direction.

**Consequences:** `apps/web` owns presentation; `apps/api` owns HTTP and public
validation; `services/ml` writes documented language-neutral outputs. A Python
HTTP service requires measured runtime need and a new accepted decision.

**Related files:** [`architecture.md`](architecture.md),
[`../apps/web/README.md`](../apps/web/README.md),
[`../apps/api/README.md`](../apps/api/README.md),
[`project-brief.md`](project-brief.md).

### DEC-005 — Share browser/API contracts in TypeScript and keep Python language-neutral

**Status:** Accepted

**Date:** 2026-07-15

**Context:** The web and API need consistent request/response shapes, while
directly coupling Python to TypeScript implementation details would make the ML
pipeline fragile.

**Decision:** Use `@paragliding-forecasts/contracts` as the source of truth for
browser/API runtime schemas and inferred payload types. Exchange data with Python
through documented JSON, records, files, or storage schemas rather than imports
or Python-specific serialized objects.

**Rationale:** TypeScript contracts eliminate duplicate browser/API shapes, and
a language-neutral Python boundary preserves independent testing and evolution.

**Alternatives considered:** Not formally recorded.

**Consequences:** Database entities, Express handlers, React components, and
environment configuration do not belong in the contracts package. Payloads and
Python outputs must document units, identifiers, versions, provenance, and
missing-value behavior.

**Related files:** [`architecture.md`](architecture.md),
[`../packages/contracts/README.md`](../packages/contracts/README.md),
[`../services/ml/README.md`](../services/ml/README.md).

### DEC-006 — Use a local-first MVP and SQLite storage direction

**Status:** Accepted

**Date:** 2026-07-15

**Context:** Early Takts require an inspectable application that starts locally,
while actual data volume and concurrency are not yet known.

**Decision:** Optimize the MVP for local execution and use SQLite as the initial
storage direction. Keep persistence behind API repository interfaces and store
local runtime databases under ignored `data/local/`.

**Rationale:** SQLite minimizes infrastructure, is inspectable, and is adequate
until measured requirements justify a server database.

**Alternatives considered:** PostgreSQL is documented as a later option if data
volume or query/concurrency requirements justify it. No ORM/query library has
been selected.

**Consequences:** Do not introduce cloud/distributed infrastructure or
PostgreSQL speculatively. Do not leak SQLite details into HTTP handlers. Schema,
migrations, and access tooling remain work for the ticket that first needs
persistence.

**Related files:** [`architecture.md`](architecture.md),
[`../README.md`](../README.md), [`../data/README.md`](../data/README.md),
[`../.env.example`](../.env.example).

### DEC-007 — Preserve explicit forecast status, provenance, units, and safety semantics

**Status:** Accepted

**Date:** 2026-07-15

**Context:** Early demos may use mock/manual/baseline data, model confidence may
be limited, and paragliding decisions are safety-sensitive.

**Decision:** Every displayed forecast must preserve explicit units, source or
model version, generation time, confidence/quality information, and one data
status: `mock`, `manual`, `baseline`, `real`, or `missing`. Missing is not zero,
and the product must always be framed as decision support rather than a safety
guarantee.

**Rationale:** Users and reviewers must be able to distinguish evidence quality
and avoid treating incomplete or experimental values as observations or safe-
flying advice.

**Alternatives considered:** Not formally recorded.

**Consequences:** These fields and labels must survive ingestion, storage, API
serialization, UI rendering, screenshots, and demos. Tests must cover missing
and non-real states when the relevant behavior is implemented.

**Related files:** [`architecture.md`](architecture.md),
[`project-brief.md`](project-brief.md), [`../README.md`](../README.md),
[`../packages/contracts/README.md`](../packages/contracts/README.md).

### DEC-008 — Keep generated/local data out of Git with a controlled fixture exception

**Status:** Accepted

**Date:** 2026-07-15

**Context:** Weather, flight, model, and SQLite artifacts can be large,
restricted, generated, sensitive, or unsuitable for normal Git history, while
parsers still require reproducible test inputs.

**Decision:** Ignore content under `data/raw`, `external`, `interim`,
`processed`, `models`, and `local`. Permit only small, sanitized,
redistributable, documented fixtures under `data/samples`. Preserve source,
retrieval, licensing, attribution, and quality metadata when permitted.

**Rationale:** This protects repository size, source terms, pilot privacy, and
reproducibility without making automated parser tests depend on live services.

**Alternatives considered:** Committing full datasets was rejected by the data
policy. External artifact/data-versioning storage is deferred until actual
needs are known.

**Consequences:** Local data directories use tracked markers but their contents
stay ignored. Fixtures require review and provenance/synthetic-origin notes.
Large-file storage or data versioning requires a future decision.

**Related files:** [`../data/README.md`](../data/README.md),
[`../data/.gitignore`](../data/.gitignore),
[`../data/samples/README.md`](../data/samples/README.md),
[`project-brief.md`](project-brief.md).

### DEC-009 — Use short-lived ticket branches and pull-request review

**Status:** Accepted

**Date:** 2026-07-15

**Context:** Takt work must remain reviewable and tied to backlog items without
adding unnecessary long-lived integration branches to a small local-first
project.

**Decision:** Start short-lived `feature/T-...` or `fix/T-...` branches from an
up-to-date `main`, keep each branch scoped to one ticket, use imperative
ticket-prefixed commits, and merge through pull-request review after acceptance
criteria and limitations are visible. Developers move their tickets through
`To Do`, `In Progress`, and `Review` as work advances; `Done` requires the
project's Definition of Done and accepted integration.

**Rationale:** This keeps `main` reproducible, PR diffs focused, and progress
visible without permanent branch drift.

**Alternatives considered:** A permanent `dev`/GitFlow branch was considered but
rejected for the current scale because there is no separate staging/release
train. Stacked feature branches may be used deliberately for dependent work but
are not the default.

**Consequences:** Later work normally waits for or rebases onto the merged
dependency. PRs reference tickets, and task status must reflect actual review
and validation rather than coding completion alone.

**Related files:** [`../CONTRIBUTING.md`](../CONTRIBUTING.md),
[`development.md`](development.md), [`tasks.md`](tasks.md).

### DEC-010 — Organize the API by feature with manual dependency injection

**Status:** Accepted

**Date:** 2026-07-17

**Context:** The API needs clear controller, application/service, and storage
boundaries, but T-002 has only three small HTTP features and no database or
complex object lifetimes.

**Decision:** Group HTTP behavior under feature modules and keep cross-cutting
configuration, HTTP middleware, and observability separate. Each data-backed
feature defines a repository port; `main.ts` manually composes concrete
adapters and services. Keep `app.ts` free of process startup and socket binding.

**Rationale:** Feature cohesion avoids a growing set of repository-wide layer
folders while repository ports preserve testability and future SQLite adapter
replacement. Manual composition provides dependency injection without adding
a container that the current application does not need.

**Alternatives considered:** A repository-wide layered structure and a DI
container were considered. Both add navigation or abstraction cost before the
project has enough features, lifetimes, or bindings to justify them.

**Consequences:** Controllers do not query storage directly. A DI container may
be reconsidered only when concrete composition complexity appears. The mock
adapters are replaceable and do not imply a database implementation.

**Related files:** [`architecture.md`](architecture.md),
[`../apps/api/README.md`](../apps/api/README.md),
[`../apps/api/src/main.ts`](../apps/api/src/main.ts).

### DEC-011 — Use Zod as the runtime browser/API contract validator

**Status:** Accepted

**Date:** 2026-07-17

**Context:** TypeScript types disappear at runtime, while both request inputs
and browser-facing payloads must preserve strict units, missing states,
provenance, and quality semantics.

**Decision:** Define strict Zod schemas in `@paragliding-forecasts/contracts`
and infer their TypeScript types. Use them to validate API requests and outgoing
payloads. Use Zod independently at API startup to validate only environment
variables the API currently consumes.

**Rationale:** One executable contract prevents static interfaces and runtime
validation from drifting and gives the future web workspace the same payload
semantics as the API.

**Alternatives considered:** Hand-written guards and type-only interfaces were
rejected because they duplicate logic or provide no runtime guarantee. Other
schema libraries were viable but offered no project-specific advantage.

**Consequences:** Contract changes require schema tests and compatibility
review. Database schemas remain a separate language-neutral boundary and must
not import TypeScript implementation details.

**Related files:** [`../packages/contracts/README.md`](../packages/contracts/README.md),
[`../packages/contracts/src/index.ts`](../packages/contracts/src/index.ts),
[`../apps/api/src/config/env.ts`](../apps/api/src/config/env.ts).

### DEC-012 — Use TSX and Vitest for the initial API development loop

**Status:** Accepted

**Date:** 2026-07-17

**Context:** T-002 needs a real TypeScript watch command, production-oriented
compiled output, and fast automated coverage at unit, HTTP integration, and
real-socket levels.

**Decision:** Use TSX for local TypeScript watch execution, `tsc` with NodeNext
ESM for build/type checking, Vitest as the shared test runner, and Supertest for
in-memory Express integration tests. Use shared ESLint and Prettier tooling at
the npm workspace root.

**Rationale:** This provides a small, Node.js 24-compatible toolchain with
honest root commands and no test-only server architecture.

**Alternatives considered:** Node's built-in test runner was viable but would
require more local test ergonomics and setup for the same current coverage.
Running TypeScript directly in production was rejected in favor of verifying
compiled output.

**Consequences:** Root scripts must propagate child failures and contracts must
build before the API consumes them. Future web tooling may reuse the shared
quality tools but owns its own runtime/build dependencies.

**Related files:** [`development.md`](development.md),
[`../package.json`](../package.json),
[`../apps/api/package.json`](../apps/api/package.json).

### DEC-013 — Use Pino logging and Problem Details HTTP errors

**Status:** Accepted

**Date:** 2026-07-17

**Context:** The local API needs request correlation and useful diagnostics
without `console.log`, secret leakage, ad hoc status bodies, or exposing
unexpected exceptions.

**Decision:** Use Pino and `pino-http` for structured application/request logs,
redact credential-bearing headers, and correlate logs with `X-Request-Id`.
Return globally handled `application/problem+json` errors with stable project
codes and safe details.

**Rationale:** Structured logs remain machine-readable outside development,
while one documented error shape gives the future dashboard reliable behavior
for validation, not-found, and internal failures.

**Alternatives considered:** Console logging and route-local error bodies were
rejected because they drift and are difficult to query or sanitize.

**Consequences:** New routes use the shared error path and must not serialize
raw exceptions. Sensitive logging fields require redaction tests when added.

**Related files:** [`../apps/api/README.md`](../apps/api/README.md),
[`../apps/api/src/observability/logger.ts`](../apps/api/src/observability/logger.ts),
[`../packages/contracts/src/problem-details.ts`](../packages/contracts/src/problem-details.ts).

## Open decisions

| Question | Options / constraints | Resolve by |
| --- | --- | --- |
| Which SQLite access layer and migration approach should be used? | Direct driver, query builder, or ORM are possible; keep persistence behind repositories and do not add storage solely for a health endpoint. | The first persistence/schema ticket, expected by T-012/T-018. |
| Which task owns the persisted prediction schema and SQLite forecast adapter? | The backlog has flight and weather schema tasks but no explicit owner for storing T-022-T-024 outputs and replacing the T-002 mock adapter. Public units/status/provenance must be mapped deliberately. | Backlog planning before real predictions are connected to the API. |
| Which task owns the underlying forecast-input panel and high/medium/low signal semantics? | Both appear in the project brief, but T-003-T-007 cover the initial screen/selectors/cards/status and T-025 covers confidence/top drivers only. | Backlog planning before claiming the full dashboard requirement. |
| What are the final coordinates, aliases, and catchment radii for each site? | Pastrona and the Dobrich regional model need particular confirmation. | T-009. |
| What access methods, permissions, attribution, caching, and rate limits apply to flight sources? | XCContest and SkyNomad must be researched without assuming scraping permission. | T-010 and T-011. |
| Which historical forecast/archive or reanalysis sources will be used? | Exact archived forecasts are preferred; reanalysis is the documented fallback. | T-016, with units refined in T-017. |
| Which browser test tool should be adopted? | Must support the local dashboard smoke test and avoid unneeded test infrastructure before the UI exists. | T-008. |
| Which first alert channel should be implemented? | Dashboard watchlist, email, Telegram, or another agreed channel; alerts require at least one-day lead time and deduplication. | T-027/T-028. |
| What deployment/distribution model is required beyond local development? | The MVP is local-first; cloud/distributed infrastructure needs a demonstrated requirement. | No task assigned; decide when deployment becomes an accepted scope item. |
| What license should the repository use? | No open-source license is currently selected. | Repository owner decision; no task assigned. |
