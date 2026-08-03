# Paragliding Forecasts Bulgaria

Local-first decision-support software for identifying promising paragliding
cross-country (XC) days in Bulgaria. The product will combine forecast and
atmospheric features with evidence from historical flights, then present the
result as an inspectable daily dashboard.

> **Safety:** this project is planning support, not an aviation weather service
> and not a guarantee that a day is safe or flyable. Pilots remain responsible
> for official weather checks, airspace, site rules, equipment, and personal
> decisions.

## Project status

- Delivery phase: **Takt 2**
- Current ticket: **T-012 - Implement flight record schema** (`Review`)
- Next ticket: **T-013 - Ingest first validated flight sample** (`To Do`;
  requires a permitted XCContest input/export method)
- Implemented: runnable React/Vite and Node.js/Express workspaces, shared runtime
  contracts, structured logging and errors, a map-ready seven-site catalog,
  deterministic date-aware mock forecasts, dashboard summary/day-preview read
  endpoints, canonical URL selection, forecast overview/comparison cards, an
  interactive Leaflet site selector, a fixed five-day selector, scoped
  accessible request states, and a routed detailed site/date forecast view with
  mock forecast inputs/drivers, and Playwright Chromium smoke coverage for the
  dashboard-to-detail happy path; and a Drizzle-owned SQLite flight-data
  foundation with reviewed, reproducible migrations
- Not implemented: data ingestion, API persistence integration, real forecasts, models, and alerts

Displayed mock responses are deliberately identified as `mock`; they are
development fixtures, not forecasts or flying advice.

## Current dashboard

The dashboard lets a user choose a forecast date and one of the initial
Bulgarian areas: Sofia - Vitosha (Kominite), Zlatitsa, Sopot, Nevsha, Shumen,
Pastrina, or the Dobrich region. It shows cloudbase, chances for 100+ km,
200+ km, and 300+ km flights, and overdevelopment risk. Every value is labelled
as `mock`, `manual`, `baseline`, `real`, or `missing`. Its detailed action and
each Other Locations card open `/forecast?site=<slug>&date=YYYY-MM-DD`. The
detail view exposes all five output values with their own confidence/status,
mock weather inputs and drivers, and a static previous-run placeholder until
real model runs exist.

## Repository layout

```text
.
|-- apps/
|   |-- web/                 # React dashboard boundary (T-003 onward)
|   `-- api/                 # Runnable Express HTTP API
|-- packages/
|   |-- contracts/           # Shared runtime schemas and TypeScript contracts
|   `-- database/            # Drizzle schema, migrations, and SQLite boundary
|-- services/
|   `-- ml/                  # Python data/ML workflows managed with uv
|-- data/                    # Local data zones; generated data is ignored
|-- docs/                    # Architecture, decisions, tasks, and handoff
|-- scripts/                 # Repository-level validation
|-- .env.example             # Safe, non-secret configuration template
|-- package.json             # npm workspace root and commands
`-- tsconfig.base.json       # Shared TypeScript compiler defaults
```

Each subproject owns its local responsibilities, commands, configuration, and
test notes in its README. Cross-project information belongs here or in `docs/`.

## Technology direction

| Area                | Choice                                                                       | Current state                                                                  |
| ------------------- | ---------------------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| Web                 | React + Vite + TypeScript, Router, TanStack Query, SCSS Modules, and Leaflet | Dashboard and browser smoke coverage completed                                 |
| API                 | Node.js + Express + TypeScript                                               | Runnable with dashboard read endpoints                                         |
| Shared contracts    | TypeScript + Zod                                                             | Runtime schemas and inferred types implemented                                 |
| Data and ML         | Python managed by `uv`                                                       | Project boundary only                                                          |
| MVP storage         | SQLite + Drizzle                                                             | Flight foundation and migration boundary implemented; API integration deferred |
| JavaScript packages | npm workspaces                                                               | One root lockfile and install                                                  |

Python is deliberately limited to ingestion, weather-feature engineering,
experiments, training, backtesting, and batch prediction work that benefits
from the scientific Python ecosystem.

## Prerequisites

- Git
- Node.js 24.x
- npm 11.x (included with Node.js)
- [`uv`](https://docs.astral.sh/uv/getting-started/installation/) for the future
  Python data/ML workflows

On Windows PowerShell, use `npm.cmd` if execution policy blocks `npm.ps1`.

## Initial setup

```powershell
git clone https://github.com/AtanasChobanov/Paragliding-Forecasts-Bulgaria.git
Set-Location Paragliding-Forecasts-Bulgaria

npm.cmd install
uv sync --project services/ml
Copy-Item .env.example .env
npm.cmd run repo:check
```

For a lockfile-exact JavaScript install, use `npm.cmd ci`. On macOS/Linux, use
`npm` and `cp .env.example .env`. npm manages only the TypeScript workspaces;
uv manages only `services/ml`.

## Run the API

Start watch mode from the repository root:

```powershell
npm.cmd run dev:api
```

The default address is `http://127.0.0.1:3000`. Available endpoints are:

```text
GET /health
GET /api/v1/sites
GET /api/v1/forecasts?siteSlug=sopot&date=YYYY-MM-DD
GET /api/v1/forecasts/summaries?date=YYYY-MM-DD&siteSlugs=sopot,zlatitsa
GET /api/v1/forecasts/days?siteSlug=sopot
```

The summary route supplies one or several dashboard cards for a selected date.
The days route always supplies the five Sofia-calendar slots from today minus
two days through today plus two days; it has no pagination or date-navigation
parameters. During mock development, use one of its returned `forecastDate`
values for an available detailed/summary example. See
[`apps/api/README.md`](apps/api/README.md) for the exact missing-data and
mock-snapshot behavior.

Build and run the compiled server with:

```powershell
npm.cmd run start:api
```

See [`apps/api/README.md`](apps/api/README.md) for request, configuration,
error, and data limitations.

## Run web development

Start the API and web development servers together:

```powershell
npm.cmd run dev
```

The dashboard origin is `http://localhost:5173` by default. To run only the
React/Vite workspace, use `npm.cmd run dev:web`; keep the API running at the
configured `VITE_API_BASE_URL` to load dashboard data.

## Commands

| Command                                                                                             | Purpose                                                                                            |
| --------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| `npm run dev`                                                                                       | Supervise the API and web development servers together                                             |
| `npm run dev:api`                                                                                   | Build shared contracts and start the API in watch mode                                             |
| `npm run dev:web`                                                                                   | Start Vite on the configured strict web port                                                       |
| `npm run start:api`                                                                                 | Build contracts/API and start compiled JavaScript                                                  |
| `npm run build`                                                                                     | Build database, contracts, API, and the production web bundle                                      |
| `npm run typecheck`                                                                                 | Type-check database, contracts, API, and web workspaces                                            |
| `npm run lint`                                                                                      | Build shared contract declarations, then lint TypeScript/TSX sources and tests, including database |
| `npm run format:check`                                                                              | Check maintained TypeScript, TSX, HTML, SCSS, and config formatting                                |
| `npm test`                                                                                          | Run database, contract, API, and web unit/integration/component tests                              |
| `npm run test:coverage`                                                                             | Run all four suites with V8 coverage and enforced thresholds                                       |
| `npm run test:browser:install`                                                                      | Download the Playwright Chromium binary once per machine/version                                   |
| `npm run test:browser`                                                                              | Run the dashboard and detail-page Chromium smoke suite headlessly                                  |
| `npm run test:browser:headed`                                                                       | Run the same browser smoke suite with visible Chromium                                             |
| `npm run test:browser:ui`                                                                           | Open Playwright UI mode for interactive browser-test debugging                                     |
| `npm run db:generate --workspace @paragliding-forecasts/database -- --name <lower_snake_case_name>` | Generate a database migration for SQL review                                                       |
| `npm run db:check --workspace @paragliding-forecasts/database`                                      | Check Drizzle schema and committed migration metadata                                              |
| `npm run db:migrate --workspace @paragliding-forecasts/database`                                    | Apply reviewed committed migrations to the configured local SQLite file                            |
| `npm run repo:check`                                                                                | Validate repository structure and runnable workspace metadata                                      |
| `uv sync --project services/ml`                                                                     | Sync the Python ML environment                                                                     |

## Run browser smoke tests

After `npm.cmd install`, download the matching Chromium binary once:

```powershell
npm.cmd run test:browser:install
npm.cmd run test:browser
```

The smoke suite starts the compiled local API and Vite dashboard on the normal
`3000` and `5173` ports, so stop a local development session first. The default
command is headless; use `test:browser:headed` to watch Chromium or
`test:browser:ui` to inspect and re-run tests interactively. It verifies the
dashboard's five required forecast outputs, then follows the detailed-forecast
link and confirms its outputs, inputs, drivers, and return navigation. It is a
browser end-to-end smoke test, not a visual-regression suite.

## Configuration and data

Copy `.env.example` to `.env` for local overrides. Vite consumes `WEB_PORT` and
the browser-exposed `VITE_API_BASE_URL`; the latter is validated as an absolute
HTTP(S) URL before React renders. If `WEB_PORT` changes, `CORS_ORIGIN` must use
the same dashboard origin. The API consumes `NODE_ENV`, `LOG_LEVEL`, `API_HOST`,
`API_PORT`, `CORS_ORIGIN`, and `FORECAST_DATA_MODE=mock`.

The API starts with safe defaults when `.env` is absent.
The logger defaults to `info`; `.env.example` opts local development into
`debug` explicitly.
`DATABASE_URL` and `MODEL_ARTIFACT_DIR` are reserved for future persistence and
model work and are not read by the current API.

Never commit `.env`, credentials, private pilot data, large weather files,
trained model artifacts, generated output, or local databases. See
[`data/README.md`](data/README.md) for the controlled fixture exception.

## Documentation map

- [`docs/architecture.md`](docs/architecture.md) - boundaries and data flow
- [`docs/decisions.md`](docs/decisions.md) - accepted choices and open decisions
- [`docs/development.md`](docs/development.md) - setup and engineering workflow
- [`docs/tasks.md`](docs/tasks.md) - task backlog and status
- [`docs/handoff.md`](docs/handoff.md) - current operational snapshot
- [`apps/api/README.md`](apps/api/README.md) - API operation and design
- [`apps/web/README.md`](apps/web/README.md) - dashboard behavior, setup, tests, and limitations
- [`packages/contracts/README.md`](packages/contracts/README.md) - public payload rules
- [`services/ml/README.md`](services/ml/README.md) - Python/ML boundary
- [`CONTRIBUTING.md`](CONTRIBUTING.md) - branch, commit, and review conventions

## Delivery and definition of done

Work is delivered in two-week Takts. A ticket is done only when its behavior is
reproducible from a clean checkout, relevant assumptions and data status are
documented, appropriate checks pass, and known limitations are recorded.

## License

No open-source license has been selected yet. Add one only after the repository
owner makes an explicit licensing decision.
