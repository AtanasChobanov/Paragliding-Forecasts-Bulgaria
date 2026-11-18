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

T-025 connects the operational GFS 06Z publications in SQLite to the React
home dashboard and detailed site/date view through the Express API. The final
detail iteration is awaiting owner review. See [the backlog](docs/tasks.md) and [handoff](docs/handoff.md) for the
current ticket and verification status.

## Current dashboard

Choose a location and one of five Sofia calendar dates. The dashboard shows
100+/200+/300+ km chances, cloudbase or conditional LCL in metres MSL, and
overdevelopment risk. Published predictions carry the `baseline` status with
per-metric confidence and limitations. Use the information button on each card
to inspect the source cycle, publication time, horizon and model versions.
Dates without a publication are disabled. Reload the page to see newly
published forecasts or update the five-day window after Sofia midnight.

Available cards link to `/forecast?site=<slug>&date=YYYY-MM-DD` in both modes.
Detail shows all 67 XC inputs, metric-specific published drivers and eleven
cloudbase hours with distinct regimes and height references. Panels paginate
within one viewport. The information buttons identify synthetic data in
explicit `mock` mode.

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

The T-023 offline XC training and prediction workflow and owner-run checkpoints
are documented in the [ML service README](services/ml/README.md#prepare-the-frozen-development-study).

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
npm.cmd run db:migrate --workspace @paragliding-forecasts/database
```

For a lockfile-exact JavaScript install, use `npm.cmd ci`. On macOS/Linux, use
`npm` and `cp .env.example .env`. npm manages only the TypeScript workspaces;
uv manages only `services/ml`.

For a new macOS/Linux machine, use the [ML environment and fresh-start
instructions](services/ml/README.md#environment-setup), including the ecCodes
native-library self-check and VS Code interpreter selection. A newly migrated
empty database supports new GFS ingestion; old prediction run keys require
their original retained data.

For local GFS 06Z publication to SQLite and operational GRIB retention, use
the [forecast publication workflow](services/ml/README.md#publish-and-retain-operational-forecasts-t-025).

## Run the API

Start watch mode from the repository root:

```powershell
npm.cmd run dev:api
```

The default address is `http://127.0.0.1:3000`. SQLite mode requires a migrated
database at `DATABASE_URL`. A migrated database with no forecast publications
returns the site catalog and unavailable dates. Available endpoints are:

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

```sh
FORECAST_DATA_MODE=sqlite npm run dev
```

Open `http://localhost:5173`. If a local `.env` still sets
`FORECAST_DATA_MODE=mock`, the command above overrides it for this session.
For future runs, set `FORECAST_DATA_MODE=sqlite` in `.env` and use
`npm run dev`. In PowerShell, use
`$env:FORECAST_DATA_MODE = "sqlite"; npm.cmd run dev`.

Use `FORECAST_DATA_MODE=mock npm run dev` for synthetic demo forecasts. To start only Vite, use `npm run dev:web` and keep the API running
at the configured `VITE_API_BASE_URL`.

## Commands

| Command                                                                                             | Purpose                                                                                            |
| --------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| `npm run dev`                                                                                       | Supervise the API and web development servers together                                             |
| `npm run dev:api`                                                                                   | Build the contracts and database workspaces and start the API watcher                                             |
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
| `uv run --project services/ml flight-label-audit`                                                    | Audit repaired 2022–2025 site-day labels offline; emit hashed local JSONL outputs                    |

## Run browser smoke tests

After `npm.cmd install`, download the matching Chromium binary once:

```powershell
npm.cmd run test:browser:install
npm.cmd run test:browser
```

Playwright runs separate mock and SQLite fixtures. The test API ports are
`3300` and `3301`. The test web ports are `5373` and `5374`. The SQLite
project migrates a disposable database and verifies November 17–19 forecast
selection, metadata, layout and map labels with the tile requests intercepted.
Both projects exercise detail navigation. SQLite detail also covers responsive
layout, metric explanations, hourly regimes, keyboard/touch and manual refresh.
Use `test:browser:headed` to watch Chromium or `test:browser:ui` to debug.

## Configuration and data

Copy `.env.example` to `.env` for local overrides. Vite consumes `WEB_PORT` and
the browser-exposed `VITE_API_BASE_URL`; the latter is validated as an absolute
HTTP(S) URL before React renders. If `WEB_PORT` changes, `CORS_ORIGIN` must use
the same dashboard origin. The API consumes `NODE_ENV`, `LOG_LEVEL`, `API_HOST`,
`API_PORT`, `CORS_ORIGIN`, `FORECAST_DATA_MODE`, and `DATABASE_URL`.
The SQLite default is `file:./data/local/paragliding.db`. The path must be
repository-relative under `data/`. See the
[API setup](apps/api/README.md#configuration) for startup errors and mode
behavior.

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
