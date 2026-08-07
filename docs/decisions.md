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
| DEC-014 | Separate internal numeric site IDs from public slugs | Accepted | 2026-07-20 |
| DEC-015 | Add dashboard-specific forecast read models | Accepted | 2026-07-21 |
| DEC-016 | Expose provisional map coordinates and confirm Pastrina spelling | Accepted | 2026-07-21 |
| DEC-017 | Use a focused React dashboard stack with Leaflet | Accepted | 2026-07-22 |
| DEC-018 | Add a provisional detailed forecast-input read model | Accepted | 2026-07-24 |
| DEC-019 | Use Playwright Chromium for local browser smoke coverage | Accepted | 2026-07-25 |
| DEC-020 | Use a phased Drizzle-owned SQLite foundation for flight data | Accepted | 2026-07-30 |
| DEC-021 | Finalize the normalized T-012 flight foundation schema | Accepted | 2026-08-02 |
| DEC-022 | Collect XCContest list pages through the permitted rendered UI boundary | Superseded | 2026-08-04 |
| DEC-023 | Partition saturated XCContest first-page views through visible filters | Accepted | 2026-08-06 |
| DEC-024 | Derive XCContest country scope from all canonical sites | Accepted | 2026-08-06 |
| DEC-025 | Use durable artifacts between versioned XCContest ingestion stages | Accepted | 2026-08-07 |

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
model version, generation time, confidence and known limitations, and one data
status: `mock`, `manual`, `baseline`, `real`, or `missing`. Missing is not zero,
and the product must always be framed as decision support rather than a safety
guarantee. This does not require a dedicated `qualityNotes` field in every
forecast payload.

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
provenance, and explicit data-status semantics.

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
not import TypeScript implementation details. `dataStatusSchema` is the
canonical five-state definition; the available-value schema is derived by
excluding `missing` and is used in a discriminated union whose missing branch
requires null value/confidence and an explicit reason.

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
ESM for build/type checking, Vitest as the shared test runner, Supertest for
in-memory Express integration tests, and Vitest's V8 provider for source-wide
coverage with enforced workspace thresholds. Use shared ESLint and Prettier
tooling at the npm workspace root.

**Rationale:** This provides a small, Node.js 24-compatible toolchain with
honest root commands and no test-only server architecture.

**Alternatives considered:** Node's built-in test runner was viable but would
require more local test ergonomics and setup for the same current coverage.
Running TypeScript directly in production was rejected in favor of verifying
compiled output.

**Consequences:** Root scripts must propagate child failures and contracts must
build exactly once before an API build consumes them. Coverage configuration
must include unimported source files and fail below the recorded thresholds.
Future web tooling may reuse the shared quality tools but owns its own
runtime/build dependencies.

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
raw exceptions. Stable problem type/status/title metadata is centralized by
problem code and validated as a one-to-one contract. Sensitive logging fields
require tests through the real `pino-http` serializer when added.

**Related files:** [`../apps/api/README.md`](../apps/api/README.md),
[`../apps/api/src/observability/logger.ts`](../apps/api/src/observability/logger.ts),
[`../packages/contracts/src/problem-details.ts`](../packages/contracts/src/problem-details.ts).

### DEC-014 — Separate internal numeric site IDs from public slugs

**Status:** Accepted

**Date:** 2026-07-20

**Context:** The initial T-002 contract used lowercase location slugs as
`siteId`. The project brief refers to `site_id` relationships across weather,
predictions, and alerts, while site names, aliases, launch clusters, and region
definitions can evolve. The browser also needs a readable and stable lookup
value before persistence is implemented.

**Decision:** Represent site identity with a positive safe-integer `id` and a
separate unique lowercase `slug`. Return both from the sites API, select
forecasts with the `siteSlug` query parameter, and pass the numeric ID through
the forecast repository boundary. Keep the current deterministic IDs in the
in-memory catalog; the future persistence owner must define a `sites` table and
preserve or deliberately migrate that seed mapping.

**Rationale:** Numeric IDs are suitable relationship keys and do not change
when a public slug is renamed. Slugs remain readable API lookup keys and avoid
exposing database navigation as the user-facing selector contract.

**Alternatives considered:** Keeping the slug as both natural primary key and
public identifier is valid for a small immutable catalog, but it couples every
future foreign key to naming changes. Looking forecasts up by numeric ID alone
was rejected because it gives the browser an opaque location selector and
unnecessarily exposes persistence identity at the HTTP boundary.

**Consequences:** T-003 and later frontend work consume `site.slug` for lookup
and may retain `site.id` for identity. T-009 may refine names, aliases, and
region definitions without rewriting prediction relationships. T-002 still
does not select a SQLite access layer or implement schema/migrations.

**Related files:** [`architecture.md`](architecture.md),
[`../packages/contracts/src/sites.ts`](../packages/contracts/src/sites.ts),
[`../packages/contracts/src/forecast.ts`](../packages/contracts/src/forecast.ts),
[`../apps/api/src/modules/sites/in-memory-site.repository.ts`](../apps/api/src/modules/sites/in-memory-site.repository.ts).

### DEC-015 — Add dashboard-specific forecast read models

**Status:** Accepted

**Date:** 2026-07-21

**Context:** The approved dashboard needs one selected-location overview,
several default location cards, and five compact date cards. Fetching the
detailed forecast once per component would duplicate data and couple UI layout
to storage queries. The date strip no longer needs arrows or historical
pagination.

**Decision:** Keep the detailed `GET /api/v1/forecasts` lookup for the later
location/date page. Add `GET /api/v1/forecasts/summaries` with one date and one
CSV list of one through seven unique site slugs, returning one item per site in
numeric-ID order. Add `GET /api/v1/forecasts/days` with only a site slug,
returning exactly the five Europe/Sofia calendar dates centered on today and
only the 100+ km metric per slot. Do not add cursor, offset, limit, anchor, or
direction fields to the dashboard date-preview contract.

The React dashboard will own these requests at route level: fetch sites once,
deduplicate the selected/default summary slugs into one request, index results
by slug, and make one separate days request for the selected site. Cards receive
data as props and do not issue their own requests.

**Rationale:** These shapes match the information density and interactions of
the approved dashboard while keeping network work bounded and storage details
out of React components. Fixed calendar slots make missing dates visible
without pagination state.

**Alternatives considered:** One detailed request per card was rejected because
it over-fetches top drivers and repeats HTTP work. A monolithic dashboard
endpoint was rejected because site metadata, multi-site summaries, and the
selected-site date strip have different cache and refresh triggers. Cursor- or
offset-based date pagination was removed after client review.

**Consequences:** Summary input is strict and duplicate-free; output order is
ID-based rather than request-based. Missing detailed forecasts return `404`,
missing summary records remain `200` items, and missing day records remain
`200` metrics in their fixed slots. The mock snapshot's startup-date limitation
must stay documented until persistence replaces it.

**Related files:** [`architecture.md`](architecture.md),
[`../apps/api/README.md`](../apps/api/README.md),
[`../packages/contracts/src/dashboard-forecasts.ts`](../packages/contracts/src/dashboard-forecasts.ts).

### DEC-016 — Expose provisional map coordinates and confirm Pastrina spelling

**Status:** Accepted

**Date:** 2026-07-21

**Context:** T-004 needs all seven locations selectable from the dashboard map
before T-009 performs field-grade coordinate and catchment validation. The
earlier `Pastrona` label was confirmed to be misspelled.

**Decision:** Add latitude and longitude directly to each site response, retain
the existing numeric IDs, sort the catalog by `id ASC`, and do not add a
`dashboardOrder` field. Rename site ID 6 to `Pastrina` with slug `pastrina`.
Use the agreed provisional coordinates only for initial map placement.

**Rationale:** Coordinates are domain metadata required by any map client,
while a dashboard-specific ordering field would encode current presentation in
the site model. Keeping ID 6 avoids unnecessary identity churn during the
spelling correction.

**Alternatives considered:** Hard-coding map coordinates in React and adding a
separate dashboard order were rejected because both duplicate or leak domain
metadata into presentation. Waiting for T-009 would block the initial selector.

**Consequences:** The site contract now requires bounded geographic
coordinates. T-009 must still verify exact points, aliases, and radii before
ingestion or geographic matching treats them as authoritative.

**Related files:** [`project-brief.md`](project-brief.md),
[`../packages/contracts/src/sites.ts`](../packages/contracts/src/sites.ts),
[`../apps/api/src/modules/sites/in-memory-site.repository.ts`](../apps/api/src/modules/sites/in-memory-site.repository.ts).

### DEC-017 — Use a focused React dashboard stack with Leaflet

**Status:** Accepted

**Date:** 2026-07-22

**Context:** T-003-T-005 need a shareable selected site/date, validated API
data, a bespoke responsive visual system, and a real map with zoom, pan,
labeled pins, and location selection. The dashboard has only two canonical
selection values and three bounded server reads, so a general-purpose client
state store or component framework would add more concepts than the current
scope requires.

**Decision:** Keep `site` and `date` in React Router search parameters and use
TanStack Query for server state. Use native `fetch` and validate every
successful response with the Zod schemas exported by
`@paragliding-forecasts/contracts`. Keep transient UI state local rather than
creating a Redux, Zustand, or custom global Context store.

Style the application with SCSS Modules, Sass `@use`, and one CSS-custom-
property theme. Use the self-hosted Inter family throughout the MVP. Build the
interactive location selector with Leaflet through React Leaflet. Use
OpenStreetMap Standard raster tiles only for the low-volume local MVP, keep the
tile source and attribution centralized/configurable, follow the tile usage
policy, and provide an accessible HTML location selector and tile-failure
fallback.

**Rationale:** This separates shareable browser navigation, cached server data,
and transient presentation state without duplicating sources of truth. SCSS
Modules support the supplied custom design while retaining component scope and
reusable theme tokens. Leaflet provides the required map interactions and
selectable named markers without Google Maps account, billing, or provider
lock-in.

**Alternatives considered:** Raw `useEffect`/`useState` fetching was not chosen
because it would require custom cancellation, stale-response, cache, retry, and
error logic. Redux, Zustand, and a custom dashboard Context were not chosen
because the URL and TanStack Query already own the relevant state. Tailwind and
Bootstrap were not chosen because the supplied visual language is small and
bespoke; both would add a second styling vocabulary, and Bootstrap would also
require substantial visual overrides. Google Maps was not chosen because it
adds billing/account and vendor coupling. A hand-built SVG map was rejected
because it would not provide a real navigable basemap. MapLibre remains a
future option if vector maps become a concrete requirement.

**Consequences:** Web dependencies belong to `apps/web` and must be version-
locked through the root npm lockfile. Route-level query ownership follows
DEC-015; presentational cards do not fetch. URL normalization must distinguish
history `replace` from user-navigation `push`. The browser must never duplicate
shared response schemas. Public OSM tiles require network access, visible
attribution, policy compliance, and have no availability guarantee. T-008 owns
the browser smoke implementation, while T-009 still owns authoritative site
coordinates.

**Related files:** [`handoff.md`](handoff.md),
[`../apps/web/README.md`](../apps/web/README.md),
[`architecture.md`](architecture.md), [`../README.md`](../README.md).

### DEC-018 — Add a provisional detailed forecast-input read model

**Status:** Accepted

**Date:** 2026-07-24

**Context:** T-006/T-007 need to expose the weather and atmospheric context
behind a detailed mock prediction before the persistence, ingestion, and final
weather-feature work is implemented. The detailed page also needs a reliable
way to distinguish mock, manually loaded, baseline, real, and missing inputs.

**Decision:** Extend only the single-site/date `ForecastResponse` with strict
`forecastInputs`. Each input is an available-or-missing value with explicit
status and units in its field name; the object additionally carries source-run
time and provenance. It covers the project brief's temperature, boundary-layer,
wind, humidity, instability, cloud, precipitation, pressure, and convergence
groups. The existing detailed route owns this request; dashboard summaries and
five-day previews remain unchanged. `topDrivers` remains an ordered string
array, and previous-run comparison values are deliberately not added to the API.

**Rationale:** The screen can show inspectable mock evidence now without
inventing storage, model-run history, driver categories, or a second browser
endpoint. Field-level missing states prevent unavailable input from becoming a
plausible numeric zero.

**Consequences:** The contract is a browser read model, not a SQLite schema or
the final weather-feature vocabulary. T-017 remains responsible for final
feature definitions/units and a later persistence owner must map those values
explicitly. The detail UI must label synthetic values and keep its five-output
`Unchanged` comparison as a static placeholder until real repeated model runs
exist.

**Related files:** [`../packages/contracts/src/forecast.ts`](../packages/contracts/src/forecast.ts),
[`../apps/api/src/modules/forecasts/mock-forecast.repository.ts`](../apps/api/src/modules/forecasts/mock-forecast.repository.ts),
[`../apps/web/src/routes/forecast-details/forecast-details-route.tsx`](../apps/web/src/routes/forecast-details/forecast-details-route.tsx).

### DEC-019 — Use Playwright Chromium for local browser smoke coverage

**Status:** Accepted

**Date:** 2026-07-25

**Context:** Vitest, React Testing Library, and MSW validate the web client's
logic and rendered semantics, but cannot prove that the local API, Vite bundle,
React application, browser routing, and HTTP requests work together in a real
browser. T-008 requires a small Takt 1 browser proof for both the dashboard and
the detailed forecast route.

**Decision:** Add `@playwright/test` as an `apps/web` development dependency
and run one Chromium project. Playwright starts the compiled local API and Vite
separately on the normal local ports, waits for both to be ready, and runs two
headless smoke scenarios: dashboard forecast cards, then dashboard-to-detail
navigation and return. Provide separate `test:browser`, `test:browser:headed`,
and `test:browser:ui` commands. Failure-only trace and screenshot artifacts are
ignored; visual baselines, cross-browser coverage, map interaction, and pixel
comparison are out of scope. Block OSM tile requests so the forecast smoke does
not depend on the public tile service.

**Rationale:** Playwright provides real Chromium execution, accessible
role/label locators, automatic waiting, and lifecycle-managed local servers
without a second test framework or a test-only application architecture. A
focused smoke suite catches integration failures that jsdom cannot, while
keeping the local Takt 1 gate small and deterministic.

**Alternatives considered:** Cypress and Selenium would introduce a larger
parallel test stack. Vitest browser mode would reuse the runner but does not
offer the same focused local multi-process E2E workflow for this scope.

**Consequences:** Contributors install the version-matched Chromium binary with
`npm run test:browser:install` before running browser coverage. The regular
`npm test` and V8 coverage commands remain separate from this browser suite.
Ports `3000` and `5173` must be free. Browser smoke validation passed on
2026-07-25 (`2 passed`) and moved T-008 from `In Progress` to `Review`; it
remains a separate check from the regular unit, integration, and component test
commands.

**Related files:** [`../apps/web/playwright.config.ts`](../apps/web/playwright.config.ts),
[`../apps/web/test/browser/dashboard.smoke.spec.ts`](../apps/web/test/browser/dashboard.smoke.spec.ts),
[`../apps/web/README.md`](../apps/web/README.md).

### DEC-020 - Use a phased Drizzle-owned SQLite foundation for flight data

**Status:** Accepted

**Date:** 2026-07-30

**Context:** T-012 is the first persistence task. The product is TypeScript-
first at its browser/API boundary, while Python owns permitted ingestion and ML
batch work. The next task must establish a durable SQLite schema without
prematurely freezing weather, prediction, model, or alert structures that have
their own later discovery/design tasks.

**Decision:** Use Drizzle ORM and Drizzle Kit in a new
`packages/database` TypeScript workspace as the sole owner of SQLite schema
DDL and migration history. T-012 creates only the Takt 2 persistence
foundation: `sites`, source-specific site aliases/takeoff mappings,
`ingestion_runs`, and canonical `flight_records`. The exact physical field
design remains a T-012 deliverable and must be documented and tested before the
task is completed.

Do not create weather features, soundings, processed feature sets, model runs,
predictions, alerts, or a generic future-data schema in T-012. Their owning
tasks add migrations later. The selected flight source for Takt 2 is XCContest,
but the storage schema remains source-neutral through fields such as source
system, source record identity, canonical URL, raw takeoff evidence, and
permission/provenance metadata.

Python ingestion/ML code may write to the migrated SQLite file through a
non-migrating batch persistence adapter after validation. It must not run
Alembic or any other migration tool, declare a competing schema, or become a
public HTTP service. The API reads through feature repository adapters and
continues to own browser-facing contracts.

**Rationale:** This keeps one migration history and one physical schema while
letting Python use the data/scientific ecosystem where it has clear value. A
phased schema keeps the T-012 reviewable, enables T-013 to persist a validated
flight sample, and avoids inventing final weather/model fields before T-017,
T-018, and the modeling tasks define them.

**Alternatives considered:** Creating every table from the initial project
brief now was rejected because it would make unvalidated weather, prediction,
and alert assumptions durable too early. A separate Python ORM/migration system
was rejected because two DDL authorities could drift. Sending every Python
batch output through a TypeScript importer was rejected for the MVP because it
adds an unnecessary process boundary; validated Python batch writes can use the
same SQLite schema directly.

**Consequences:** A T-013 collector/importer must preserve an immutable raw
artifact, normalize and validate it, resolve a canonical project site, decide
duplicates, and then write accepted records to `flight_records`. A canonical
accepted record retains both the raw XCContest takeoff name/ID and a foreign key
to `sites`; ambiguous records go to an interim quarantine rather than receiving
a guessed site ID. T-014 owns duplicate/traceability behavior and T-015 owns
sanitized frozen parser fixtures. The local SQLite file stays ignored under
`data/local`.

**Related files:** [`architecture.md`](architecture.md),
[`handoff.md`](handoff.md), [`tasks.md`](tasks.md),
[`../data/README.md`](../data/README.md),
[`../services/ml/README.md`](../services/ml/README.md).

### DEC-021 — Finalize the normalized T-012 flight foundation schema

**Status:** Accepted

**Date:** 2026-08-02

**Context:** DEC-020 selected Drizzle-owned SQLite and bounded the T-012 scope,
but left the physical schema as a ticket deliverable. The source research,
confirmed seven-site coordinates, supplied XCContest list-page evidence, and
schema review established the needed normalisation and provenance rules.

**Decision:** T-012 creates only `flight_sources`, `sites`,
`source_site_mappings`, `ingestion_runs`, and `flight_records`, as specified in
the accepted T-012 implementation plan supplied during the task. The model is
3NF: source takeoff identity and matching evidence live in an immutable mapping
row; a canonical flight stores the mapping foreign key rather than repeating
site, token, source name, match method, match distance, or distance band.

Accepted flights use `(source_id, source_flight_id)` as their unique external
identity, `takeoff_at_utc` as the single stored event time, canonical scored
distance in kilometres, an optional track URL, and metadata/track validation
level. A source ID remains on the flight row so that the cross-run unique
constraint and composite source-consistency foreign keys are enforceable in
SQLite. `distance_band` is derived at read time.

Run provenance uses an immutable raw-artifact manifest outside SQLite. The run
stores the manifest path/hash, permission flags/reference, source scope URL,
pipeline version, lifecycle timestamps, and outcome counters. Per-artifact
retrieval times and optional ETags remain inside that manifest; no run-level
ETag or retrieval timestamp is stored.

Drizzle/Drizzle Kit remain the sole DDL and migration authority. Python uses
standard-library `sqlite3` only after migration and never owns schema history.

**Consequences:** The first migration creates the five tables and their
constraints/indexes; a second seed migration inserts the seven canonical sites
and XCContest source. There are no speculative weather/model/alert tables,
source aliases without approved evidence, raw payload rows, pilot data,
landing coordinates, score points, linear/tracklog distances, or track-status
column.

**Related files:** [`T-012-flight-schema.drawio`](T-012-flight-schema.drawio),
[`architecture.md`](architecture.md), [`handoff.md`](handoff.md),
[`../data/README.md`](../data/README.md), [`../CONTRIBUTING.md`](../CONTRIBUTING.md).


### DEC-022 - Collect XCContest list pages through the permitted rendered UI boundary

**Status:** Accepted

**Date:** 2026-08-04

**Context:** T-010 established that XCContest flight-list data is dynamically
rendered and that undocumented backend calls, session values and challenge
bypass must not be used. For the present T-013 work, the project owner has
confirmed an ordinary, low-volume browser workflow for the public flights page.
The first implementation needs raw evidence without prematurely owning the
parser, validation, matching, duplicate or persistence responsibilities.

**Decision:** The T-013 collector uses Playwright Chromium only through the
rendered XCContest controls and table. For every requested season it selects
the `BG` country and `FAI3` (`PG *`) category, establishes non-increasing
scored distance order through the rendered length control, then uses the
rendered Next pager rather than calculating page URLs. It paces source state
transitions by at least three seconds, captures the exact rendered `#flights`
fragment once per page, and stops after the first captured page containing a
distance below 100 km. A full raw page is retained even when its final rows
are below the threshold; a later parser must exclude those rows from the
accepted dataset.

The command defaults to headless execution and offers `--headed` and
`--slow-mo-ms` for manual local inspection. It accepts one or more explicit
`--season` values and a fail-closed `--max-pages` safety cap. It does not accept
or persist a permission-reference argument. The later database-import slice
owns the `ingestion_runs` placeholder required by the accepted schema.

The collector writes ignored immutable raw fragments and a manifest under
`data/raw/xccontest/<run-key>/`, with ignored local progress or failure state
under `data/interim/xccontest/<run-key>/`. It must not call undocumented
backend endpoints, retain cookies/tokens, bypass login/consent/Cloudflare or
CAPTCHA, download IGC/track files, retain pilot identity, parse/normalize
flights, assign sites, decide canonical duplicates, or write SQLite records.

**Rationale:** Browser control interaction follows the scope explicitly
authorised for this project, while preserving exact source evidence for a
separate parser run. A source-provided pager avoids a brittle dependence on the
current hash/offset convention. The threshold and page cap reduce collection
volume without silently dropping potentially qualifying pages.

**Consequences:** Collector tests use a fake UI driver and synthetic fragments,
not a frozen source fixture. T-014 remains responsible for canonical duplicate
and persisted source-traceability behavior; T-015 remains responsible for
sanitized frozen parser fixtures. On 2026-08-04, the available headless browser
did not render a visible flight table, so live success is unverified. A
developer must perform a permitted `--headed` run in a normal browser
environment; an interstitial or challenge must be handled only by the ordinary
user flow, never bypassed.

**Related files:** [`../services/ml/README.md`](../services/ml/README.md),

[`handoff.md`](handoff.md), [`tasks.md`](tasks.md),
[`T-010-xccontest-research-report.md`](T-010-xccontest-research-report.md).

### DEC-023 - Partition saturated XCContest first-page views through visible filters

**Status:** Accepted

**Date:** 2026-08-06

**Supersedes:** the pagination portion of DEC-022.

**Context:** In the permitted ordinary browser workflow, XCContest rendered the
first BG/PG list successfully but did not refresh its table after the
source-provided pager action. Opening its offset fragment directly or attempting
to work around an interstitial/challenge is outside the approved boundary.
However, the rendered category, date, and sortable-table controls continue to
operate normally. A first page contains at most 100 rows, so a distance-sorted
page whose final row is still at least 100 km may omit qualifying flights.

**Decision:** For each selected season, collect one `BG` + `PG *` view in
descending distance order. If it is saturated, collect the exact disjoint solo
PG classes `CCC`, `EN D`, `EN C`, `EN B`, and `EN A`, again in descending
distance order. Only a saturated exact class is further divided by every date
offered in the rendered date control. For every still-saturated
class-and-date view, collect pilot, points, and airtime in both source-provided
orders as a best-effort supplement. Do not use the pager, calculate offset
URLs, call undocumented endpoints, or open concurrent tabs.

All source state transitions remain paced by at least three seconds. The
collector stores a separate raw fragment per nonempty category/date/sort view,
and the manifest records its scope. It records a `saturated_unresolved` season
status when a class-and-date view remains saturated even after supplementary
sorts; a successful command must surface that status as incomplete coverage.
It must not claim that alternate sort orders establish exhaustive collection.

**Rationale:** Exact classes create a smaller, non-overlapping partition than
the nested starred classes. Date partitioning is used only when necessary, which
keeps normal low-volume runs small. Alternate sorting may expose additional
records without relying on a prohibited navigation mechanism, but it is not a
completeness proof.

**Consequences:** `--max-pages` is replaced by a fail-closed `--max-views` cap
for all rendered views in a run. The raw collector still does not normalize,
retain pilot identity as an accepted field, deduplicate canonical records,
assign sites, or write SQLite. It may retain raw visible-row evidence and count
repeated source IDs so downstream parsing can prove coverage; it must not drop
overlapping raw observations. The T-013 parser/normalizer owns same-run collapse
by XCContest source flight ID before site assignment, while T-014 hardens
cross-run idempotency, conflict detection, and persisted traceability. T-015
scope remains unchanged. A developer must manually verify a permitted headed
run in a normal desktop browser before treating any live sample as validated.

**Related files:** [`../services/ml/src/paragliding_forecasts_ml/ingestion/xccontest/collector.py`](../services/ml/src/paragliding_forecasts_ml/ingestion/xccontest/collector.py),
[`../services/ml/src/paragliding_forecasts_ml/ingestion/xccontest/browser.py`](../services/ml/src/paragliding_forecasts_ml/ingestion/xccontest/browser.py),
[`../services/ml/README.md`](../services/ml/README.md),
[`handoff.md`](handoff.md).

### DEC-024 - Derive XCContest country scope from all canonical sites

**Status:** Accepted

**Date:** 2026-08-06

**Supersedes:** the hard-coded `BG` country selection in DEC-022 and DEC-023.

**Context:** The collector originally fixed its visible XCContest country filter to
Bulgaria. The canonical `sites` table already carries ISO2 country codes and is the
authoritative project scope. Future sites in other countries must expand source collection
without a collector code edit, while inactive sites remain relevant historical evidence.

**Decision:** Before a collector run creates a browser or raw-artifact directory, Python
uses only standard-library `sqlite3` to open the Drizzle-migrated SQLite file read-only.
It accepts only a relative `file:` URL below repository `data/`, opens it with `mode=ro`,
enables foreign keys, and neither creates a database nor runs DDL or migrations. URL
precedence is CLI `--database-url`, then `DATABASE_URL`, then
`file:./data/local/paragliding.db`. It reads every distinct country using
`SELECT DISTINCT country_code_iso2 FROM sites ORDER BY country_code_iso2`; `is_active`
does not filter this scope. An empty, invalid, unreadable, or unmigrated result fails
closed before browser interaction or artifact creation.

The collector processes each requested `season × country` target sequentially in one
browser session. Country is explicitly selected through the rendered source UI and is
verified against the selected filter and each row launch country. The global `--max-views`
cap remains fail-closed across the complete multi-country run. Manifest schema v2 records
the `all_sites` country scope, per-target statuses, and country-aware artifacts/checkpoints;
the collector version is `xccontest-collector/2`. Existing ignored raw evidence stays
immutable, and later parser work must accept legacy BG-only manifests as well as v2.

**Version policy:** Every change to collector behaviour, browser/source interaction, raw
evidence, run metadata, or CLI contract must increment `collector_version`. Every change
to manifest fields, shape, semantics, or compatibility must increment
`manifest_schema_version`. A collector change without the applicable version bump, focused
tests, and README/decision update is incomplete.

**Rationale:** Reusing the canonical database scope makes country expansion data-driven
without introducing another migration authority or Python dependency. Read-only discovery
prevents an attempted collection from silently creating an empty database or collecting an
accidental fallback scope. Explicit country provenance makes a multi-country raw run
auditable before parsing and persistence exist.

**Consequences:** Adding a site in a new country intentionally expands subsequent source
workload. The collector still does not parse, normalize, match sites, deduplicate, or write
accepted records. T-013 remains in progress; T-014 and T-015 retain their existing scopes.

**Related files:** [`../services/ml/README.md`](../services/ml/README.md),
[`../services/ml/src/paragliding_forecasts_ml/storage/sqlite.py`](../services/ml/src/paragliding_forecasts_ml/storage/sqlite.py),
[`handoff.md`](handoff.md), [`tasks.md`](tasks.md).

### DEC-025 - Use durable artifacts between versioned XCContest ingestion stages

**Status:** Accepted

**Date:** 2026-08-07

**Context:** The collector needs in-memory row values for collection coverage,
threshold, and country checks, while parsing must be replayable after the
browser process exits. A real manifest-v2 run also demonstrated that current
and archived XCContest seasons can expose different canonical detail URL path
forms. Passing collector-only Python objects directly into later ingestion
stages would make replay, audit, and failure recovery depend on one process and
would bypass the immutable evidence boundary.

**Decision:** The exact saved HTML fragments plus their versioned manifest are
the durable collector-to-parser interface. `RowObservation` remains a minimal
ephemeral collector-control model and is not a normalized ingestion payload.
The offline parser reads the immutable artifacts, verifies compatible manifest
metadata/hashes/counters, and writes versioned language-neutral staging output.
Separate stage commands are the current operational interface. A future single
ingestion command may orchestrate them, but stages must communicate through run
keys and durable artifacts or staging outputs rather than shared in-memory
objects.

Parser output versions are independent from collector and manifest versions.
Any change to accepted raw compatibility, selectors, parsing/normalization,
output semantics, deduplication/conflict behaviour, staging layout, or CLI
contract increments `PARSER_VERSION`, writes to a new non-overwriting
`parser-vN` directory, and updates focused compatibility tests and
documentation. Parser v2 accepts legacy/v1 and complete manifest-v2 input.

**Rationale:** Immutable stage boundaries preserve source evidence, allow
offline replay without another source request, make partial-run recovery
possible, and prevent transient browser models from becoming an undocumented
pipeline contract. Independent versioning makes old parser results auditable
while allowing current source variants to be handled explicitly.

**Consequences:** Collector DOM selectors and parser selectors share one source
module, but only the parser owns normalization. A one-command ingestion wrapper
must not skip raw artifact creation. Existing `parser-v1` staging remains
untouched; parser v2 writes a separate directory. Validation/site mapping and
SQLite persistence remain later T-013 slices.

**Related files:** [`../services/ml/README.md`](../services/ml/README.md),
[`../services/ml/src/paragliding_forecasts_ml/ingestion/xccontest/selectors.py`](../services/ml/src/paragliding_forecasts_ml/ingestion/xccontest/selectors.py),
[`handoff.md`](handoff.md).

## Open decisions

| Question | Options / constraints | Resolve by |
| --- | --- | --- |
| What exact T-012 field types, nullability, indexes, constraints, and migration layout should be used? | Must implement DEC-020's bounded Takt 2 tables, preserve source/provenance/validation data, retain numeric site IDs, and keep accepted flights distinct from quarantined candidates. | T-012 design and implementation. |
| Which task owns the persisted prediction schema and SQLite forecast adapter? | The backlog has flight and weather schema tasks but no explicit owner for storing T-022-T-024 outputs and replacing the T-002 mock adapter. Public units/status/provenance must be mapped deliberately. | Backlog planning before real predictions are connected to the API. |
| What are the final coordinates, aliases, and catchment radii for each site? | Current map points are provisional; Pastrina and the Dobrich regional model need particular confirmation. | T-009. |
| What retention, attribution, licensing, and rate limits apply beyond the current XCContest browser workflow? | T-013 has a project-owner-confirmed ordinary low-volume UI workflow; do not extend it to bulk/commercial use or SkyNomad without explicit terms. | Before broader collection or product use. |
| Which historical forecast/archive or reanalysis sources will be used? | Exact archived forecasts are preferred; reanalysis is the documented fallback. | T-016, with units refined in T-017. |
| Which first alert channel should be implemented? | Dashboard watchlist, email, Telegram, or another agreed channel; alerts require at least one-day lead time and deduplication. | T-027/T-028. |
| What deployment/distribution model is required beyond local development? | The MVP is local-first; cloud/distributed infrastructure needs a demonstrated requirement. | No task assigned; decide when deployment becomes an accepted scope item. |
| What license should the repository use? | No open-source license is currently selected. | Repository owner decision; no task assigned. |
