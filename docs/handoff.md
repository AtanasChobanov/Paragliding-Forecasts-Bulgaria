# Project Handoff

## Purpose and source of truth

This is a concise operational snapshot for the next implementation task. It is
not a project history. Use the following documents for the authoritative detail:

1. `AGENTS.md` for repository rules and workflow.
2. `docs/tasks.md` for backlog status and acceptance scope.
3. `docs/project-brief.md` for product, safety, and data requirements.
4. `docs/architecture.md` for system boundaries.
5. `docs/decisions.md` for accepted durable decisions.
6. Git history for prior implementation detail and validation evidence.

## Current state (2026-08-16)

| Field | Value |
| --- | --- |
| Branch | `feature/T-015-parser-fixtures`, based on T-014 commit `21a7665`; rebase after T-014 merges. |
| Working tree at handoff update | The T-016 research report is already staged. This handoff/tasks/decisions update is intentionally unstaged; preserve both sets of documentation changes. |
| Task status in `docs/tasks.md` | T-012 `Review`; T-013 `Review`; T-014 `Review`; T-015 `Review`; T-016 `Review`. |
| Next implementation focus | Review/merge T-012 through T-016, then run the bounded T-017 weather-field/source data spike before accepting an operational weather provider. |
| Local storage | SQLite selected by `DATABASE_URL`; local databases, raw source data, and interim artifacts are ignored. |

T-013 now has two successful local XCContest ingestion runs. The complete
`fresh`/human-review/`resume` workflow was manually exercised successfully for
2024 on 2026-08-11. This is functional verification by the project owner, not a
license, safety, or future source-access guarantee.

## Architecture and implemented product baseline

- `apps/web`: React/Vite local dashboard. It presents forecast evidence and
  explicit data states; it must not read SQLite or calculate model probabilities.
- `apps/api`: Express/TypeScript browser-facing API. It owns HTTP configuration
  and browser/API boundary validation, not Python ingestion or React rendering.
- `packages/contracts`: shared Zod/API contracts.
- `packages/database`: Drizzle SQLite schema and reviewed migrations. Drizzle is
  the only DDL/migration owner.
- `services/ml`: Python 3.12/uv ingestion, data, feature, model, and batch work.
  It produces language-neutral storage/file boundaries rather than a second HTTP
  service.

The dashboard/API baseline from T-001 through T-008 is implemented and tested.
Its detailed visual and historical test checkpoints are intentionally not
repeated here; consult Git and the owning README/tests when changing that area.

## T-016 weather-data research handoff

The detailed source comparison is in
[`T-016-forecast-data-research-report.md`](T-016-forecast-data-research-report.md).
T-016 is ready for review: exact historical forecasts exist, but no one free
high-resolution archive covers the complete likely Bulgarian flight-history
period.

- Treat `forecast`, `reanalysis`, and `observation` as distinct source kinds.
  An as-issued forecast is the information available before a flight day;
  reanalysis is a retrospective physically consistent reconstruction; station
  and radiosonde values are point observations. Do not train or backtest as if
  they were interchangeable, and retain source/model/run/valid/lead provenance.
- The provisional exact/live primary is explicit Open-Meteo ECMWF IFS HRES
  Single Runs from 2024-03-14. NOAA GFS offers older exact forecasts from 2006
  at materially coarser resolution. ERA5 is the provisional long-history
  reanalysis baseline; CERRA is a bounded 5.5 km terrain-resolution comparison.
  Direct DWD ICON-EU is the commercial-safe raw-GRIB comparator/future fallback.
  These are research recommendations, not accepted provider or feature choices.
- For current forecasts, select only a fully available named model run and
  preserve `runAt`, `availableAt`, `retrievedAt`, `validAt`, and `leadHours`.
  A `00 UTC` global run normally becomes available 4–6 hours later; schedule
  ingestion from provider availability metadata rather than a fixed local time.
  If a new run is unavailable, retain the last successful forecast and expose
  its age. ERA5, which has about five days of latency, is not an operational
  fallback.
- Open-Meteo's free hosted service is non-commercial. A paid beta/subscription
  product must use its appropriate commercial plan or a direct licensed source;
  preserve required attribution and source licence metadata. The direct DWD
  path avoids a hosted Open-Meteo commercial dependency but requires GRIB
  decoding, subsetting, and operational archiving.
- T-017 must request a small, representative Bulgaria sample across 24/48/72/
  120-hour leads and confirm per-model field availability, units, nulls,
  grid-orography fit, CAPE/CIN/PBL derivability, payload cost, run identity,
  attribution, and source switching behaviour before T-018 designs the schema.
  T-019 should parse raw NOAA IGRA Sofia profiles; image scraping/OCR remains
  deferred.

## Database and flight-data boundary

The migrated SQLite flight foundation contains `flight_sources`, `sites`,
`source_site_mappings`, `ingestion_runs`, and `flight_records`. Preserve units,
provenance, confidence, and the states `mock`, `manual`, `baseline`, `real`, and
`missing` across boundaries.

Important current behavior:

- Canonical flight identity is source-specific: `(source_id, source_flight_id)`.
  T-014 classifies each repeat as no-op revalidation, enrichment, preservation,
  conflict, or a reviewed resolution; it never silently replaces a row.
- A persisted flight retains the chosen source URL, canonical values, selected
  source-site mapping, validation provenance, creator run, and latest validator
  run. `validation_notes` is schema-v1 machine-verifiable quality/provenance JSON
  after a T-014 reconciliation; pre-existing legacy text is not backfilled.
- A conflict writes ignored immutable review evidence under
  `data/interim/xccontest/<run-key>/reconciliation-v1/` and rolls back before
  any flight/run write. Follow the `Flight reconciliation and review workflow` section of
  `services/ml/README.md` exactly.
- T-012 migrations are reviewed/applied local schema history. Do not rewrite or
  alter applied migrations; generate a new reviewed migration when schema change
  is required.

## XCContest T-013: operational workflow

The implemented commands preserve their individual durable stage boundaries:

```powershell
uv run --env-file .env --project services/ml xccontest-collect --season <year>
uv run --env-file .env --project services/ml xccontest-parse --run-key <uuid>
uv run --env-file .env --project services/ml xccontest-site-mappings propose --run-key <uuid>
uv run --env-file .env --project services/ml xccontest-site-mappings apply --review-file <mapping-decisions.jsonl>
uv run --env-file .env --project services/ml xccontest-validate --run-key <uuid>
uv run --env-file .env --project services/ml xccontest-persist --run-key <uuid> --policy-file <path>
```

The recommended orchestration commands are:

```powershell
uv run --env-file .env --project services/ml xccontest-ingest fresh 
  --season <year> 
  --headed 
  --policy-file data/local/xccontest-import-policy.json

uv run --env-file .env --project services/ml xccontest-ingest resume 
  --run-key <uuid> 
  --policy-file data/local/xccontest-import-policy.json
```

`fresh` performs preflight, collection, parsing, read-only proposal generation,
validation, and persistence when safe. `resume` is offline: it reuses raw and
interim artifacts and never launches a browser. Raw output remains under
`data/raw/xccontest/<run-key>/`; parser, mapping, validation, and reconciliation
review output remains under `data/interim/xccontest/<run-key>/`. New mapping
snapshots create distinct `validation-v2/<snapshot>/` output directories; existing
artifacts are not overwritten.

After the mapping gate allows accepted records, persistence now compares them
with canonical SQLite rows. Exact repeats revalidate, safe missing-to-known
values enrich, and lower-quality incoming values cannot erase known values. A
material difference returns `awaiting_reconciliation_review` (exit code 2) and
writes no database row. Copy/review the returned `reconciliation-proposals.jsonl`
into `reconciliation-decisions.jsonl`, then run the same offline `resume`
command. The detailed contract, including every required JSONL field, is in the
`Flight reconciliation and review workflow` section of `services/ml/README.md`.

### Source safety

- Use only the permitted normal browser workflow and comply with source terms.
  Do not bypass login, challenges, access controls, or rate limits; do not use
  proxies, IP rotation, parallel tabs, undocumented endpoints, or synthesized
  pagination URLs.
- Collector v3 defaults to a 30-second source delay before every navigation and
  source-changing visible UI action. `--slow-mo-ms` is debugging-only.
- A 3–29.999 second delay requires `--acknowledge-rate-limit-risk`; lower than
  three seconds is rejected. The raw manifest records pacing policy.
- On HTTP 500, challenge, failed initial navigation, or missing rendered table,
  stop and investigate without repeated retries. A 500 can be an IP-specific
  access response rather than a general source outage.
- Collect only explicitly chosen seasons. XCContest season `Y` spans
  `Y-1-10-01` through `Y-09-30`.

### Mapping review gate

`fresh` automatically writes read-only proposals but never applies them.
Reviewers copy/edit the standard sibling file:

```powershell
$mappingDir = "data/interim/xccontest/<run-key>/site-mapping-v2"
Copy-Item "$mappingDir/mapping-proposals.jsonl" "$mappingDir/mapping-decisions.jsonl"
```

Apply reviewed decisions manually, then run `resume`. An approved mapping enters
SQLite after the human review. A rejected decision keeps matching flights in
quarantine and excludes them from persistence, but it no longer blocks the
accepted subset when all of the following match the immutable proposal:

- `proposal_id`;
- source/key type/key value; and
- source-point coordinates where applicable.

Missing, duplicate, mismatched, provisional, ambiguous, country-mismatched, or
otherwise unreviewed mapping evidence remains blocking with
`awaiting_mapping_review`. The result reports both
`actionable_mapping_quarantine_count` (unresolved) and
`reviewed_rejected_mapping_quarantine_count`. `--persist-approved-only` remains
an explicit override for intentionally retaining unresolved records; normally do
not need it after a complete accepted/rejected review.

## Verified local imports

All records below are local ignored data; never commit the database, raw HTML,
or interim JSONL.

| Ingestion run | Scope and result | Durable notes |
| --- | --- | --- |
| `f1032827-a98d-4c01-969e-e67b4885f90d` | First successful import: 267 accepted flights from the prior 2025/2026 collection; 1,200 seen, 664 rejected, 69 quarantined, 200 same-run duplicates removed. | Established the persistence slice and the first `ingestion_runs` row. |
| `8d809838-3ff8-42ce-9977-3997cd2536bc` | Manual 2024 `fresh`, review/apply, then successful `resume` on 2026-08-11. 600 seen; 208 normalized candidates; 182 persisted accepted flights; 295 rejected; 26 quarantined; 97 same-run duplicates removed. | `ingestion_run_id=2`; validation snapshot `fbe9bc251bc07b287d16e2c2127c70daf0b781754ca871931bd6530680ea2204`; 26 quarantines were explicitly reviewed/rejected and `actionable_mapping_quarantine_count=0`. |

For the 2024 run, eight reviewed mappings were approved and inserted, while ten
proposals were rejected. The successful result used pipeline version
`xccontest-collector/3|xccontest-parser/2|xccontest-validation/2|xccontest-persistence/2`.
The raw manifest is complete, schema version 3, and covers season 2024/BG.

## Verification baseline

The latest T-015 code checks passed locally:

```powershell
uv run --project services/ml ruff format --check
uv run --project services/ml ruff check
uv run --project services/ml pytest
```

At the latest verification, all 77 ML tests passed, including 11 focused T-014
reconciliation tests and the committed T-015 parser-fixture integration/regression
test. The persistence/component tests use synthetic durable
artifacts, real mapping-review transactions, and temporary SQLite migrated by
the committed Drizzle migrations; they make no source request and never open the
existing 449-row local database. The project owner asked not to run a
fresh/collector command for T-014 verification. Manual verification is therefore
an offline `xccontest-ingest resume` or `xccontest-persist` against existing
local interim data only. Do not mistake fixtures/fakes for permission to make
new live source requests.

## T-014 review handoff

**Delivered:** compare-and-reconcile persistence, same-run no-op replay,
cross-run duplicate revalidation, partial-run resume support, atomic conflict
pause/resolution, source URL preservation, schema-v1 quality notes, append-only
run events, detailed operator documentation, and integration/component coverage
through real temporary SQLite migrations and mapping-review transactions. No
database migration or Docker instance was needed because existing text provenance
fields are sufficient and SQLite tests migrate a temporary local file.

**Manual review:** use only already collected `data/interim/xccontest/<run-key>/`
artifacts. Do not run `fresh` or a collector command. If an existing run produces
a reconciliation pause, follow the `Flight reconciliation and review workflow` section of
`services/ml/README.md`; inspect the generated proposal, create the
matching decisions file, and run offline `resume`.
An exact repeated snapshot is expected to be a successful no-op. Do not edit raw,
validation, proposal, or existing database evidence by hand.

## T-015 parser fixture handoff

**Delivered:** a small committed synthetic XCContest manifest-v3 mini-run under
`data/samples/xccontest/parser-v2/synthetic-mini-run-v1/`, reviewed parser-v2
golden JSONL/report outputs, and a fixture-driven offline parser
integration/regression test. The test copies the fixture into a temporary raw
layout, validates hashes/counters through the real parser, and compares every
output artifact. It opens no browser, makes no network request, and does not
access SQLite.

The fixture is entirely project-authored: it contains no copied live/raw page,
real pilot information, account data, or track. Its README records synthetic
origin, sanitation/redistribution limits, test command, and case matrix.
Coverage includes manifest-v3 compatibility; current/archived URL shapes;
100/200/300 km boundaries; decimal parsing; route variants; season/timezone
boundaries; launch evidence; exact and conflicting duplicate observations;
under-threshold/malformed rows; and pilot-text exclusion from parser output.
Browser navigation, source responses, pagination, retries, and rate policy
remain collector/browser concerns, covered separately.

**Validation:** `uv run --project services/ml ruff format --check`, `ruff
check`, and the full `pytest` suite passed on 2026-08-13: 77 tests passed.

## Routine commands

From repository root:

```powershell
npm.cmd install
uv sync --project services/ml
Copy-Item .env.example .env
npm.cmd run repo:check
```

For broad TypeScript validation use `npm.cmd run build`, `typecheck`, `lint`,
`format:check`, and `test`. For ML work use the `uv run --project services/ml`
commands above. Update this handoff only with a current operational snapshot;
record durable design choices in `docs/decisions.md` and task status in
`docs/tasks.md`.
