# Project Decisions

## Purpose

This document records durable project decisions, their rationale, and their
consequences. Temporary progress and Git state belong in
[`handoff.md`](handoff.md); full system design belongs in
[`architecture.md`](architecture.md); requirements belong in
[`project-brief.md`](project-brief.md); implementation work and status belong in
[`tasks.md`](tasks.md).

## Decision index

| Decision ID | Title                                                                           | Status     | Date       |
| ----------- | ------------------------------------------------------------------------------- | ---------- | ---------- |
| DEC-001     | Use one repository with bounded subprojects                                     | Accepted   | 2026-07-15 |
| DEC-002     | Use npm workspaces for TypeScript and uv for Python                             | Accepted   | 2026-07-15 |
| DEC-003     | Use TypeScript by default and limit Python to data/ML work                      | Accepted   | 2026-07-15 |
| DEC-004     | Use React/Vite for web and Node.js/Express for the public API                   | Accepted   | 2026-07-15 |
| DEC-005     | Share browser/API contracts in TypeScript and keep Python language-neutral      | Accepted   | 2026-07-15 |
| DEC-006     | Use a local-first MVP and SQLite storage direction                              | Accepted   | 2026-07-15 |
| DEC-007     | Preserve explicit forecast status, provenance, units, and safety semantics      | Accepted   | 2026-07-15 |
| DEC-008     | Keep generated/local data out of Git with a controlled fixture exception        | Accepted   | 2026-07-15 |
| DEC-009     | Use short-lived ticket branches and pull-request review                         | Accepted   | 2026-07-15 |
| DEC-010     | Organize the API by feature with manual dependency injection                    | Accepted   | 2026-07-17 |
| DEC-011     | Use Zod as the runtime browser/API contract validator                           | Accepted   | 2026-07-17 |
| DEC-012     | Use TSX and Vitest for the initial API development loop                         | Accepted   | 2026-07-17 |
| DEC-013     | Use Pino logging and Problem Details HTTP errors                                | Accepted   | 2026-07-17 |
| DEC-014     | Separate internal numeric site IDs from public slugs                            | Accepted   | 2026-07-20 |
| DEC-015     | Add dashboard-specific forecast read models                                     | Accepted   | 2026-07-21 |
| DEC-016     | Expose provisional map coordinates and confirm Pastrina spelling                | Accepted   | 2026-07-21 |
| DEC-017     | Use a focused React dashboard stack with Leaflet                                | Accepted   | 2026-07-22 |
| DEC-018     | Add a provisional detailed forecast-input read model                            | Accepted   | 2026-07-24 |
| DEC-019     | Use Playwright Chromium for local browser smoke coverage                        | Accepted   | 2026-07-25 |
| DEC-020     | Use a phased Drizzle-owned SQLite foundation for flight data                    | Accepted   | 2026-07-30 |
| DEC-021     | Finalize the normalized T-012 flight foundation schema                          | Accepted   | 2026-08-02 |
| DEC-022     | Collect XCContest list pages through the permitted rendered UI boundary         | Superseded | 2026-08-04 |
| DEC-023     | Partition saturated XCContest first-page views through visible filters          | Accepted   | 2026-08-06 |
| DEC-024     | Derive XCContest country scope from all canonical sites                         | Accepted   | 2026-08-06 |
| DEC-025     | Use durable artifacts between versioned XCContest ingestion stages              | Accepted   | 2026-08-07 |
| DEC-026     | Configure geographic catchments for every initial launch site                   | Accepted   | 2026-08-08 |
| DEC-027     | Review source-site mappings before flight acceptance                            | Accepted   | 2026-08-08 |
| DEC-028     | Default XCContest collection to conservative source pacing                      | Accepted   | 2026-08-11 |
| DEC-029     | Gate one-command XCContest persistence on mapping review                        | Accepted   | 2026-08-11 |
| DEC-030     | Reconcile repeated XCContest source flights without silent overwrite            | Accepted   | 2026-08-12 |
| DEC-031     | Lock weather-source roles and canonical feature semantics                       | Accepted   | 2026-08-16 |
| DEC-032     | Implement GFS and ERA5 weather ingestion in T-018                               | Accepted   | 2026-08-17 |
| DEC-033     | Finalize the normalized T-018 weather persistence schema                        | Accepted   | 2026-08-20 |
| DEC-034     | Use one packaged atmospheric catalogue and durable stage protocol               | Accepted   | 2026-08-21 |
| DEC-035     | Pin GFS GRIB parser identity and preserve only canonical weather quality states | Accepted   | 2026-08-21 |
| DEC-036     | Use reviewed site coordinates with bilinear points and radius evidence          | Accepted   | 2026-08-24 |
| DEC-037     | Validate weather sources through a hashed registry and policy                   | Accepted   | 2026-08-26 |
| DEC-038     | Preserve immutable weather artifacts through explicit stage supersession        | Accepted   | 2026-08-26 |
| DEC-039     | Separate hourly weather facts from daily feature builds                         | Accepted   | 2026-09-08 |
| DEC-040     | Fix S07 daily window, profile band, and accepted derivations                    | Superseded | 2026-09-08 |
| DEC-041     | Correct the common GFS S07 profile source contract                              | Accepted   | 2026-09-09 |
| DEC-042     | Activate audited S07 humidity and turbulent-flux inputs                         | Accepted   | 2026-09-09 |
| DEC-043     | Remove unrequired S07 resolved-inversion metrics                                | Accepted   | 2026-09-09 |
| DEC-044     | Bind daily GFS collection to the Sofia flying-window policy                     | Accepted   | 2026-09-10 |
| DEC-045     | Normalize GFS interval products to exact adjacent UTC windows                   | Accepted   | 2026-09-10 |
| DEC-046     | Make weather persistence immutable, atomic, and artifact-replayable             | Accepted   | 2026-09-10 |
| DEC-047     | Supply weather usage authority through an explicit local policy file            | Accepted   | 2026-09-11 |

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
module, but only the parser owns normalization. `CollectionReport` is a compact
command summary; per-artifact and per-target detail remains only in the manifest.
Version identifiers live in source-specific `versions.py`, while manifest compatibility
policy remains in `manifest.py`. A one-command ingestion wrapper must not skip raw
artifact creation. Existing `parser-v1` staging remains
untouched; parser v2 writes a separate directory. Validation/site mapping and
SQLite persistence remain later T-013 slices.

**Related files:** [`../services/ml/README.md`](../services/ml/README.md),
[`../services/ml/src/paragliding_forecasts_ml/ingestion/xccontest/selectors.py`](../services/ml/src/paragliding_forecasts_ml/ingestion/xccontest/selectors.py),
[`handoff.md`](handoff.md).

### DEC-026 - Configure geographic catchments for every initial launch site

**Status:** Accepted

**Date:** 2026-08-08

**Context:** Source list rows can expose launch coordinates that are near, but not bit-for-bit identical to, canonical launch coordinates. The initial T-009 locations need a deliberate tolerance for site-mapping proposals without reclassifying launch areas as broad regions.

**Decision:** Keep Sofia - Vitosha (Kominite), Zlatitsa, Sopot, Nevsha, Shumen, and Pastrina as `launch_area` sites and set their `catchment_radius_km` values to 5. Keep Dobrich as a `region` with its existing 30 km radius. Geographic matching considers every same-country site with a non-null radius; it does not branch on `site_type`. A coordinate inside exactly one configured radius is a strong mapping proposal, but remains quarantined until a human approves a `source_site_mapping` row.

**Rationale:** This supports ordinary coordinate drift around known launches while retaining a conservative reviewed-mapping gate. The existing schema already validates the radius independently of `site_type`, so no DDL change is needed.

**Consequences:** A reviewed custom Drizzle data migration applies the six 5 km values to existing and fresh databases. Matching code must use inclusive Haversine distance checks, quarantine overlaps, and never call an external geocoder. API/UI contracts remain unchanged because catchments are ingestion configuration.

**Related files:** [`../packages/database/src/schema.ts`](../packages/database/src/schema.ts), [`../packages/database/drizzle/20260808175017_set_launch_area_catchments/migration.sql`](../packages/database/drizzle/20260808175017_set_launch_area_catchments/migration.sql), [`handoff.md`](handoff.md).

### DEC-027 - Review source-site mappings before flight acceptance

**Status:** Accepted

**Date:** 2026-08-08

**Context:** XCContest parser staging preserves source launch name, optional point coordinates, and current opaque site-token URLs, but no source string or nearby coordinate may silently assign a canonical project site.

**Decision:** The site-mapping command creates ignored, grouped JSONL proposals and never writes mappings automatically. A reviewed JSONL file explicitly creates `provisional` or `approved` rows in `source_site_mappings`; approval requires a verification reference and timestamp. The validator accepts only approved mappings. It derives coordinate suggestions from every same-country site with a configured catchment radius, quarantines overlap or unknown evidence, and writes versioned accepted/quarantine/report outputs keyed by a mapping snapshot hash.

**Consequences:** Validation communicates only through parser-v2 JSONL, SQLite mapping rows, and versioned interim files. It neither contacts XCContest nor writes ingestion provenance or flight records; a later T-013 persistence slice owns those writes. Any change to source matching, proposal, review, or validation output semantics increments the corresponding mapping or validation version.

**Related files:** [`../services/ml/src/paragliding_forecasts_ml/ingestion/xccontest/site_mapping.py`](../services/ml/src/paragliding_forecasts_ml/ingestion/xccontest/site_mapping.py), [`../services/ml/src/paragliding_forecasts_ml/ingestion/xccontest/validator.py`](../services/ml/src/paragliding_forecasts_ml/ingestion/xccontest/validator.py), [`../services/ml/README.md`](../services/ml/README.md).

### DEC-028 - Default XCContest collection to conservative source pacing

**Status:** Accepted

**Date:** 2026-08-11

**Context:** XCContest does not publish an official numerical rate limit for the permitted
rendered-browser workflow. Repeated local collector runs without a conservative delay resulted
in an apparent IP-specific server failure. Playwright `slow_mo` delays browser actions, but it is
not a source-rate-limit guarantee.

**Decision:** Pace every browser navigation and source-changing rendered-control operation by
30 seconds by default. The collector accepts a configured source delay no lower than three
seconds; a value below 30 requires an explicit `--acknowledge-rate-limit-risk` flag and is
recorded in manifest schema v3. `--slow-mo-ms` remains debugging-only. The collector uses one
sequential browser session, opens no parallel tabs, does not retry failed source operations, and
stops for manual inspection on an unsuccessful navigation, challenge, or missing table. It does
not rotate IPs, use proxies, or bypass source controls.

**Consequences:** Collector v3 and manifest schema v3 record the effective pacing policy while
parser compatibility retains immutable legacy and v2 raw runs. Thirty seconds is a conservative
operational default, not a published XCContest guarantee. Developers must stop rather than retry
when the source presents an access failure.

**Related files:** [`../services/ml/README.md`](../services/ml/README.md),
[`../services/ml/src/paragliding_forecasts_ml/ingestion/xccontest/browser.py`](../services/ml/src/paragliding_forecasts_ml/ingestion/xccontest/browser.py),
[`handoff.md`](handoff.md).

### DEC-029 - Gate one-command XCContest persistence on mapping review

**Status:** Accepted

**Date:** 2026-08-11

**Context:** The T-013 collector, parser, proposal, validator, and persistence slices already
communicate through immutable raw/interim artifacts. A new top-level command should reduce
operator steps without auto-approving site mappings or persisting a partial mapping decision that
cannot safely be amended before T-014's cross-run idempotency policy.

**Decision:** `xccontest-ingest fresh` performs preflight, collection, parsing, proposal, and
validation sequentially. It automatically creates the read-only mapping proposal artifact, but
never calls mapping `apply`. It persists immediately only when validation has no mapping-actionable
quarantines and at least one approved record. Otherwise it exits with the explicit
`awaiting_mapping_review` status before writing canonical flights. After a human applies reviewed
mapping decisions, `xccontest-ingest resume --run-key <uuid>` performs only offline reusable stages,
creates or verifies the validation output for the current mapping snapshot, and persists exactly
once. A rejection in the standard sibling review file resolves only the matching proposal evidence:
it remains quarantined and is excluded from persistence, but does not block the approved subset. New,
unresolved, ambiguous, provisional, or country-mismatched mapping evidence still blocks the run. An
explicit `--persist-approved-only` permits a reviewer to retain mapping-actionable
quarantines and persist the approved subset; this forfeits adding the remaining records to that
persisted run until T-014.

**Consequences:** Every stage preserves its current non-overwriting raw/interim directory and
SHA-256 contract. A new mapping snapshot gets a separate `validation-v2/<snapshot>/` directory;
parser artifacts are not recreated and the collector never runs during `resume`. Separate stage
commands remain supported for focused work and recovery. T-014 still owns duplicate/upsert and
retroactive traceability behavior.

**Related files:** [`../services/ml/README.md`](../services/ml/README.md),
[`../services/ml/src/paragliding_forecasts_ml/ingestion/xccontest/pipeline.py`](../services/ml/src/paragliding_forecasts_ml/ingestion/xccontest/pipeline.py),
[`handoff.md`](handoff.md).

### DEC-030 - Reconcile repeated XCContest source flights without silent overwrite

**Status:** Accepted

**Date:** 2026-08-12

**Supersedes:** the T-014 limitation in DEC-029 that `--persist-approved-only`
forfeits adding later approved records to that persisted run. DEC-029's
mapping-review gate remains accepted.

**Context:** The database already enforces `(source_id, source_flight_id)` as a
canonical source identity, while a run can be resumed after a partial approved
subset or a later run can legitimately observe the same flight. Rejecting all
repeats loses offline recovery; a generic upsert or replace could silently
change a source URL, site mapping, takeoff time, distance, duration, route, or
track evidence. T-014 also needs durable per-record quality/provenance notes
without expanding the validated T-012 schema speculatively.

**Decision:** Persistence compares every accepted normalized flight with the
canonical SQLite row for the same source identity before it writes. Exact
same-run evidence is a successful no-op. Cross-run exact duplicates revalidate
the existing canonical row and retain its original creator run. Missing duration,
track, or route information may be enriched only in the defined direction; a
lower-quality or missing incoming value cannot erase an existing known value.
A metadata-to-track validation upgrade is automatic, but not the reverse.

A changed source URL, approved site-mapping ID, takeoff timestamp, normalized
scored distance, two concrete distinct durations, two known distinct route
values, or two concrete distinct track URLs is a conflict. A conflict writes
non-overwriting, ignored `reconciliation-v1/<plan-sha256>` proposal/report
evidence under the run's interim directory and returns
`awaiting_reconciliation_review` without any database write. A complete sibling
JSONL decisions file must copy immutable proposal identity/fingerprints and give
each proposal either `keep_existing` or `accept_incoming`, plus an auditable
reference, reviewer, UTC review timestamp, and rationale. Invalid, stale, or
partial decisions fail closed. One valid reviewed transaction resolves all
conflicts and non-conflicts together.

The normal `fresh`/mapping-review/`resume` gate does not change. The explicit
`--persist-approved-only` path can now create a partial run; after mapping
review, offline resume reconciles prior accepted records and adds newly accepted
records under the same run rather than failing for duplicates.

`flight_records.source_flight_url` remains the chosen source link.
`flight_records.validation_notes` stores schema-v1 machine-verifiable JSON for
versions, mapping/accepted evidence hashes, artifact-reference count/hash,
derived quality flags, and reconciliation outcome/event/optional review
reference. `ingestion_runs.notes` stores append-only versioned persistence
events. Existing legacy notes are not destructively backfilled. No migration is
required because these existing text provenance fields are sufficient; Drizzle
remains the sole schema owner.

**Rationale:** This preserves the highest-value canonical record, allows safe
partial-run recovery and cross-run revalidation, makes a material contradiction
visible to a human, and retains enough hashes and references to audit the
choice without copying raw artifacts or pilot identity into SQLite.

**Consequences:** The persistence revision is `xccontest-persistence/3`.
Operators use the documented reconciliation proposal/decision workflow and
`xccontest-ingest resume` for resolution; neither path contacts XCContest.
Focused unit and migrated-temporary-SQLite integration tests cover enrichment,
preservation, no-op replay, cross-run duplicates, conflict atomicity, stale
decisions, reviewed resolution, and pipeline pause propagation. T-015 remains
responsible for committed sanitized parser fixtures.

**Related files:** [`../services/ml/README.md`](../services/ml/README.md),
[`../services/ml/src/paragliding_forecasts_ml/ingestion/xccontest/reconciliation.py`](../services/ml/src/paragliding_forecasts_ml/ingestion/xccontest/reconciliation.py),
[`../services/ml/src/paragliding_forecasts_ml/ingestion/xccontest/persistence.py`](../services/ml/src/paragliding_forecasts_ml/ingestion/xccontest/persistence.py),
[`handoff.md`](handoff.md).

### DEC-031 - Lock weather-source roles and canonical feature semantics

**Status:** Accepted

**Date:** 2026-08-16

**Context:** T-016 identified candidate historical forecast and reanalysis
sources, but generic provider documentation could not prove exact per-model
field availability, native units, null behavior, step semantics, terrain fit, or
payload cost. T-017 tested representative Bulgarian sites, weather cases, and
forecast leads, then parsed bounded GFS, ERA5, CERRA, and IGRA evidence and
exact hosted IFS HRES/ICON-EU responses.

**Decision:** Use GFS as the coarse exact long-history forecast comparator,
ICON-EU as the preferred recent regional profile forecast, and IFS HRES only as
a conditional high-resolution surface/PBL component rather than a sole source.
Use ERA5 as the long-history reanalysis baseline and CERRA only as an offline
terrain-resolution reanalysis comparator. Use IGRA as upper-air observational
validation, never as a forecast substitute. ERA5 is not a live fallback, and
CERRA's full-domain payload/queue cost precludes per-site live requests.

The T-017 machine-readable catalogue owns canonical weather names and units.
Native representations, model/run/valid/step times, grid point and model
elevation, missing metadata, and source licence/provenance remain mandatory.
Provider PBL/cloud base stay distinct from derived PBL/LCL. CIN is nullable and
normalized to a non-negative magnitude without hiding the native convention.
Thermal strength is not a renamed vertical velocity or square root of TKE;
convective velocity scale may be derived only from validated buoyancy flux and
boundary-layer depth. Wind may enter as native `u`/`v` or speed/direction, with
the counterpart derived and versioned.

**Consequences:** T-018 may implement the locked catalogue but must preserve
explicit `missing` and `derived` states and cannot assume every source supplies
every canonical field. ERA5 bitmap/sentinel handling is required. CERRA's
verified surface cloud fields are already percent, surface wind components must
be derived from native speed/direction, and direct CERRA PBL/cloud-base/CAPE/CIN
remain unavailable. A commercial release still requires owner confirmation of
provider licences, attribution, retention, and direct-source/archive operations.

**Related files:** [`T-017-weather-feature-spike-report.md`](T-017-weather-feature-spike-report.md),
[`weather-field-catalogue.json`](../services/ml/src/paragliding_forecasts_ml/ingestion/atmosphere/resources/weather-field-catalogue.json),
[`handoff.md`](handoff.md).

### DEC-032 - Implement GFS and ERA5 weather ingestion in T-018

**Status:** Accepted

**Date:** 2026-08-17

**Context:** T-017 locks canonical weather semantics and source roles, but it
does not implement storage or source collectors. The project now needs one
complete, reproducible ingestion path before T-020: exact forecasts whose
historical and operational distributions match, plus a separately preserved
reanalysis baseline. A model trained on GFS snapshots cannot safely accept an
ICON-EU or IFS HRES snapshot merely because canonical names and units match.

**Decision:** T-018 implements the source-neutral weather schema and the full
GFS and ERA5 ingestion pipeline through SQLite. GFS is the only exact-forecast
source in this phase, both for historical archive collection and for the
current/future forecasts shown by the product. The collector selects an
explicit, complete GFS run, retains run/availability/retrieval/valid/lead and
grid provenance, and persists the source without substitution by another
forecast model. When a new GFS run is unavailable, retain the most recent
successful GFS result and expose its age rather than silently changing source.

ERA5 is collected independently through the registered CDS access path. It
remains reanalysis, never a live or row-level substitute for a missing GFS
forecast. T-018 stores it with its own reference/step/statistic provenance for
later forecast-to-ERA5 verification, bias-correction pairs, climatology and
separate reanalysis cohorts. Those joins, datasets and all ML work remain out
of T-018. Product documentation and presentation that use ERA5 must include
the applicable Copernicus/ECMWF attribution required by the dataset licence.

T-018 does not implement Open-Meteo, ICON-EU, IFS HRES, direct DWD ICON-EU or
CERRA collectors. They remain future options, each requiring a new accepted
source decision, source-specific adapter and compatible model evaluation:

- Open-Meteo ICON-EU or direct DWD ICON-EU could provide a finer regional
  profile source. Direct DWD would require immutable collection-time archival
  of every selected complete run because it is not an arbitrary-date archive.
- Open-Meteo IFS HRES could provide a high-resolution surface/PBL component,
  but it must not be treated as a complete profile source without a verified
  profile-capable endpoint and a compatible model path.
- CERRA could be used later as an offline terrain-resolution reanalysis
  comparator, with its large full-domain payload and queued retrieval cost
  handled outside operational collection.

IGRA remains the T-019 observational sounding branch and is not part of this
weather-forecast ingestion scope.

**Consequences:** T-018's weather contract and persistence must retain source and
provider-dataset identity, source product key, run/reference/availability,
retrieval/valid/lead/step times, grid coordinates/elevation, interpolation, native provenance, field quality
and feature-contract version. Forecast and reanalysis rows stay distinct. A
future forecast-source addition must select a compatible weather snapshot and
prediction artifact together; it must never relabel or silently blend another
model's values into a GFS cohort. Neighbourhood calculations use physical
distance and retain their footprint version.

**Related files:** [`T-017-weather-feature-spike-report.md`](T-017-weather-feature-spike-report.md),
[`weather-field-catalogue.json`](../services/ml/src/paragliding_forecasts_ml/ingestion/atmosphere/resources/weather-field-catalogue.json),
[`T-016-forecast-data-research-report.md`](T-016-forecast-data-research-report.md),
[handoff.md](handoff.md).

### DEC-033 - Finalize the normalized T-018 weather persistence schema

**Status:** Accepted

**Date:** 2026-08-20

**Context:** T-018/S01 needs an exact relational contract before GFS and ERA5
collectors can persist data. Earlier drafts mixed direct scalar values,
repeatable atmospheric variants, interval values, field quality, grid sampling,
and ingestion provenance. They also risked redundant site/grid foreign keys,
a speculative artifact catalog, and a fabricated model-version value that GFS
and ERA5 files do not reliably publish.

**Decision:** The reviewed `T-012-flight-schema.drawio` weather section is the
physical schema source of truth. Drizzle owns fourteen weather tables:

- `weather_sources`, `weather_ingestion_runs`, and `weather_product_runs` for
  provider dataset, pipeline execution, and native product/cycle identity;
- `weather_site_sampling_configs`, `weather_grids`, `weather_grid_points`,
  `weather_sampling_footprints`, and `weather_sampling_footprint_nodes` for one
  approved site coordinate and reproducible point/neighbourhood sampling;
- `weather_samples`, `weather_profile_levels`,
  `weather_convection_measurements`, and `weather_interval_measurements` for
  direct scalar, vertical-profile, repeatable CAPE/CIN, and explicit
  interval/statistic values; and
- `weather_feature_snapshots` plus `weather_field_provenance` for versioned
  derived ML inputs and per-field native/quality meaning.

Flight and weather ingestion provenance remains separate. The existing
`ingestion_runs` table is renamed to `flight_ingestion_runs`; weather runs use
`weather_ingestion_runs`. A weather run retains `ingestion_method` separately
from `request_purpose`, run-level training/operational permission decisions,
the raw manifest pointer/hash, one pipe-delimited `pipeline_version`, lifecycle,
and counters. The rename preserves the old flight table's internal constraint
and index names so SQLite can perform a data-preserving table rename instead of
a risky rebuild.

No `model_version` column is stored for GFS or ERA5. Reproducibility comes from
`weather_sources`, `source_product_key`, reference/availability/valid times,
raw manifest/hash, and versioned pipeline components; an absent provider
semantic version is never replaced by an invented value.

The storage shape is deliberately hybrid rather than EAV-only or one giant
wide row. Direct single-valued surface fields live on `weather_samples`;
pressure levels, parcel/layer convection variants, and time-window metrics use
normalized child rows; derived ML-ready fields use a versioned wide feature
snapshot. `weather_field_provenance` is the only owner of `quality_state`, one
field at a time. Interval rows retain `source_step_start_hours` and
`source_step_end_hours`, but do not duplicate a row-level quality state.
Temperature is canonical Kelvin, humidity/cloud cover are percent, wind is
metres per second, direction is degrees from north, and explicit AGL/MSL names
are retained wherever present in the accepted diagram.

The schema avoids transitively redundant foreign keys. A sample reaches its
site/grid through `point_footprint_id`, and a footprint node reaches its grid
through `grid_point_id`. Field-provenance ownership is polymorphic but exactly
one of its five owner foreign keys must be set; partial unique indexes enforce
one `(owner, field_code, field_variant)` row despite SQLite NULL semantics.
Nullable convection layer/method-version identities use partial unique indexes
for the same reason.

One weather coordinate is approved per canonical site for T-018. Dobrich uses
the Kardam accepted-flight centroid `43.746321, 28.074025`; the canonical
`sites` coordinate stays the region/map centre. Multi-point regional
aggregation is not implemented.

There is no separate `weather_artifacts`, `weather_surface_samples`,
`weather_profiles`, or generic one-to-many sampling-point table. Raw/interim
files remain immutable filesystem evidence referenced by the run manifest.
Soundings remain T-019.

Cross-row rules that SQLite CHECK constraints cannot express remain mandatory
pipeline validation: point interpolation weights sum to one; footprint/grid
nodes belong to the same grid; point versus neighbourhood footprint roles are
used correctly; grid first-seen runs match the grid source; and every interval
metric and CAPE/CIN slot receives its matching field-provenance row in the same
persistence transaction.

The schema is delivered as one coherent generated/reviewed migration because
all fourteen tables form one foreign-key graph. The migration contains no
GFS/ERA5, site-coordinate, grid, or footprint seed rows; those require separate
reviewed collector/configuration inputs. Migration tests may apply it only to
temporary SQLite files before owner review; generation does not authorize
application to the configured local database.

**Consequences:** Collectors and persistence adapters have an exact target and
must not create parallel JSON/EAV storage. Query indexes follow run lookup,
product/source time, site/footprint valid time, profile pressure, interval
window, field quality, and ingestion-provenance paths. Adding a new source or
metric requires an explicit compatibility/schema decision rather than an
unreviewed column or field code.

**Related files:** [`T-012-flight-schema.drawio`](T-012-flight-schema.drawio),
[`architecture.md`](architecture.md), [`handoff.md`](handoff.md),
[`../packages/database/src/schema.ts`](../packages/database/src/schema.ts).

### DEC-034 - Use one packaged atmospheric catalogue and durable stage protocol

**Status:** Accepted

**Date:** 2026-08-21

**Context:** T-018/S02 needs runtime validation of the T-017 canonical weather
vocabulary and reproducible boundaries before a GFS or ERA5 adapter can be
implemented. A copied Python enum, mutable intermediate files, or one combined
pipeline version would permit silent vocabulary drift and make offline replay
ambiguous.

**Decision:** Move the single machine-readable T-017 catalogue into the ML
package resources. Load it at runtime with strict validation; do not retain a
second manual field vocabulary. Use strict versioned contracts for request
plans, raw manifests, native parser batches, canonical samples/profile levels,
validation reports, feature snapshots, stage manifests, and persistence
receipts. Source adapters own planning/collection and source-native parsing;
source-neutral normalization, spatial alignment, validation, feature building,
and persistence have separate component versions.

Raw evidence lives under `data/raw/weather/<run-key>/`; all derived evidence and
an append-only hash-linked state ledger live under
`data/interim/weather/<run-key>/`. Every durable file is exclusive-create and
SHA-256 verified. `fresh` and offline `resume` are execution modes, while
`failed`, `partial`, `quarantined`, and `persisted` are protocol dispositions.
The existing SQLite lifecycle remains `running`/`succeeded`/`failed`; S08 maps
filesystem outcomes into it without a schema change.

**Consequences:** S02 does not expose a placeholder weather command, make a
network request, parse a real GRIB payload, or write SQLite. Each later slice
must add only its real stage implementation and use the S02 artifact/hash/state
boundary. The T-017 report and all decisions link to the packaged resource.

**Related files:**
[`weather-field-catalogue.json`](../services/ml/src/paragliding_forecasts_ml/ingestion/atmosphere/resources/weather-field-catalogue.json),
[`contracts.py`](../services/ml/src/paragliding_forecasts_ml/ingestion/atmosphere/contracts.py),
[`artifacts.py`](../services/ml/src/paragliding_forecasts_ml/ingestion/weather/artifacts.py),
[`handoff.md`](handoff.md).

### DEC-035 - Pin GFS GRIB parser identity and preserve only canonical weather quality states

**Status:** Accepted

**Date:** 2026-08-21

**Context:** T-018/S04 must make NOAA GFS GRIB parsing reproducible without
trusting mutable ecCodes short names, while preserving the quality vocabulary
already accepted by the weather persistence contract. GFS `HPBL` demonstrates
the risk: in the observed operational table it has a numeric local parameter
identity but an unusable generic short name.

**Decision:** Use Python `eccodes` 2.47.0 and a versioned numeric profile for
NOAA `kwbc` GRIB2 master table 2/local table 1. Verify centre, table versions,
discipline/category/number, level, reference/valid time, step and statistics
before grids pass the raw boundary. Preserve native missing bitmap/sentinel
masks and use only `real`, `derived`, `missing`, `sentinel_missing`, and
`invalid_payload` quality states. Normalize signed GFS CIN to the canonical
positive magnitude while retaining the native sign convention; retain native
U/V and derive wind speed/direction; retain a stated accumulation interval
without inferred de-accumulation unless adjacent intervals and a reset are
proven. GUST has no T-017/S01 destination, so retain it only as native evidence
with an explicit unsupported canonical mapping outcome. Orography is not a
canonical weather measurement, but it must cross the S04 boundary as static
model-grid terrain evidence for S05 elevation diagnostics and below-terrain
filtering.

**Consequences:** S05 consumes hash-verified canonical grid artifacts, not raw
GRIB. A new GUST persistence field requires a separate catalogue/schema decision.
The pinned profile must be deliberately reviewed if NOAA changes its GRIB table
or source identity.

**Related files:** [`profile.py`](../services/ml/src/paragliding_forecasts_ml/ingestion/gfs/profile.py),
[`parser.py`](../services/ml/src/paragliding_forecasts_ml/ingestion/gfs/parser.py),
[`normalizer.py`](../services/ml/src/paragliding_forecasts_ml/ingestion/gfs/normalizer.py),
[`handoff.md`](handoff.md).

### DEC-036 - Use reviewed site coordinates with bilinear points and radius evidence

**Status:** Accepted

**Date:** 2026-08-24

**Context:** T-018/S05 needs one deterministic value at each approved weather
site while retaining enough nearby-grid evidence for later spatial features.
The regional Dobrich map centre is not a meaningful launch/sampling point, GFS
terrain is much coarser than the reviewed site terrain, and silently selecting
a nearest cell would discard useful sub-cell position information. The Project
Brief asks for derived convergence and wind-shear indicators, but it does not
require S05 itself to invent a pressure-gradient/divergence formula.

**Decision:** Provision one reviewed `weather_site_sampling_configs` row for
each of the seven canonical sites through committed data migrations. Six use
their canonical site coordinate; Dobrich uses the accepted Kardam coordinate
`43.746321, 28.074025`. Missing or incomplete configuration fails the offline
sampling preflight and is never auto-created during ingestion.

Fetch reviewed reference elevation through the explicit-network
`copernicus-elevations` command using Copernicus DEM GLO-30, bilinear sampling,
and EGM2008 orthometric height. The command is repeatable, not a refresh/resume
protocol: it emits an ignored review artifact and never writes SQLite. A
separate guarded migration pins the seven reviewed results and their reference;
later provider changes require a new review and migration.

The packaged `canonical-site-sampling-policy-v1` uses strict bilinear point
sampling on the canonical regular latitude/longitude grid. Missing contributing
nodes produce an explicit missing value; weights are never renormalized. Wind
components are interpolated first, then speed and meteorological direction are
derived. Nearest-point sampling remains schema-compatible for future policies
but is not implemented by S05.

Separately retain an inclusive 50 km Haversine node footprint for MSL pressure,
surface U/V and 925 hPa U/V. S05 does not calculate convergence, divergence or
pressure-gradient features; it preserves deterministic node evidence for the
versioned S07 feature builder. Pressure-level geopotential height is MSL;
subtract the reviewed site elevation and the bilinear model orography to expose
site-AGL and model-AGL. Exclude a pressure level when either AGL value is
negative. Always report signed and absolute model-minus-site terrain mismatch.

Fingerprint the input manifest, canonical grid geometry and orography, reviewed
site snapshot, packaged policy, point/radius footprints and component version.
The per-sample identity key is an artifact-level deterministic identity, not a
new SQLite column. Equal verified inputs and policy must produce byte-identical
site and neighbourhood artifacts.

**Consequences:** `gfs-sample --run-key <uuid>` is offline-only, reads the
migrated SQLite configuration read-only, consumes only a complete normalized
state event, and appends `spatially_aligned/complete`. Coarse GFS terrain/site
differences remain visible and can affect pressure-level exclusion. S07 owns
the scientific definition and validation of any neighbourhood-derived feature.

**Related files:**
[`canonical-site-sampling-policy-v1.json`](../services/ml/src/paragliding_forecasts_ml/ingestion/weather/resources/canonical-site-sampling-policy-v1.json),
[`spatial.py`](../services/ml/src/paragliding_forecasts_ml/ingestion/weather/spatial.py),
[`sites.py`](../services/ml/src/paragliding_forecasts_ml/ingestion/weather/sites.py),
[`handoff.md`](handoff.md).

### DEC-037 - Validate weather sources through a hashed registry and policy

**Status:** Accepted

**Date:** 2026-08-26

**Context:** T-018/S06 must decide whether validation needs invented model IDs,
persisted response headers, or an XCContest-style manual mapping gate. GFS and
ERA5 have different expected coverage, while a source-neutral validator must
fail closed for an unknown or inactive source without turning `weather_sources`
into mutable collector transport configuration.

**Decision:** Seed GFS `noaa_gfs_0p25_aws_grib2` and ERA5 `copernicus_era5` as
active `weather_sources` rows through a guarded migration. Treat that table as
the persistent registry/allow-list and snapshot/hash the exact row in every S06
validation boundary. Source adapters retain their pinned endpoint and their
source-specific request construction; the registry base URL is provenance, not
a runtime override. Do not add a fabricated `model_id`/`model_version`, retain
observed HTTP response headers, or add a manual alias/mapping approval path.

Use packaged `source-aware-weather-validation-policy/1`, keyed by registry
source code. S06 is offline-only and validates hash-linked S05 artifacts against
source/kind, payload media/shape evidence, canonical unit/range/time/lead,
profile order/duplicates/core null policy, and terrain mismatch. GFS requires
a lead and, as superseded by DEC-041, the
1000/975/950/925/900/850/800/750/700/650/600/550/500 hPa profile grain; ERA5 requires
the same profile grain and no lead. Accepted, missing, and quarantined
artifacts are immutable;
quarantine returns exit `2` and blocks S07. S05 v2 no longer assigns a coverage
status; S06 owns that disposition while still reading legacy S05 v1 artifacts.

**Consequences:** Missing required coverage is not equivalent to a corrupt
payload: both receive stable machine-readable reasons, but only violated source
policy/payload integrity quarantines the affected sample. A repeated validator
invocation reuses its evidence and produces no duplicate state event. New source
support or a changed policy requires a new versioned policy/validator and an
explicit compatibility decision.

**Related files:**
[`weather-validation-policy.json`](../services/ml/src/paragliding_forecasts_ml/ingestion/weather/resources/weather-validation-policy.json),
[`validation.py`](../services/ml/src/paragliding_forecasts_ml/ingestion/weather/validation.py),
[`schema.ts`](../packages/database/src/schema.ts),
[`handoff.md`](handoff.md).

### DEC-038 - Preserve immutable weather artifacts through explicit stage supersession

**Status:** Accepted

**Date:** 2026-08-26

**Context:** A weather run can contain valid artifacts from multiple component
versions, for example `spatial-v1` followed by `spatial-v2`. The original
linear state ledger accepted only the next stage, so a newer artifact could be
written immutably but remain absent from the ledger. Selecting the highest
filesystem directory would bypass the audited state history and is unsafe.

**Decision:** Keep state events append-only and read schema-v1 events for
backward compatibility. New schema-v2 events may set `supersedes_sequence` only
for a derived stage (`parsed`, `normalized`, `spatially_aligned`, `validated`,
or later derived stages). It must identify the current completed boundary for
that same stage and carry distinct immutable evidence. Raw collection and
persistence remain non-supersedable within a run. Stage commands reuse an exact
producer-version/fingerprint/upstream match; otherwise they create or verify the
versioned artifact and append the explicit superseding event. Downstream stages
select the latest completed event for their immediate input; validation also
requires its own recorded upstream spatial boundary to match it.

**Consequences:** A run remains reproducible at every historical boundary while
newer parser, normalizer, spatial, validator, or feature versions can progress
without a new run UUID. A completed artifact left unledgered by older code can
be hash-verified and attached once, never rewritten. This does not turn raw
collection into a mutable resume operation; a new collection remains a new run.

**Related files:**
[`state.py`](../services/ml/src/paragliding_forecasts_ml/ingestion/weather/state.py),
[`artifacts.py`](../services/ml/src/paragliding_forecasts_ml/ingestion/weather/artifacts.py),
[`parser_cli.py`](../services/ml/src/paragliding_forecasts_ml/ingestion/gfs/parser_cli.py),
[`spatial_cli.py`](../services/ml/src/paragliding_forecasts_ml/ingestion/weather/spatial_cli.py),
[`validation_cli.py`](../services/ml/src/paragliding_forecasts_ml/ingestion/weather/validation_cli.py).

### DEC-039 - Separate hourly weather facts from daily feature builds

**Status:** Accepted

**Date:** 2026-09-08

**Context:** DEC-033 mixed provider-time facts with an ML feature row designed
around one valid instant. S07 instead needs one feature build for a site's
local flying day, calculated from accepted hourly inputs inside the fixed local
flying window. The old schema also retained repeated valid ranges, hashes, and
grid metadata that are derivable or belong in immutable artifacts rather than
stable relational facts.

**Decision:** Supersede the weather-storage portion of DEC-033 with a
source-neutral hourly-to-daily contract. A provider cycle remains
`weather_product_runs` and owns its `weather_sources` reference. Exact provider
times live in `weather_product_valid_times` as unique
`(product_run_id, valid_at_utc)` rows with optional non-negative lead.
`weather_ingestion_runs` references one product run and one
`target_local_date`; it does not repeat `source_id`. Its lifecycle, permission,
manifest SHA-256, pipeline version, counters, and error fields remain because
they describe the ingestion execution.

Provider-time facts become `weather_point_samples` linked to their ingestion
run, product valid time, and point footprint. Their child tables become
`weather_point_profile_levels`, `weather_point_convection_measurements`, and
`weather_point_interval_measurements`. Interval rows retain canonical
start/end and statistic but not duplicate native step columns; native step
evidence remains in `weather_field_provenance`. Profile levels retain provider
geopotential MSL height, derived site-AGL height, and pressure-level vertical
velocity. Model-AGL remains an interim diagnostic, not a relational column.

Replace the one-sample feature row with one typed
`weather_daily_feature_snapshots` row per ingestion, point footprint, and
feature contract. `weather_daily_feature_snapshot_inputs` records the exact
hourly input set as a relational many-to-many mapping, so one immutable hourly
fact can participate in different feature-contract versions without copying
it. `weather_daily_feature_profile_layers` stores repeatable daily vertical
features with explicit AGL boundaries. `weather_field_provenance` gains daily
snapshot and layer owners; its exactly-one-owner rule and partial unique
indexes remain the field-quality and missing/unsupported source of truth.

Provider PBL and cloud base remain explicitly provider-named. No derived-PBL
column duplicates a provider value. Mixed-layer LCL, buoyancy flux, and
convective velocity scale are nullable typed daily outputs and may be
populated only by an accepted, versioned derivation; otherwise provenance must
record `missing` or `unsupported`.

Keep `weather_grids` as minimal provider grid identity
`(source_id, grid_key)`. Grid points, footprints, and footprint nodes retain
the interpolation geometry. Remove grid dimensions/step/hash, grid first-seen
run, footprint version/hash, and feature input hash. Sampling identity is its
method version plus immutable relational site/grid/node definition; daily input
identity is the join table. The raw manifest hash is the only relational
SHA-256 retained. Do not add a grid-point-measurement table or database
window-policy table; raw node fields and the versioned flying-window policy
remain immutable artifacts/code until database configuration has a product
need.

The generated migration is intentionally lossy for the unused pre-persistence
weather runtime tables. It must fail before DDL when any legacy runtime weather
row exists. Apply it only after owner review and confirmation that the target
database has no weather runtime rows requiring conversion.

**Consequences:** S07 can consume the same validated canonical contract from
GFS or ERA5, aggregate hourly facts into one local-day build, and rebuild
another feature-contract version from the recorded inputs. Local date is
stored once on the ingestion run and exact UTC time once on the product valid
time. Cross-row provider/run, footprint-role, complete-input, and flying-window
rules remain persistence and feature-builder transaction responsibilities.

**Related files:** [`schema.ts`](../packages/database/src/schema.ts),
[`migration.sql`](../packages/database/drizzle/20260908181331_refactor_daily_weather_persistence/migration.sql),
[`handoff.md`](handoff.md).

### DEC-040 - Fix S07 daily window, profile band, and accepted derivations

**Status:** Accepted

**Date:** 2026-09-08

**Context:** S07 needs one ML-ready site/day feature snapshot, while source
artifacts remain hourly. The prior GFS selector and validation policy only kept
925/850/700 hPa, which cannot reliably bracket the adopted AGL layers. The
earlier feature plan also proposed aggregates that are not part of the reviewed
typed daily schema.

**Decision:** Use Europe/Sofia, 10:00--20:00 inclusive, as
sofia-flying-window/1: exactly eleven expected hourly valid instants after
DST-aware ZoneInfo conversion. An aggregate is missing only when that feature's
required hourly or interval input coverage is incomplete; another feature in
the same daily snapshot may remain complete. Do not split the day across runs
or assemble one feature snapshot from multiple run keys.

Collect, normalize, sample, and validate GFS HGT/TMP/RH/UGRD/VGRD/VVEL at
1000/975/950/925/900/875/850/800/750/700 hPa, matching ERA5's first profile
band. Pressure surfaces remain MSL evidence; site-AGL is height MSL minus
reviewed site elevation MSL, and a level below site or model terrain is
excluded. S07 uses no extrapolation: layer boundaries must be bracketed by
valid retained profile values.

Accepted formulas are component wind speed sqrt(u²+v²), meteorological
direction from atan2(-u,-v), linear vertical interpolation, endpoint lapse and
vector shear, trapezoidal height-weighted humidity, and full-rank
least-squares planes for neighbourhood pressure-gradient and divergence
∂u/∂x + ∂v/∂y. Arithmetic mean U/V precedes daily wind speed/direction.
Positive canonical CIN is aggregated with maximum, not minimum. The applied
schema correction migration records that decision.

Provider PBL/cloud base remain provider facts. Derived PBL, mixed-layer LCL,
surface buoyancy flux, and Deardorff convective velocity scale are unsupported
until their source inputs and project methods are separately accepted. VVEL,
gust, and TKE never fill those slots. S07 must emit missing/unsupported
provenance and a machine-readable reason instead of a fabricated value.

Keep the collector's 128 MiB default as a fail-closed per-command limit until
a real full-profile 11-hour inventory establishes a reviewed larger daily cap.
The next orchestration change must add a local-date/window option that derives
the eleven UTC valid-at values in one run; it must not use a cross-run
assembler or parallel requests merely to evade the cap.

**Consequences:** S07 receives a source-neutral, sufficiently dense vertical
profile and has exact, constrained formulas and missingness behavior. The
remaining work is implementation of the feature artifact contract, builder,
and daily collection orchestration; it is not another database redesign.

**Related files:** [`T-018-S07-implementaion-plan.md`](T-018-S07-implementaion-plan.md),
[`profile.py`](../services/ml/src/paragliding_forecasts_ml/ingestion/gfs/profile.py),
[`weather-validation-policy.json`](../services/ml/src/paragliding_forecasts_ml/ingestion/weather/resources/weather-validation-policy.json).

### DEC-041 - Correct the common GFS S07 profile source contract

**Status:** Accepted

**Date:** 2026-09-09

**Supersedes:** The GFS profile-band and mean-wind-speed wording in DEC-040.

**Context:** DEC-040 required 875 hPa in the common
`gfs.tCCz.pgrb2.0p25.fFFF` object. The official NOAA f003 inventory does not
publish the required HGT/TMP/RH/UGRD/VGRD/VVEL messages at 875 hPa in that
object, so the existing selector fails closed before collection. Its 700 hPa
ceiling also cannot conservatively promise a 3000 m site-AGL boundary at all
reviewed Bulgarian sites.

**Decision:** Keep one GFS `pgrb2.0p25` object per valid instant; do not join
`pgrb2b` merely to obtain 875 hPa. Ignore 875 hPa and require the ordered
profile pressure grain
`1000/975/950/925/900/850/800/750/700/650/600/550/500 hPa` for the current
HGT/TMP/RH/UGRD/VGRD/VVEL GFS profile inputs. The 500 hPa top is conservative
bracketing evidence for the fixed 1500 and 3000 m AGL feature boundaries, not
a new daily pressure-band feature.

The source-aware validation policy records the same profile pressure grain for
both registered source contracts so a source-neutral S07 build has one required
vertical shape. This slice changes only the implemented GFS collector/parser/
normalizer path; the future ERA5 adapter must supply that already-declared
shape through its own source implementation.

Version the changed immutable boundaries: GFS collector `gfs-collector/3`,
parser `gfs-parser/3`, numeric GRIB profile
`noaa-gfs-grib2-table-v2`, normalizer `gfs-normalizer/3`, validation policy
`source-aware-weather-validation-policy/2`, and validator
`source-aware-weather-validator/3`. This preserves prior artifact boundaries
and causes changed upstream evidence to be explicitly superseded rather than
rewritten.

For daily wind semantics, mean U/V produces only the resultant direction.
`wind_speed_*_mean_m_s` is the arithmetic time/height mean of scalar
`hypot(u, v)`, not `hypot(mean(u), mean(v))`; the separately stored component
means retain the resultant-vector information.

**Consequences:** Selector, numeric parser identity, canonical normalization,
spatial input, source validation, fixtures, and tests use one 13-level
contract and reject 875 hPa. A source artifact that lacks a required level is
quarantined or reported as the existing explicit below-terrain missing state;
no level is substituted or extrapolated. No database migration is needed for
this source-contract correction.

The next source-input checkpoint still has to add direct 2 m and
pressure-level SPFH, and verify/pin SHTFL/LHTFL interval/sign metadata before
S07 uses those accepted feature inputs. It must not infer either quantity from
other fields.

**Evidence:** [NOAA GFS pgrb2.0p25 f003 inventory](https://www.nco.ncep.noaa.gov/pmb/products/gfs/gfs.t00z.pgrb2.0p25.f003.shtml)
shows 500--650 hPa HGT/TMP/RH/SPFH/VVEL/UGRD/VGRD and no 875 hPa entries;
its surface section identifies 2 m SPFH and `SHTFL`/`LHTFL` as interval-average
fluxes.

**Related files:** [`profile.py`](../services/ml/src/paragliding_forecasts_ml/ingestion/gfs/profile.py),
[`inventory.py`](../services/ml/src/paragliding_forecasts_ml/ingestion/gfs/inventory.py),
[`weather-validation-policy.json`](../services/ml/src/paragliding_forecasts_ml/ingestion/weather/resources/weather-validation-policy.json),
[`T-018-S07-implementaion-plan.md`](T-018-S07-implementaion-plan.md),
[`handoff.md`](handoff.md).

### DEC-042 - Activate audited S07 humidity and turbulent-flux inputs

**Status:** Accepted

**Date:** 2026-09-09

**Context:** DEC-041 corrects the available common-object vertical band, but
S07 still requires direct 2 m and pressure-level specific humidity plus
validated sensible/latent heat-flux intervals. The pre-S07 catalogue and daily
schema also retained four unaccepted derived field families and their five
unused daily columns.

**Decision:** Collect GFS `SPFH` at 2 m and at every DEC-041 pressure level.
Normalize both as direct `specific_humidity_kg_per_kg` evidence, retaining the
2 m `dimension` as `2m_above_ground` and profile `pressure_pa`; neither form is
derived from temperature, relative humidity, or pressure. Require the direct 2
m field and the profile field in the source-aware policy for both source
contracts. The S09 ERA5 adapter remains responsible for providing the same
canonical inputs through its separately specified source-normalization method.

Collect GFS `SHTFL` and `LHTFL` at surface only for lead hours at least one.
Their GRIB statistic must be an interval average; retain their verified
upward-positive GFS sign as canonical upward-positive W/m² interval evidence.
They populate distinct sensible and latent heat-flux inputs. Do not calculate
the removed kinematic buoyancy flux or Deardorff convective velocity scale.

The active catalogue is `t017-spike-v2`: it admits the `unsupported` quality
state with null native/canonical value invariants and removes
`derived_boundary_layer_height_agl_m`, `mixed_layer_lcl_agl_m`,
`surface_buoyancy_flux_kinematic_k_m_s`, and
`convective_velocity_scale_m_s`. Spatial sampling preserves `unsupported` as
null evidence rather than converting it into a real value.

Add nullable hourly `specific_humidity_2m_kg_per_kg` with a `[0,1]` SQLite
constraint. Remove the unused daily
`mixed_layer_lcl_agl_{mean,max}_m`,
`surface_buoyancy_flux_kinematic_mean_k_m_s`, and
`convective_velocity_scale_{mean,max}_m_s` columns through the reviewed
forward-only migration `20260909123754_correct_s07_feature_inputs`; never edit
an applied migration.

Version the changed immutable boundaries: GFS collector `gfs-collector/4`,
parser `gfs-parser/4`, numeric GRIB profile
`noaa-gfs-grib2-table-v3`, normalizer `gfs-normalizer/4`, spatial sampler
`weather-spatial/3`, policy
`source-aware-weather-validation-policy/3`, and validator
`source-aware-weather-validator/4`.

**Consequences:** A source artifact now has the direct humidity anchors and
verified flux intervals that S07 needs, while unsupported values stay explicit
null evidence. The forward migration is approved and covered by fresh-db,
idempotence, strict-table, foreign-key, and constraint tests. Applying it to a
non-test local database remains an explicit owner-authorized operation because
it drops the five legacy daily columns.

**Evidence:** [NOAA GFS pgrb2.0p25 f003 inventory](https://www.nco.ncep.noaa.gov/pmb/products/gfs/gfs.t00z.pgrb2.0p25.f003.shtml)
identifies `SPFH` at 2 m and across the retained pressure band, and `SHTFL` /
`LHTFL` as surface average fields.

**Related files:** [`inventory.py`](../services/ml/src/paragliding_forecasts_ml/ingestion/gfs/inventory.py),
[`normalizer.py`](../services/ml/src/paragliding_forecasts_ml/ingestion/gfs/normalizer.py),
[`weather-validation-policy.json`](../services/ml/src/paragliding_forecasts_ml/ingestion/weather/resources/weather-validation-policy.json),
[`schema.ts`](../packages/database/src/schema.ts),
[`migration.sql`](../packages/database/drizzle/20260909123754_correct_s07_feature_inputs/migration.sql),
and [`handoff.md`](handoff.md).

### DEC-043 - Remove unrequired S07 resolved-inversion metrics

**Status:** Accepted

**Date:** 2026-09-09

**Context:** The preliminary S07 plan and daily profile-layer schema contained
`inversion_strength_max_k` and `inversion_depth_at_max_m`. These are model-level
derivations from temperature and height profiles, not GPS or provider fields.
They are not a project-brief requirement and have no accepted ML or prediction
use. Their specialised detection method would add an unneeded second stability
metric alongside the accepted lapse-rate and humidity profiles.

**Decision:** Do not calculate, emit, catalogue, persist, or train on resolved
inversion strength or depth in S07. Retain the accepted lapse-rate and humidity
profile features as the S07 stability evidence. Remove both daily
profile-layer columns and their paired SQLite constraint with the reviewed
forward-only migration `20260909165706_remove_s07_inversion_metrics`; do not
edit any applied migration.

**Consequences:** The S07 vertical helper and test coverage exclude inversion
run detection. Existing databases require the named forward migration before
S08 persistence can rely on the cleaned profile-layer shape. No source
collector, parser, normalizer, hourly sample, or field-catalogue change is
required because these metrics were never raw canonical fields.

**Related files:** [`T-018-S07-implementaion-plan.md`](T-018-S07-implementaion-plan.md),
[`schema.ts`](../packages/database/src/schema.ts),
[`migration.sql`](../packages/database/drizzle/20260909165706_remove_s07_inversion_metrics/migration.sql),
and [`handoff.md`](handoff.md).

### DEC-044 - Bind daily GFS collection to the Sofia flying-window policy

**Status:** Accepted

**Date:** 2026-09-10

**Context:** The approved S07 feature contract is one `Europe/Sofia` local
10:00--20:00 day, but the prior GFS collector exposed only repeatable raw UTC
`--valid-at` arguments. This made the required DST conversion an error-prone
caller responsibility and permitted accidental incomplete/cross-window runs.

**Decision:** `gfs-collect --local-date YYYY-MM-DD` is the daily operational
mode. It is mutually exclusive with low-level `--valid-at`, derives exactly the
eleven Sofia 10:00--20:00 instants through IANA `zoneinfo`, and records
`target_local_date` plus `sofia-flying-window/1` in request/resolved-plan
provenance. The resolved-plan local-date shape is schema v2 and the collector
is versioned as `gfs-collector/5`; existing schema-v1 explicit-UTC plans remain
readable. One local day stays in one selected GFS cycle/run.

**Consequences:** DST conversion cannot be silently supplied by callers.
The 128 MiB default remains fail-closed; no larger default is inferred here.
The bounded 2026-09-10 inventory check for local date `2026-09-11` resolved
the `2026-09-10T00:00:00Z` GFS cycle, selected 594 ranges, and measured
`1,168,112,596` bytes (`1114 MiB` minimum), with no payload download or
artifact write. `--maximum-total-mib 1114` is therefore reviewed only for
that exact replay scope; every new scope needs its own bounded measurement.

**Related files:** [`cli.py`](../services/ml/src/paragliding_forecasts_ml/ingestion/gfs/cli.py),
[`models.py`](../services/ml/src/paragliding_forecasts_ml/ingestion/gfs/models.py),
[`planner.py`](../services/ml/src/paragliding_forecasts_ml/ingestion/gfs/planner.py),
and [`README.md`](../services/ml/README.md).

### DEC-045 - GFS interval products are normalized to exact adjacent UTC windows

**Status:** Accepted

**Date:** 2026-09-10

**Decision:**

- Keep provider interval metadata (`startStep`, `endStep`, and step type)
  as the authority for GFS accumulated and averaged fields.
- Normalize accumulated fields such as total precipitation by subtracting
  two values with the same accumulation anchor.
- Normalize averaged fluxes such as downward short-wave, sensible-heat, and
  latent-heat flux by subtracting their time integrals and dividing by the
  requested adjacent interval duration.
- Treat a valid numeric zero after normalization as observed information,
  not as missing data.
- Use the `[09:00, 10:00)` value only when needed as a boundary baseline;
  the daily flying-window aggregate remains exactly `[10:00, 20:00)` local.
- Stop requesting GFS gust because it has no accepted feature, persistence,
  or model use in the current contract.
- Rationale:
  - GFS may encode forecast-hour 32 as an accumulation or average over
    forecast hours 30-32 rather than only 31-32. Treating that value as a
    one-hour quantity biases precipitation and energy-flux features.
  - Exact interval reconstruction makes fresh and offline replay deterministic
    and keeps temporal semantics explicit.

### DEC-046 - Weather persistence is immutable, atomic, and artifact-replayable

**Status:** Accepted

**Date:** 2026-09-10

**Decision:**

- Python owns weather DML but never creates or migrates schema. It may write
  only to a database already migrated by the committed Drizzle migrations.
- Persist the complete weather graph in one `BEGIN IMMEDIATE` transaction
  and mark the run `succeeded` last. Any failure rolls back the entire
  graph, so no partially succeeded run is visible.
- Identify an acquisition by its natural run key and immutable input
  fingerprint. Replaying an exact persisted run fully revalidates the stored
  graph and is a no-op; any mismatch is an explicit conflict and never an
  overwrite.
- Enrichment is append-only under a new feature-contract or replay run;
  provider revisions use a new source/product run identity. An existing null
  becoming a value under the same immutable identity is a conflict, not an
  in-place patch.
- Preserve expected missing values as SQL `NULL` with field-level
  provenance and a reason code. Unsupported fields are absent from the
  active contract and selector rather than stored as perpetually missing
  metrics.
- `weather-ingest resume` is artifact-only: it must neither instantiate a
  network transport nor make a source request. Verified raw/interim artifacts
  may rebuild derived stages and restore database writes into another freshly
  migrated database.
- GFS provider cloud base remains explicitly unsupported. Add a separately
  named mixed-layer LCL estimate and PBL-minus-LCL gap, plus physically
  derived surface buoyancy flux and convective velocity scale. Remove lower
  layer omega from the feature contract while retaining upper-layer omega and
  the shared persistence columns required to store it.
- Rationale:
  - The policy prevents silent data mutation and duplicate training examples,
    makes recovery independent of another large GFS download, and preserves the
    distinction between provider observations, physical estimates, and missing
    information.

### DEC-047 - Supply weather usage authority through an explicit local policy file

**Status:** Accepted

**Date:** 2026-09-11

**Context:** `weather_ingestion_runs` requires explicit, non-null
`model_training_allowed` and `operational_use_allowed` values. Existing GFS
raw/request artifacts preserve the source permission basis and reference but
do not carry those owner-authorized usage flags. Inferring or hard-coding either
boolean would make an immutable replay appear authorized without evidence.

**Decision:** Follow the established XCContest persistence boundary, scoped by
weather source. By default `weather-persist` resolves local
`data/local/gfs-usage-policy.json` for a GFS run and
`data/local/era5-usage-policy.json` for an ERA5 run. An optional
`--policy-file` override is permitted only when its strict source-specific
schema matches the run: `gfs_usage_policy_schema_version` for GFS or
`era5_usage_policy_schema_version` for ERA5, plus `permission_basis`,
`permission_reference`, `model_training_allowed`, and
`operational_use_allowed`. The adapter hashes the exact selected file bytes
into the persistence input fingerprint and writes its asserted values to the
terminal weather ingestion run. The policy file is local operator authority,
not a replacement for the source raw manifest; the raw source basis/reference
and attribution stay preserved from immutable collection evidence.

The command does not download, alter, or recreate raw artifacts. Replaying a
run with changed policy bytes is an immutable-input conflict, even if the
booleans happen to be the same. Future fresh and resume orchestration must
forward this explicit policy path; no default policy or inferred source-wide
permission flags are allowed.

**Consequences:** Existing retained raw runs can be persisted offline once an
owner supplies the reviewed local policy file. Final production attribution,
retention, and source terms remain an open release decision; this boundary
records the local usage authority actually used for one immutable persistence
run.

**Related files:** [`persistence_models.py`](../services/ml/src/paragliding_forecasts_ml/ingestion/weather/persistence_models.py),
[`persistence.py`](../services/ml/src/paragliding_forecasts_ml/ingestion/weather/persistence.py),
[`persistence_cli.py`](../services/ml/src/paragliding_forecasts_ml/ingestion/weather/persistence_cli.py),
and [`handoff.md`](handoff.md).
### DEC-048 - Resolve feature inputs by exact centralized canonical selectors

**Status:** Accepted

**Date:** 2026-09-12

**Decision:** Weather feature construction resolves every source-backed point,
profile-surface-anchor, thermodynamic, and neighbourhood input through one
central selector registry. A selector matches exactly on canonical `field_code`,
`grain`, and `dimension`; zero matches remain feature-local missing evidence,
while duplicate exact matches or an unmapped source-backed policy identity are
build errors. It never falls back to dimensionless or source-specific inputs.

The schema-v2 `weather-feature-policy-v3` keeps feature contract `/3` and
snapshot/report schemas unchanged, but declares `weather-feature-builder/3`.
The policy supplies the stage producer version, so the feature stage directory,
fingerprint, manifest, and configuration cannot drift from the loaded policy.
Prior v1/v2 policies and their immutable artifacts remain parseable and
untouched. This correction does not alter the accepted GFS terrain policy or
any SQLite persistence mapping.

**Consequences:** Canonical `2m_above_ground`, `10m_above_ground`, surface,
mean-sea-level, cloud, and surface-parcel convection identities are selected
without ambiguity. The v3 build creates a new immutable boundary and supersedes
the v2 ledger event; it does not rewrite prior artifacts. GFS provider cloud
base remains `unsupported/source_field_unavailable`.
## Open decisions

| Question                                                                                                                  | Options / constraints                                                                                                                                                                                                             | Resolve by                                                               |
| ------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| Which task owns the persisted prediction schema and SQLite forecast adapter?                                              | The backlog has flight and weather schema tasks but no explicit owner for storing T-022-T-024 outputs and replacing the T-002 mock adapter. Public units/status/provenance must be mapped deliberately.                           | Backlog planning before real predictions are connected to the API.       |
| What are the final coordinates, aliases, and catchment radii for each site?                                               | Current map points are provisional; Pastrina and the Dobrich regional model need particular confirmation.                                                                                                                         | T-009.                                                                   |
| What retention, attribution, licensing, and rate limits apply beyond the current XCContest browser workflow?              | T-013 has a project-owner-confirmed ordinary low-volume UI workflow; do not extend it to bulk/commercial use or SkyNomad without explicit terms.                                                                                  | Before broader collection or product use.                                |
| What final production attribution, retention, and archive-operation wording is required for the selected weather sources? | T-018 uses direct NOAA GFS and CDS ERA5. Preserve source/permission evidence for both and the applicable Copernicus/ECMWF attribution for ERA5; confirm final product wording and retention operations before commercial release. | Before a commercial release.                                             |
| Which first alert channel should be implemented?                                                                          | Dashboard watchlist, email, Telegram, or another agreed channel; alerts require at least one-day lead time and deduplication.                                                                                                     | T-027/T-028.                                                             |
| What deployment/distribution model is required beyond local development?                                                  | The MVP is local-first; cloud/distributed infrastructure needs a demonstrated requirement.                                                                                                                                        | No task assigned; decide when deployment becomes an accepted scope item. |
| What license should the repository use?                                                                                   | No open-source license is currently selected.                                                                                                                                                                                     | Repository owner decision; no task assigned.                             |
