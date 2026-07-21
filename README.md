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

- Delivery phase: **Takt 1**
- Current tickets: **T-003-T-005 - Dashboard, site selector, and date selector**
  (`In Progress`)
- Implemented: a runnable Node.js/Express/TypeScript API, shared runtime
  contracts, structured logging and errors, a map-ready seven-site catalog,
  deterministic date-aware mock forecasts, and dashboard summary/day-preview
  read endpoints
- Not implemented: the React dashboard, SQLite schema or access layer, data
  ingestion, real forecasts, models, and alerts

Mock responses are deliberately identified as `mock`; they are development
fixtures for the upcoming dashboard, not forecasts or flying advice.

## Planned MVP

The first dashboard will let a user choose a forecast date and one of the
initial Bulgarian areas: Sofia - Vitosha (Kominite), Zlatitsa, Sopot, Nevsha,
Shumen, Pastrina, or the Dobrich region. It will show cloudbase, chances for
100+ km, 200+ km, and 300+ km flights, and overdevelopment risk. Every value
must be labelled as `mock`, `manual`, `baseline`, `real`, or `missing`.

## Repository layout

```text
.
|-- apps/
|   |-- web/                 # React dashboard boundary (T-003 onward)
|   `-- api/                 # Runnable Express HTTP API
|-- packages/
|   `-- contracts/           # Shared runtime schemas and TypeScript contracts
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

| Area | Choice | Current state |
| --- | --- | --- |
| Web | React + Vite + TypeScript | Scaffold present; dashboard implementation pending |
| API | Node.js + Express + TypeScript | Runnable with dashboard read endpoints |
| Shared contracts | TypeScript + Zod | Runtime schemas and inferred types implemented |
| Data and ML | Python managed by `uv` | Project boundary only |
| MVP storage | SQLite | Direction accepted; schema and access layer deferred |
| JavaScript packages | npm workspaces | One root lockfile and install |

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

## Commands

| Command | Purpose |
| --- | --- |
| `npm run dev:api` | Build shared contracts and start the API in watch mode |
| `npm run start:api` | Build contracts/API and start compiled JavaScript |
| `npm run build` | Build shared contracts, then the API |
| `npm run typecheck` | Type-check contracts and API |
| `npm run lint` | Build shared contract declarations, then lint TypeScript sources and tests |
| `npm run format:check` | Check maintained TypeScript/config formatting |
| `npm test` | Run contract and API unit/integration/smoke tests |
| `npm run test:coverage` | Run the same suites with V8 coverage and enforced thresholds |
| `npm run repo:check` | Validate repository structure and runnable workspace metadata |
| `uv sync --project services/ml` | Sync the Python ML environment |

`npm run dev:web` and the combined `npm run dev` are not runnable yet; the
React portion of T-003-T-005 must add and document their real behavior.

## Configuration and data

Copy `.env.example` to `.env` for local overrides. The API currently consumes
only `NODE_ENV`, `LOG_LEVEL`, `API_HOST`, `API_PORT`, `CORS_ORIGIN`, and
`FORECAST_DATA_MODE=mock`. It starts with safe defaults when `.env` is absent.
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
