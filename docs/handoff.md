# Project Handoff

## Handoff metadata

| Field | Value |
| --- | --- |
| Last updated | 2026-07-17 |
| Current Git branch | `feature/t-001-repository-scaffold` tracking `origin/feature/t-001-repository-scaffold` |
| Current/recent task | `T-001 — Create project repository and README skeleton` — status `Review` |
| Next intended task | `T-002 — Create local server skeleton` — status `To Do` |
| Latest relevant commit | `09d18fd T-001 add Python dependency lockfile` |
| Working tree | **Not clean.** No staged changes and no modifications to tracked files were present at generation time. Pre-existing untracked inputs: `docs/project-brief.md`, `docs/tasks.md`. Files created by this documentation request: `AGENTS.md`, `docs/handoff.md`, `docs/decisions.md`; they remain untracked until the user stages them. |

The branch contains two commits beyond `main`: `ac43e13 T-001 scaffold
repository structure` and `09d18fd T-001 add Python dependency lockfile`. At
inspection time, the branch tip matched its remote tracking branch; T-001 has
not been observed as merged into `main`.

## Project goal

Build a local-first decision-support application that ranks promising
paragliding XC days for selected Bulgarian locations and eventually warns users
at least one day before an opportunity. It will connect historical flight
evidence to forecast, weather, and sounding features while exposing confidence,
provenance, and safety limitations. See [`project-brief.md`](project-brief.md)
for the complete scope.

## Current state

### Implemented and verified

- A private npm monorepo is configured with `apps/*` and `packages/*`
  workspaces, Node.js 24/npm 11 engine constraints, and a committed lockfile.
- The uv-managed Python project has Python 3.12 metadata and a committed
  `services/ml/uv.lock` containing only the local project.
- Strict shared and package-specific TypeScript configuration exists.
- Root/subproject setup, architectural boundaries, data policy, contribution
  workflow, and safety/data-state requirements are documented.
- `npm run repo:check` validates the T-001 scaffold and workspace names.
- Git ignore rules exclude secrets, generated Node/Python artifacts, local
  SQLite files, raw/derived datasets, and model artifacts while permitting
  small fixtures under `data/samples/`.

### Scaffolded or placeholder-only

- `apps/api`, `apps/web`, and `packages/contracts` have package metadata,
  README files, TypeScript configs, and empty `src` boundaries only.
- `services/ml` has project metadata and an empty package boundary; it has no
  ingestion, feature, training, prediction, or test implementation.
- Data-zone directories exist, but no application schema or committed dataset
  has been implemented.

### Planned but not started

- No local API or web server runs yet.
- No Express entry point, health endpoint, React/Vite application, shared
  contract source, SQLite schema, data pipeline, model, alert, or browser test
  exists.
- There are no current dev, build, lint, formatting, type-check, or test scripts.

## Work completed in the current session

- Completed and committed the T-001 repository scaffold on a dedicated feature
  branch.
- Established npm workspaces for the future API, web app, and shared contracts.
- Established the uv-managed Python/ML project and committed its lockfile.
- Added project-wide setup, repository map, safety framing, data policy,
  subproject responsibilities, architecture, development, and contribution
  documentation.
- Added repository hygiene/configuration files and the `repo:check` validation
  script.
- Discussed and applied the workflow of a short-lived feature branch and a
  ticket-prefixed commit/PR review process; T-001 is now recorded as `Review` in
  `docs/tasks.md`.
- Created permanent agent guidance (`AGENTS.md`), this operational handoff, and
  the durable decision log (`docs/decisions.md`) in the present documentation
  request. These files are not committed.

## Files created or modified

### Committed as part of T-001

- `README.md`, `CONTRIBUTING.md`, `docs/architecture.md`, and
  `docs/development.md` define repository-wide setup, boundaries, workflow, and
  handover expectations.
- `package.json`, `package-lock.json`, and `tsconfig.base.json` define the npm
  workspace and shared TypeScript baseline.
- `apps/api/*`, `apps/web/*`, and `packages/contracts/*` establish the
  TypeScript subproject boundaries without runtime implementation.
- `services/ml/*` establishes the Python 3.12/uv project, lockfile, source
  namespace, and empty test boundary.
- `.env.example`, `.editorconfig`, `.gitattributes`, `.gitignore`, and
  `data/.gitignore` define safe local configuration, cross-platform text rules,
  and ignored artifacts.
- `data/README.md`, its zone markers, and `data/samples/README.md` document the
  local data lifecycle and committed-fixture exception.
- `scripts/check-structure.mjs` provides the only current repository validation
  script.

### Pre-existing untracked inputs at the start of this request

- `docs/project-brief.md` — Markdown project requirements used as a requested
  source of truth; it was not created or modified by this request.
- `docs/tasks.md` — Markdown backlog showing T-001 in `Review` and T-002 next;
  it was not created or modified by this request.

### Created by this documentation request

- `AGENTS.md` — durable instructions for future Codex sessions.
- `docs/handoff.md` — current operational snapshot.
- `docs/decisions.md` — durable accepted/proposed decisions and open choices.

## Important implementation details

- The npm workspace names are `@paragliding-forecasts/api`,
  `@paragliding-forecasts/web`, and `@paragliding-forecasts/contracts`.
- The only current root script is `repo:check`. Commands documented as arriving
  in T-002/T-003 are not runnable and must not be reported as implemented.
- The intended browser-facing boundary is the Express API; Python begins as a
  batch data/ML pipeline. See [DEC-003](decisions.md#dec-003--use-typescript-by-default-and-limit-python-to-dataml-work) through
  [DEC-005](decisions.md#dec-005--share-browserapi-contracts-in-typescript-and-keep-python-language-neutral).
- `.env.example` currently reserves ports, API origin, SQLite location, model
  artifact directory, logging, and `FORECAST_DATA_MODE=mock`. T-002 should
  validate only variables it actually consumes.
- Local SQLite is intended under `data/local/` and is ignored. No schema or
  access library has been selected; see [DEC-006](decisions.md#dec-006--use-a-local-first-mvp-and-sqlite-storage-direction).
- Empty `.gitkeep` files preserve scaffold directories. Remove a marker when a
  real tracked file occupies that directory; data-zone markers may remain so
  ignored local directories exist after checkout.
- Only small, sanitized, redistributable test fixtures may be committed under
  `data/samples/`; all other data zones remain local/ignored.

## Validation performed

- **Passed:** `npm.cmd install --package-lock-only --ignore-scripts` generated
  and validated the npm lockfile/workspace links.
- **Passed:** `npm.cmd ci --ignore-scripts` installed the three npm workspace
  links and reported no audit findings at the time it ran.
- **Passed:** `npm.cmd run repo:check` reported `Repository scaffold check
  passed.`
- **Passed:** ad hoc JSON parsing of all manifests/TypeScript configs and TOML
  parsing of `services/ml/pyproject.toml`.
- **Passed:** checks that `.nvmrc` and the old root `.python-version` were absent,
  and `services/ml/.python-version` contained `3.12`.
- **Passed:** ignore-policy checks for `.env`, `node_modules`, TypeScript output,
  `.venv`, Python cache files, raw data, model artifacts, and local SQLite;
  `data/samples` remained eligible for committed fixtures.
- **Passed:** trailing-whitespace checks, staged-diff checks, and clean working
  tree checks before the two T-001 commits.
- **Passed with explicit local overrides:** `uv --cache-dir .tmp/uv-cache lock
  --project services/ml --check --python <bundled Python 3.12.13>` resolved the
  single local project and confirmed that `uv.lock` is current.
- **Not run / unavailable:** application build, lint, format, type-check, unit,
  integration, and browser tests because no corresponding scripts or runtime
  implementation exists yet.

## Failed attempts and discarded approaches

- The original DOCX project brief was passed to the packaged renderer, but
  rendering failed because LibreOffice/`soffice` was unavailable. Its text and
  tables were instead inspected structurally. The ignored, empty
  `.tmp/t001-brief-review/` scratch directory remains; no tracked partial output
  was created.
- The first `uv sync --project services/ml` attempt failed because `uv` was not
  installed at that time. An official installer attempt was aborted by the
  user; it produced no repository changes. `uv 0.11.28` is now available.
- A current `uv sync --project services/ml --locked` retry failed because the
  default cache path at `C:\Users\User\AppData\Local\uv\cache` conflicts with
  an existing entry. A project-local cache then exposed a stale `.venv` linked
  to a missing uv-managed interpreter and insufficient permission to create
  `C:\Users\User\AppData\Roaming\uv\python`. Lockfile validity was checked
  successfully using a project-local cache and an explicit available Python
  3.12.13 interpreter; the default local sync path remains unresolved.

## Known issues, blockers and uncertainties

- **Confirmed:** `docs/project-brief.md` and `docs/tasks.md` are untracked. They
  will be absent from a clean clone until deliberately staged and committed.
- **Confirmed:** `docs/tasks.md` contains spreadsheet serial values instead of
  rendered dates and has a mis-encoded euro-cost heading. This request did not
  alter the task source.
- **Confirmed:** scheduling sources disagree: the project brief retains an
  original 15 June 2026 UI milestone, while `docs/tasks.md` places the end of
  Takt 1 on 2026-07-28. The repository owner should confirm which schedule is
  authoritative.
- **Confirmed local-tool issue:** default `uv sync` is currently blocked by the
  cache/interpreter conditions described above. The lockfile itself is current.
- **Confirmed:** no runnable server or application validation exists yet;
  T-001 is scaffold/documentation only and remains in review.
- **Unresolved:** API development runner, test framework, runtime validation
  library, and SQLite access layer have not been selected.
- **Unresolved:** launch coordinates/radii, source access terms, historical
  forecast provider, alert channel, deployment approach, and license remain
  open. See `docs/decisions.md`.

## Next steps

1. Complete review/merge of `T-001 — Create project repository and README
   skeleton`. Before merging, decide whether the five untracked documentation
   files should be included and reconcile the task/schedule formatting issues.
2. Start `T-002 — Create local server skeleton` from an updated `main` after
   T-001 is merged, or use an explicitly managed stacked branch if work must
   begin earlier.

For T-002:

- **Intended outcome:** add a real Node.js/Express/TypeScript local server that
  starts with a documented command. The existing API README proposes separating
  `app.ts` from `server.ts` and a first `GET /health` endpoint, but the ticket's
  required outcome is the reliable documented server startup.
- **Inspect first:** `AGENTS.md`, this handoff, T-002 in `tasks.md`, the Express
  API section of `architecture.md`, `../apps/api/README.md`, root/API package
  manifests, TypeScript configs, and `.env.example`.
- **Dependencies from T-001:** npm workspace name, Node/npm constraints, strict
  TypeScript baseline, `API_PORT`, contribution workflow, and `repo:check`.
- **Required validation:** clean npm installation; the newly introduced API dev
  command; an automated or reproducible health/startup check; any build,
  type-check, lint, and test commands introduced by T-002; `npm run repo:check`;
  final diff review. Report any unavailable check honestly.
- **Decisions to resolve only as needed:** dev runner, test runner, server
  shutdown behavior, configuration validation, and whether T-002 needs a
  runtime schema library. Do not introduce SQLite access merely for a health
  endpoint unless the ticket requires it.

## Quick start for the next Codex session

> Read the root `AGENTS.md`, this `docs/handoff.md`, T-002 in `docs/tasks.md`,
> and only the relevant API/setup sections of `docs/project-brief.md` and
> `docs/architecture.md`. Inspect the current Git state, confirm whether T-001
> has merged and whether the untracked documentation was committed, then
> summarize T-002 and propose a short plan before making changes.
