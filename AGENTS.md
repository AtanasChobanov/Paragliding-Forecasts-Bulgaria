# Repository Guidance

## Project overview

Paragliding Forecasts Bulgaria is a local-first decision-support product that
will rank promising Bulgarian paragliding cross-country days from forecast,
atmospheric, and historical-flight evidence. It is not an aviation weather or
safety service; see [`docs/project-brief.md`](docs/project-brief.md) for the
complete requirements and safety framing.

## Source-of-truth documents

- [`docs/project-brief.md`](docs/project-brief.md) defines product requirements,
  delivery goals, risks, and the initial data model.
- [`docs/architecture.md`](docs/architecture.md) defines system boundaries and
  the accepted high-level design.
- [`docs/tasks.md`](docs/tasks.md) is the ticket backlog and task-status source.
- [`docs/decisions.md`](docs/decisions.md) records durable accepted/proposed
  decisions and open choices.
- [`docs/handoff.md`](docs/handoff.md) is the current operational snapshot for
  the next session; update it at the end of meaningful work.

Future agents should read, in order:

1. this root `AGENTS.md`;
2. the current `docs/handoff.md`;
3. the relevant ticket in `docs/tasks.md`;
4. only the sections of `docs/project-brief.md` and `docs/architecture.md`
   needed for that ticket.

Do not load or reproduce the entire project brief when a focused section is
sufficient.

## Repository structure

- `apps/api/` - scaffold for the Node.js, Express, and TypeScript HTTP API.
- `apps/web/` - scaffold for the React, Vite, and TypeScript dashboard.
- `packages/contracts/` - scaffold for shared browser/API TypeScript contracts.
- `services/ml/` - uv-managed Python project for ingestion, data/feature work,
  modeling, backtesting, and batch prediction.
- `data/` - local data zones; only small sanitized fixtures under `samples/`
  may be committed.
- `docs/` - project brief, architecture, tasks, development notes, decisions,
  and the session handoff.
- `scripts/` - repository-level automation; currently the scaffold check.

## Technology and tooling rules

- Use Node.js 24.x and npm 11.x. The root is a private npm monorepo with
  workspaces `apps/*` and `packages/*`; commit `package-lock.json`.
- TypeScript strict mode is the default for product-facing code. React/Vite is
  the selected web direction; Node.js/Express is the selected browser-facing
  API direction. These applications are currently scaffolds, not running apps.
- Use Python 3.12 and uv only for `services/ml`; commit `services/ml/uv.lock`.
  Python initially produces language-neutral batch outputs and is not a second
  public HTTP service.
- `packages/contracts` owns browser/API payload shapes. Keep the Python boundary
  language-neutral through documented JSON, records, or storage schemas.
- SQLite is the MVP storage direction; database schema and access tooling are
  not implemented yet. Do not silently choose an ORM or validator.
- Preserve units, provenance, confidence, and the explicit data states `mock`,
  `manual`, `baseline`, `real`, and `missing` across system boundaries.
- Consult `docs/decisions.md` before changing these choices and record any
  approved architectural change there.

## Setup and commands

Current clean-checkout setup from the repository root:

```powershell
npm.cmd install
uv sync --project services/ml
Copy-Item .env.example .env
npm.cmd run repo:check
```

On macOS/Linux, use `npm` and `cp .env.example .env`. On Windows, `npm.cmd`
avoids PowerShell execution-policy problems with `npm.ps1`.

Currently supported repository commands:

- `npm install` / `npm.cmd install` - install/link npm workspaces.
- `uv sync --project services/ml` - sync the Python project environment.
- `npm run repo:check` / `npm.cmd run repo:check` - validate the scaffold and
  workspace metadata.

There are currently no runnable dev, build, lint, formatting, type-check, test,
API, web, ingestion, training, or prediction scripts. Add and document a command
in the same ticket that implements its real behavior; never simulate success
with placeholder logic.

## Engineering conventions

- Install JavaScript dependencies into the owning npm workspace; reserve root
  dependencies for tooling shared by multiple TypeScript workspaces.
- Add Python dependencies with `uv add --project services/ml`; do not introduce
  Yarn, pnpm, requirements files, Poetry, or unmanaged virtual environments
  without an approved migration decision.
- Keep `.env` local. Add safe examples to `.env.example`, validate variables at
  the owning startup boundary, and document them in the owning README. Never put
  secrets in `VITE_` variables.
- Do not commit credentials, private pilot data, raw downloads, local SQLite
  databases, model artifacts, generated output, or large datasets. Committed
  fixtures must be small, sanitized, licensed, deterministic, and documented.
- The web app must not read databases or calculate model probabilities. The API
  must not contain React presentation or Python training logic.
- Keep public units explicit, represent missing values deliberately, and retain
  source/quality metadata.
- Add tests and reproducible checks with the behavior they validate. Follow the
  area-specific expectations in the subproject READMEs and project brief.
- Update repository-wide setup in the root README and local commands/config in
  the owning subproject README. Record limitations and safety implications
  honestly.
- Use short-lived ticket branches and imperative ticket-prefixed commits as
  described in `CONTRIBUTING.md`. Keep every change scoped to the requested
  ticket and preserve unrelated user work.

## Task workflow

1. Inspect the repository, current branch, status, staged/unstaged diff, and
   recent relevant commits.
2. Read `docs/handoff.md` and the relevant ticket in `docs/tasks.md`.
3. Confirm scope, acceptance criteria, dependencies, and unresolved choices.
4. Create a short implementation plan.
5. Implement only the requested ticket; do not start later tickets implicitly.
6. Run every relevant validation command that actually exists.
7. Review the final diff for unrelated or accidental changes.
8. Update task status only when the repository state justifies it.
9. Update `docs/handoff.md` with the verified end state and validation results.
10. Add new durable decisions or supersessions to `docs/decisions.md`.

Do not mark a task completed when required validation has failed, could not run,
or has not been performed. Report partial verification explicitly.

## Definition of done

A requested task is done only when:

- the requested functionality and acceptance criteria are implemented;
- relevant available tests, linting, type checking, builds, and validation have
  been run, with results reported honestly;
- behavior required by the ticket is reproducible from documented commands;
- the diff contains no unrelated changes and preserves existing user work;
- affected setup, commands, configuration, assumptions, and limitations are
  documented;
- unverified behavior, blockers, and follow-up work are explicit.

## Restrictions

- Do not introduce a dependency without a concrete need owned by the task.
- Do not change architecture, service boundaries, package managers, storage
  direction, or data semantics silently.
- Do not commit secrets, local environment files, generated data, or large
  artifacts.
- Do not fabricate commands, test results, completed behavior, or source data.
- Do not overwrite, discard, stage, or commit unrelated user changes.
- Do not work on later tickets unless explicitly requested.
- Do not present assumptions or proposals as accepted decisions.
- Do not weaken the product's safety framing or present forecasts as guarantees.
