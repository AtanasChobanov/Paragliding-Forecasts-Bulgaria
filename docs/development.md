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

## Command contract

T-002 implements these root commands:

| Command | Contract |
| --- | --- |
| `npm run dev:api` | Build contracts and start the TypeScript API watcher |
| `npm run start:api` | Build contracts/API and start compiled JavaScript |
| `npm run build` | Emit ESM plus declarations for contracts, then API runtime ESM |
| `npm run typecheck` | Strictly type-check contracts/API without emitting |
| `npm run lint` | Lint TypeScript source and tests |
| `npm run format:check` | Verify maintained TypeScript/config formatting |
| `npm test` | Run contract and API unit/integration/smoke suites |
| `npm run repo:check` | Validate repository and runnable workspace structure |

T-003 must add `dev:web` and the combined `dev` command. Each executable
command must perform real work, fail when its child check fails, and be tested
and documented in the change that introduces it.

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
| ML | Ruff, pytest, schema/data-quality checks, reproducible backtests |

Do not make the root command report success by swallowing failed child checks.

## Data and safety

Run ingestion against cached or frozen samples during automated tests. Live
source checks should be explicit and rate-limited. Document provider terms,
attribution, timezone handling, coordinate assumptions, and missing data.

Forecast outputs are decision support. UI copy, API fields, screenshots, and
demo notes must not imply a guarantee of safe flying conditions.
