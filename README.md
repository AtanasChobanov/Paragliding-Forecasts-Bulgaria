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
- Current ticket: **T-001 - repository and README scaffold**
- Implemented now: repository boundaries, package-manager configuration,
  setup notes, documentation ownership, and repository validation
- Intentionally not implemented yet: a running API (**T-002**) and the React
  dashboard (**T-003**)

Keeping those boundaries explicit prevents scaffold-only placeholders from
being mistaken for working forecast functionality.

## Planned MVP

The first dashboard will let a user choose a forecast date and one of the
initial Bulgarian areas: Sofia - Vitosha (Kominite), Zlatitsa, Sopot, Nevsha,
Shumen, Pastrona, or the Dobrich region. It will show cloudbase, chances for
100+ km, 200+ km, and 300+ km flights, and overdevelopment risk. Every value
must be labelled as mock, manual, baseline, real, or unavailable.

## Repository layout

```text
.
|-- apps/
|   |-- web/                 # React + TypeScript dashboard (T-003 onward)
|   `-- api/                 # Node.js + Express + TypeScript API (T-002 onward)
|-- packages/
|   `-- contracts/           # Shared TypeScript API contracts and schemas
|-- services/
|   `-- ml/                  # Python data/ML workflows managed with uv
|-- data/                    # Local data zones; generated data is ignored
|-- docs/                    # Architecture and developer setup notes
|-- scripts/                 # Repository-level automation
|-- .env.example             # Safe, non-secret configuration template
|-- package.json             # npm workspace root
`-- tsconfig.base.json       # Shared TypeScript compiler defaults
```

Each real subproject has its own README for its local responsibilities,
commands, environment variables, and test strategy. Cross-project information
belongs here or in `docs/`; it should not be copied into every README.

## Technology direction

| Area | Choice | Why |
| --- | --- | --- |
| Web | React + Vite + TypeScript | Fast local dashboard development and typed UI code |
| API | Node.js + Express + TypeScript | Keeps product/API work in TypeScript and makes boundaries explicit |
| Shared contracts | TypeScript package | One source for API request/response shapes used by web and API |
| Data and ML | Python managed by `uv` | Uses the mature scientific Python ecosystem where it adds real value |
| MVP storage | SQLite | Inspectable local storage; PostgreSQL is deferred until scale requires it |
| JavaScript packages | npm workspaces | One lockfile and one install from the repository root |

TypeScript is the default for the UI, HTTP API, and shared product contracts.
Python is deliberately limited to ingestion, weather-feature engineering,
experiments, training, and batch prediction tasks that benefit from Python's
data ecosystem.

## Prerequisites

- Git
- Node.js 24.x
- npm 11.x (included with Node.js)
- [`uv`](https://docs.astral.sh/uv/getting-started/installation/) for Python
  environment and dependency management

Python does not need to be installed separately when `uv` is allowed to manage
the version selected in `services/ml/.python-version`.

On Windows PowerShell, an execution policy may block `npm.ps1`. If that happens,
use `npm.cmd` in place of `npm`; the commands are otherwise identical.

## Initial setup

```powershell
git clone https://github.com/AtanasChobanov/Paragliding-Forecasts-Bulgaria.git
Set-Location Paragliding-Forecasts-Bulgaria

npm.cmd install
uv sync --project services/ml
Copy-Item .env.example .env
npm.cmd run repo:check
```

For macOS or Linux, use `npm` instead of `npm.cmd` and `cp .env.example .env`
instead of `Copy-Item`.

`npm install` manages only the TypeScript workspaces. `uv sync --project
services/ml` manages only the Python environment. Do not install Python
dependencies with npm or JavaScript dependencies with uv.

## Commands

### Available in T-001

| Command | Purpose |
| --- | --- |
| `npm run repo:check` | Validate the expected scaffold and workspace metadata |
| `npm install` | Install/link all npm workspaces and update `package-lock.json` |
| `uv sync --project services/ml` | Create/sync the Python ML environment |

### Reserved development commands

These are the stable command names the next tickets must implement. They are
documented now but are **not yet runnable**, because T-001 contains no fake
server or dashboard:

| Command | Introduced by | Expected result |
| --- | --- | --- |
| `npm run dev:api` | T-002 | Start the Express API in watch mode |
| `npm run dev:web` | T-003 | Start the Vite dashboard in watch mode |
| `npm run dev` | T-003 | Start web and API together for local development |
| `npm test` | T-002 onward | Run available automated checks across workspaces |

The Python README will add exact ingestion, training, and prediction commands
when those entry points exist. Commands must never pretend to succeed while
running placeholder logic.

## Configuration and data

Copy `.env.example` to `.env` for local settings. Commit changes to
`.env.example` when a new variable becomes required, but never commit `.env`,
credentials, API keys, private pilot data, large weather files, trained model
artifacts, or local databases.

See [`data/README.md`](data/README.md) for the data-zone policy. Small,
sanitized, frozen fixtures may be committed under `data/samples/` when needed
for reproducible parser tests.

## Documentation map

- [`docs/architecture.md`](docs/architecture.md) - service boundaries and data flow
- [`docs/development.md`](docs/development.md) - detailed setup and dependency workflow
- [`apps/web/README.md`](apps/web/README.md) - dashboard ownership and planned commands
- [`apps/api/README.md`](apps/api/README.md) - HTTP API ownership and planned endpoints
- [`services/ml/README.md`](services/ml/README.md) - Python/ML environment and boundaries
- [`packages/contracts/README.md`](packages/contracts/README.md) - shared contract rules
- [`CONTRIBUTING.md`](CONTRIBUTING.md) - branch, commit, and review conventions

## Delivery and definition of done

Work is delivered in two-week Takts. A ticket is done only when its behavior is
reproducible from a clean checkout, relevant assumptions and data status are
documented, appropriate checks pass, and known limitations are recorded.

## License

No open-source license has been selected yet. Add one only after the repository
owner makes an explicit licensing decision.
