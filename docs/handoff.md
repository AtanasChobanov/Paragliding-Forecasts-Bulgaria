## T-018/S04 GFS GRIB parser and normalization handoff

T-018/S04 is implemented. The offline-only `gfs-parse` command accepts only a
complete, hash-verified S03 raw GFS run. It uses the pinned Python `eccodes`
2.47.0 binding and numeric NOAA `kwbc` GRIB2 profile (master table 2, local
table 1) to verify every selected message's identity, level, reference/valid
time, forecast step, statistic and grid metadata before storing immutable native
arrays and missing masks. `HPBL` is matched numerically because its ecCodes
short name is not stable enough to be a parser identity.

The normalizer emits separate canonical surface/convection/interval and
pressure-level grains for S05. It retains native U/V fields; derives speed and
meteorological direction; converts signed GFS CIN to a positive magnitude while
retaining the native convention; and maps GFS geopotential-height values to
canonical height. Bitmap/sentinel cells are retained through masks and marked
`sentinel_missing`; valid values are `real`; derived arrays are `derived`; and
malformed boundary input is rejected as `invalid_payload`. The only accepted
quality-state vocabulary is `real`, `derived`, `missing`, `sentinel_missing`,
and `invalid_payload`.

The parser preserves S03's shortest explicitly identified APCP interval. It
does not infer a precipitation rate or de-accumulate across runs; a future
multi-interval implementation may de-accumulate only when it proves adjacent
interval continuity and reset behavior. `GUST` and orography remain parsed as
native evidence but are explicit unsupported canonical mappings because neither
has a T-017/S01 destination. No additional GUST metric was added: the Project
Brief requests wind speed/direction and shear, while T-017 and the persisted
weather schema contain no gust field.

A committed offline golden contract fixture locks the f007 numeric identities,
selected-selector count, canonical-grain counts, GUST mapping outcome and
quality policy. The fixture is intentionally small and contains no raw NOAA
grid download; the parser's real f007 run was additionally exercised locally
against ignored raw evidence on 2026-08-21.

Final verification: `uv run --project services/ml pytest -q` (106 passed),
`uv run --project services/ml ruff check`, `uv run --project services/ml ruff
format --check`, `uv run --project services/ml gfs-parse --help`, and `git diff
--check` all passed. No network request is made by default tests or `gfs-parse`.

Next slice: T-018/S05 must consume only hash-verified S04 canonical grid
artifacts; it must not re-fetch raw GFS, reinterpret parser provenance, or add
an unapproved GUST persistence field.
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

## Current state (2026-08-20)

| Field | Value |
| --- | --- |
| Branch | `feature/T-018-weather-ingestion`. |
| Working tree at handoff update | T-018/S02 adds Python runtime contracts, immutable artifacts, state protocol, tests, and documentation. T-018/S01 is committed on this branch; its migration has not been applied to the configured local database. |
| Task status in `docs/tasks.md` | Unchanged in this session; `tasks.md` was deliberately not edited. |
| Next implementation focus | Implement S03 GFS request planning and immutable collection against the S02 contracts; do not add a placeholder CLI. |
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
- DEC-031 supersedes the earlier provisional source preference: GFS is the
  coarse exact long-history forecast comparator; ICON-EU is the preferred recent
  regional profile candidate; IFS HRES is only a conditional high-resolution
  surface/PBL component; ERA5 is the long-history reanalysis baseline; CERRA is
  an offline terrain comparison; and IGRA is observational validation. Do not
  silently substitute these source kinds or models.
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
- T-017 completed that bounded Bulgaria sample and locked the source/feature
  contract for T-018. T-019 should parse raw NOAA IGRA Sofia profiles; image
  scraping/OCR remains deferred.

## T-017 weather-field spike handoff

The detailed results and proposed canonical vocabulary are in
[`T-017-weather-feature-spike-report.md`](T-017-weather-feature-spike-report.md)
and the machine-readable
[`weather-field-catalogue.json`](../services/ml/src/paragliding_forecasts_ml/ingestion/atmosphere/resources/weather-field-catalogue.json).

The no-credential phase is complete for five canonical sites, representative
strong/marginal/precipitation cases, and 24/48/72/120-hour leads:

- Open-Meteo IFS HRES provides useful high-resolution surface, CAPE/CIN, and
  PBL fields, but all requested pressure-level profiles were null. One explicit
  archived run also returned an HTTP-200 plain-text unavailable-run error. It
  cannot remain the sole detailed source.
- Open-Meteo ICON-EU returned complete 925/850/700 hPa temperature, humidity,
  wind, and geopotential profiles in the sample, but no PBL height or pressure-
  level vertical velocity. It is the preferred regional profile candidate.
- NOAA GFS public AWS GRIB2 returned the required surface, profile, CAPE/CIN,
  PBL, and vertical-velocity inventory without registration; it is accepted as
  the coarse exact long-history comparator.
- NOAA IGRA Sofia raw/derived archives contained 06 and 12 UTC profiles for all
  three 2025 case dates and are accepted as observational validation evidence.
- ERA5 authenticated CDS retrievals completed for all three case dates. The
  surface and pressure-level inventories are accepted as the long-history
  reanalysis baseline; direct CIN and cloud base are nullable, and bitmap/
  missing-value metadata must turn sentinels into explicit nulls.
- CERRA retrieval and decoding are verified: 13 analysis messages across two
  successful jobs used the 1069 x 1069 full-domain grid with zero missing values.
  It is accepted as an offline terrain comparator, not as primary direct PBL,
  cloud-base, CAPE, or CIN evidence.

CDS account setup and all required terms are complete. Four bounded ERA5
requests downloaded 519,048 bytes and were decoded successfully: all 630
pressure-level messages had no missing grid values, while direct ERA5 CIN was
missing for 93.359% and cloud base for 21.839% of the sampled surface grid.
Preserve run/base time, valid time, step/statistic, native units, and missing
metadata; never persist the GRIB missing sentinel as a physical value.

Both CERRA jobs completed successfully and were downloaded. The 12-field
analysis payload is 27,438,924 bytes and the one-field diagnostic is 2,286,577
bytes. Each spent about two hours queued, while provider processing took about
10 seconds and local download under six seconds. The decoded native surface
inventory is `2t` K, `2r` %, `10si` m/s, `10wdir` degrees true, `msl`/`sp` Pa,
`tcc`/`lcc`/`mcc`/`hcc` %, `orog` m, and `tciwv` kg/m2. CERRA surface wind
components are derived from native speed/direction. Raw GRIB, request/result
metadata, and `cerra-decoded-summary.json` remain ignored under
`data/raw/weather-spike/cds/`. T-017 is ready for review.

## Post-spike weather implementation context

T-018 owns the source-neutral SQLite weather schema and the complete GFS and
ERA5 ingestion pipeline through persistence. It includes immutable raw
artifacts/manifests, source decoders, canonical normalization, deterministic
site/grid sampling, validation/quarantine, versioned feature building and
idempotent SQLite writes. Do not create inert placeholder collectors.

GFS is the only exact-forecast source in this implementation phase. It is used
both for historical exact forecasts and for the current/future forecasts that
the product will later show, preserving one source/model distribution across
training and operational inference. Select only a complete named GFS run;
retain the last successful GFS result and its age when a new run is unavailable.
Do not silently replace it with another model.

ERA5 is the separate long-history reanalysis baseline, collected through the
registered CDS path. It is not a live fallback and must never fill a missing
GFS row. Its later roles are independent reanalysis evaluation, forecast-to-
ERA5 verification/bias pairs and climatology/anomaly features; those joins and
all ML work remain outside T-018. Any product use of ERA5 must carry the
applicable Copernicus/ECMWF attribution.

Open-Meteo ICON-EU, direct DWD ICON-EU, Open-Meteo IFS HRES and CERRA are not
implemented in T-018. They remain future source options only: ICON-EU for a
regional profile path, IFS HRES for a conditional high-resolution surface/PBL
component, and CERRA for an offline terrain-resolution reanalysis comparison.
Each requires a new accepted source decision, an adapter, provenance/archival
handling and a compatible model evaluation. IGRA soundings remain T-019.

### T-018 implementation slice plan

- `S00` (complete) — lock this scope in decisions and handoff; do not edit
  `tasks.md` except for lifecycle status changes.
- `S01` (implementation complete; owner review pending) — Drizzle weather schema,
  manifest-backed run provenance, site/grid/sample/profile/feature identity,
  generated migration, constraints, indexes, and temporary migration tests.
- `S02` (complete; 89 Python tests, Ruff, wheel-resource, and repository checks passed) — shared atmospheric contracts, durable artifacts, manifests, versions and stage state machine.
- `S03` — implement the GFS request planner and immutable collector.
- `S04` — implement GFS GRIB parsing and T-017 canonical normalization.
- `S05` — implement deterministic canonical site/grid sampling and AGL policy.
- `S06` — implement source-aware validation, missingness and quarantine.
- `S07` — implement the versioned meteorological feature builder.
- `S08` — implement non-migrating SQLite persistence and the end-to-end GFS
  `fresh`/offline `resume` walking skeleton.
- `S09` — implement the ERA5 CDS collector/parser/normalizer through the same
  validation and persistence boundaries.
- `S10` — harden the GFS+ERA5 orchestration, offline replays, bounded live
  verification, documentation and final T-018 validation.

### T-018/S02 durable atmospheric protocol

S02 moves the sole machine-readable T-017 catalogue to the packaged resource
`services/ml/src/paragliding_forecasts_ml/ingestion/atmosphere/resources/weather-field-catalogue.json`.
There is no copied Python field enum: strict Pydantic contracts validate field
codes, canonical units, source IDs, and quality states against that resource at
runtime.

`data/raw/weather/<run-key>/` owns one immutable `request-plan.json`, native
payloads, and `manifest.json`. `data/interim/weather/<run-key>/` owns versioned
fingerprint directories for parser, normalizer, spatial alignment, validation,
feature building, and persistence evidence, plus an append-only hash-linked
state-event ledger. A `fresh` run initializes a new UUID directory; `resume` is
an offline mode that may only append a legal next event after verifying the
prior hashes. `partial` and `persisted` are terminal, failed parser/normalizer
stages may retry from the last complete stage, and only validation may emit or
resolve `quarantined`.

S02 declares source adapter, parser, normalizer, spatial aligner, validator,
feature builder, and persistence protocols plus independently versioned
component slots. It intentionally adds no weather CLI command, source request,
GRIB/NetCDF parser, or SQLite write. The synthetic proof covers the complete
request-to-persistence hash chain without network or database access.
### T-018/S01 schema and migration review state

The final weather section of `docs/T-012-flight-schema.drawio` is the S01
physical source of truth. It has fourteen tables: source/run/product identity;
approved site/grid sampling; canonical samples, pressure levels, repeatable
convection and interval measurements; derived feature snapshots; and per-field
provenance. Direct surface scalars stay on `weather_samples`; there is no
`weather_artifacts`, `weather_surface_samples`, `weather_profiles`, or generic
multi-point site table.

Key accepted semantics:

- `weather_ingestion_runs.ingestion_method` and `request_purpose` remain
  separate. Permission flags are run-level, not duplicated on
  `weather_sources`; component versions share the existing pipe-delimited
  `pipeline_version` convention.
- GFS and ERA5 do not receive a fabricated `model_version`. Dataset identity,
  `source_product_key`, reference/availability/valid times, manifest hash, and
  pipeline versions are the reproducibility contract.
- One approved weather coordinate exists per site. Dobrich uses the Kardam
  accepted-flight centroid `43.746321, 28.074025`; the site row remains the map
  centre. Multi-point regional aggregation is deferred.
- Samples do not repeat `site_id` or `grid_id`; those are reached through the
  footprint graph. Footprint nodes likewise do not repeat `grid_id` or an
  ordinal.
- Interval rows retain `source_step_start_hours` and
  `source_step_end_hours`. `quality_state` exists only per field in
  `weather_field_provenance`. Zero is a real value; missing/sentinel values use
  NULL plus their explicit provenance state.
- Convection rows may keep CAPE and CIN both NULL when their required per-field
  provenance rows say missing. Partial unique indexes make nullable
  parcel/layer identities deterministic.
- SQLite checks enforce row-local UUID, SHA-256, time, lifecycle, unit range,
  interval, ownership, and identity rules. Cross-row rules such as interpolation
  weights summing to one, same-grid footprint membership, correct
  point/neighbourhood role, and required interval/CAPE/CIN provenance remain
  mandatory validator/persistence-transaction checks.

`packages/database/drizzle/20260820160216_create_weather_foundation/` is one
coherent generated migration for the full FK graph. Its SQL was minimally
amended so all fourteen new tables are SQLite `STRICT`. It also renames the
populated flight `ingestion_runs` table to `flight_ingestion_runs` without a
rebuild. Legacy internal flight constraint/index names intentionally remain;
an initial generated draft tried to rebuild the parent table merely to rename
those objects and failed correctly against populated FK data, so that draft was
discarded and safely regenerated.

The migration contains no source/site/grid seed data. Approved site sampling
configs are pre-provisioned configuration; a missing config must fail preflight and
request review rather than being auto-created halfway through ingestion. No
`db:migrate` command has been run against the configured database, and nothing
from S01 is committed.
Temporary migration tests cover a fresh file, constraints, and an upgrade from
the four prior migrations with an existing linked flight row.

## Database and flight-data boundary

The migrated SQLite flight foundation contains `flight_sources`, `sites`,
`source_site_mappings`, `flight_ingestion_runs`, and `flight_records`. Preserve units,
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
| `f1032827-a98d-4c01-969e-e67b4885f90d` | First successful import: 267 accepted flights from the prior 2025/2026 collection; 1,200 seen, 664 rejected, 69 quarantined, 200 same-run duplicates removed. | Established the persistence slice and the first `flight_ingestion_runs` row. |
| `8d809838-3ff8-42ce-9977-3997cd2536bc` | Manual 2024 `fresh`, review/apply, then successful `resume` on 2026-08-11. 600 seen; 208 normalized candidates; 182 persisted accepted flights; 295 rejected; 26 quarantined; 97 same-run duplicates removed. | `ingestion_run_id=2`; validation snapshot `fbe9bc251bc07b287d16e2c2127c70daf0b781754ca871931bd6530680ea2204`; 26 quarantines were explicitly reviewed/rejected and `actionable_mapping_quarantine_count=0`. |

For the 2024 run, eight reviewed mappings were approved and inserted, while ten
proposals were rejected. The successful result used pipeline version
`xccontest-collector/3|xccontest-parser/2|xccontest-validation/2|xccontest-persistence/2`.
The raw manifest is complete, schema version 3, and covers season 2024/BG.

### T-018/S01 verification (uncommitted)

The final generated migration and compatibility rename were verified on
2026-08-20 without touching the configured local database:

- `npm.cmd run test`: database 25, contracts 15, API 82, and web 121 tests
  passed;
- `npm.cmd run build`, `npm.cmd run typecheck`, `npm.cmd run lint`,
  `npm.cmd run repo:check`, and database `db:check` passed;
- focused Prettier checks for every T-018 TypeScript/JSON file passed;
- `uv run --project services/ml pytest`: 77 tests passed after updating the
  existing XCContest persistence adapter to `flight_ingestion_runs`;
- `uv run --project services/ml ruff format --check` and `ruff check` passed;
- `git diff --check` passed and `docs/tasks.md` is unchanged.

The repository-wide `npm.cmd run format:check` still reports only the already
committed pre-T-018 snapshot
`packages/database/drizzle/20260811080029_add_browser_ui_ingestion_method/snapshot.json`.
The new snapshot passes focused formatting. The old applied snapshot was not
rewritten as unrelated cleanup.
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
