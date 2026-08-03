# Development guide

## Package-manager boundaries

- Use npm from the repository root for `apps/*` and `packages/*`.
- Use uv with `--project services/ml` for Python dependencies and commands.
- Commit `package-lock.json` and `services/ml/uv.lock` after they are generated.
- Do not use Yarn, pnpm, pip requirements files, Poetry, or manually managed
  virtual environments unless the project records an explicit migration.

## Clean-checkout setup

```powershell
npm.cmd install
uv sync --project services/ml
Copy-Item .env.example .env
npm.cmd run repo:check
```

PowerShell may block `npm.ps1`; `npm.cmd` avoids that wrapper. On macOS/Linux,
use `npm` and `cp`. CI and clean-verification runs should use `npm ci` to
install exactly the committed JavaScript lockfile.

## Adding dependencies

Install JavaScript dependencies into the package that owns them:

```powershell
npm.cmd install express --workspace @paragliding-forecasts/api
npm.cmd install react --workspace @paragliding-forecasts/web
npm.cmd install zod --workspace @paragliding-forecasts/contracts
```

Install Python dependencies through uv:

```powershell
uv add --project services/ml pandas
uv add --project services/ml --dev pytest
```

Avoid adding application dependencies to the npm workspace root. Root-level
dependencies are reserved for tooling used across multiple TypeScript
workspaces.

## SQLite schema and migrations

T-012 introduces `packages/database` as the single owner of SQLite schema
declarations, Drizzle Kit generation, reviewed SQL migrations, and migration
history. Python may use the migrated SQLite file through a non-migrating
adapter; it must not create tables or use Alembic/another migration system.

The following T-012 command contract is implemented and verified:

```powershell
npm.cmd run db:generate --workspace @paragliding-forecasts/database -- --name <lower_snake_case_name>
npm.cmd run db:check --workspace @paragliding-forecasts/database
npm.cmd run db:migrate --workspace @paragliding-forecasts/database
```

Use `db:generate` to create committed SQL migration files from the Drizzle
schema, review the result, then apply it through `db:migrate`. Never use
`drizzle-kit push`: this repository requires a reviewed, reproducible migration
history. Commit the schema declaration, generated SQL, and `drizzle/meta`
snapshot/journal files together.

Migration names passed to Drizzle Kit are concise lower `snake_case`, for
example `create_flight_foundation`. Never edit or rename a migration that has
been applied outside a disposable local test database; create a new migration.
Migration tests must start with a fresh ignored SQLite file and prove the
migrator can be run again safely.

## Command contract

The runnable workspaces implement these root commands:

| Command | Contract |
| --- | --- |
| `npm run dev` | Supervise the API and Vite watchers; stop the sibling when either exits |
| `npm run dev:api` | Build contracts and start the TypeScript API watcher |
| `npm run dev:web` | Start Vite on the configured strict port |
| `npm run start:api` | Build contracts/API and start compiled JavaScript |
| `npm run build` | Build database, contracts/API, and emit the production Vite bundle |
| `npm run typecheck` | Strictly type-check database/contracts/API/web without emitting |
| `npm run lint` | Lint TypeScript and TSX source/tests, including database |
| `npm run format:check` | Verify maintained TS/TSX/HTML/SCSS/config formatting |
| `npm test` | Run database, contract, API, and web unit/integration/component suites |
| `npm run test:coverage` | Run V8 coverage for database/contracts/API/web and enforce thresholds |
| `npm run test:browser:install` | Download the Playwright Chromium binary used by browser smoke tests |
| `npm run test:browser` | Start local API/Vite processes and run browser smoke tests headlessly |
| `npm run test:browser:headed` | Run the same smoke tests with visible Chromium |
| `npm run test:browser:ui` | Run browser smoke tests through Playwright's interactive UI |
| `npm run db:generate --workspace @paragliding-forecasts/database -- --name <lower_snake_case_name>` | Generate a named migration for review |
| `npm run db:check --workspace @paragliding-forecasts/database` | Validate Drizzle schema/migration metadata |
| `npm run db:migrate --workspace @paragliding-forecasts/database` | Apply reviewed committed migrations to the configured local database |
| `npm run repo:check` | Validate repository and runnable workspace structure |

The root test commands include all four implemented TypeScript workspaces.
Each executable command must perform real work and fail when its child check
fails.

## Environment variables

`.env.example` is the reviewed contract for local configuration. `.env` is
ignored and local. When adding a variable:

1. add a safe example value and comment to `.env.example`;
2. validate it at the owning application's startup boundary;
3. document it in that subproject's README;
4. never expose secrets through a `VITE_` variable.

An application validates only configuration it currently consumes. Reserved
future settings may remain documented without forcing an unrelated service to
own their semantics.

## Branch and review flow

Use short-lived ticket branches and pull requests, including for scaffolding.
Recommended names are `feature/T-123-short-description` and
`fix/T-123-short-description`. Keep `main` in a reproducible state and reference
the backlog item in commits and pull requests.

## Checks by area

Current and planned checks by area are:

| Area | Expected checks |
| --- | --- |
| Repository | structure/workspace validation and clean-lockfile install |
| Web | typecheck, unit/component tests, production build, browser smoke test |
| API | build, lint, format, typecheck, unit/integration tests, real-socket smoke test |
| Contracts | build, schema/type tests, invariant and compatibility checks |
| Database | fresh-file migrations, migration idempotence, schema/constraint integrity, and connection-path checks |`n| ML | Ruff, pytest, schema/data-quality checks, reproducible backtests |

Do not make the root command report success by swallowing failed child checks.

## Data and safety

Run ingestion against cached or frozen samples during automated tests. Live
source checks should be explicit and rate-limited. Document provider terms,
attribution, timezone handling, coordinate assumptions, and missing data.

Forecast outputs are decision support. UI copy, API fields, screenshots, and
demo notes must not imply a guarantee of safe flying conditions.
