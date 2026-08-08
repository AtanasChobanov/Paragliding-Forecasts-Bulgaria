# Data and ML service

## Status

The permitted XCContest browser collector and its offline parser/normalizer are
implemented. The parser turns immutable rendered list artifacts into deduplicated
local staging records only; it does not match sites, update mappings, write
SQLite, or make source requests. Feature engineering, training, and prediction
entry points start in later Takts.

## Why Python exists in a TypeScript-first repository

Product behavior, HTTP transport, and the dashboard stay in TypeScript. Python
is used only where its scientific ecosystem is the practical choice:

- historical flight and weather ingestion;
- tabular and atmospheric feature engineering;
- `pandas`, `xarray`, NetCDF, and sounding workflows;
- transparent baseline and tree-based models;
- backtesting, calibration, and batch prediction.

The Node API remains the only browser-facing backend. The initial Python side
is a batch pipeline that writes documented, versioned outputs for the API to
read; it is not automatically a second HTTP service.

## Environment setup

From the repository root:

```powershell
uv sync --project services/ml
```

`uv` reads this project's `.python-version` and creates a local virtual
environment. The first successful dependency resolution should produce
`services/ml/uv.lock`; commit that lockfile for reproducible development.

Add dependencies through uv rather than editing an activated environment:

```powershell
uv add --project services/ml pandas
uv add --project services/ml --dev pytest
```

## Planned layout

```text
services/ml/
|-- src/paragliding_forecasts_ml/
|   |-- ingestion/
|   |   |-- common/
|   |   `-- xccontest/
|   |-- features/
|   |-- models/
|   |-- prediction/
|   |-- storage/
|   `-- validation/
|-- tests/
|-- pyproject.toml
`-- uv.lock
```

## Commands

Run the collector for one or more explicitly selected XCContest seasons:

```powershell
uv sync --project services/ml
uv run --env-file .env --project services/ml xccontest-collect --season 2025
uv run --env-file .env --project services/ml xccontest-collect --season 2025 --season 2024
```

It is headless by default. Use `--headed` (optionally with `--slow-mo-ms`) for
local UI inspection. Before creating a browser or artifact directory, the command opens the
Drizzle-migrated SQLite database in read-only mode and derives distinct ISO2 codes from
all `sites` rows, including inactive sites. `DATABASE_URL` precedence is `--database-url`,
then the process environment, then `file:./data/local/paragliding.db`; only relative
`file:` URLs below repository `data/` are accepted. The root `.env` is loaded by
`uv run --env-file .env`, not by a Python dotenv dependency.

The collector processes every requested `season × country` target sequentially in one
browser session, starting each target with `FAI3` (`PG *`) sorted by descending distance. If the first view is
saturated — a source-provided next page exists and its last distance is at least
100 km — it does not activate the pager or construct an offset URL. Instead it
uses the rendered exact `CCC`, `EN D`, `EN C`, `EN B`, and `EN A` controls. A
saturated exact category is split through every date offered by XCContest's
visible date control. If a category/date view is still saturated, the collector
captures the visible pilot, points, and airtime orderings in both directions as
best-effort supplementary evidence.

Every state transition is sequential and paced by at least three seconds; this
collector intentionally does not open parallel tabs. It writes nonempty exact
rendered `#flights` fragments under ignored `data/raw/xccontest/<run-key>/` and
progress/failure state under ignored `data/interim/xccontest/<run-key>/`. The
exact saved HTML fragment is the durable parser input and retains the source
fields without conversion. The ephemeral `RowObservation` model contains only
flight ID, distance, and launch country because those values drive collector
coverage, threshold, and country checks; it is not an ingestion-stage payload.

The in-memory `CollectionReport` is likewise only a compact command/log summary:
manifest relative path and hash, lifecycle, requested/completed scope summaries, and
aggregate counters. Per-artifact detail and target statuses exist only in the immutable
manifest; no raw root path, raw HTML, or row data is carried by the report.

Manifest schema v2 records the database-derived `all_sites` country scope, per-target country statuses, country-aware artifact paths, source URL, collector lifecycle timestamps,
completion/coverage status, category/date/sort scope, artifact hashes, per-view
row counts, qualifying-distance counts, and run-wide observed/distinct/repeated
flight-ID counts. The CLI also returns the repository-relative manifest path
and SHA-256 needed by the later `ingestion_runs` write. The checkpoint and
failure report carry the available observation counters. `--max-views` is a
fail-closed cap across the full run, rather than a pagination cap.

A run reports `incomplete` when a category/date view remains saturated after
all supplementary sort views. Those views can discover additional flight IDs,
but cannot prove that every qualifying row was exposed. Treat that manifest
status as a coverage warning, not as a successful complete sample.

Automated tests use a fake UI driver; they do not make live XCContest requests.
When a developer's browser environment cannot render the list table, stop and
run the command manually with `--headed`; do not bypass consent, Cloudflare,
CAPTCHA, login, or call undocumented backend endpoints directly.

Parse an already collected raw run without browser or network access:

```powershell
uv run --project services/ml xccontest-parse --run-key <uuid>
```

Parser v2 accepts legacy BG-only manifests and complete manifest-v2 runs. For
v2 it verifies country/season scope, target completion, artifact and run
counters, every SHA-256, and the actual saved row/qualifying counts before
normalizing the numeric flight ID, UTC takeoff timestamp, launch evidence,
route, distance, duration, and both supported XCContest detail URL forms. It
applies the 100--2000 km staging range, removes identical same-run duplicate
records, and keeps every contributing raw artifact reference. Unknown or
ambiguous launch evidence, site mapping approval, and SQLite persistence remain
outside this command.

## Reviewed site mapping and validation

Create review proposals from a parser-v2 run without source access or SQLite writes:

```powershell
uv run --env-file .env --project services/ml xccontest-site-mappings propose --run-key <uuid>
```

The command writes non-overwriting `site-mapping-v2/mapping-proposals.jsonl` under the
matching ignored interim run directory. A proposal may be based on the exact XCContest
site token, a normalized source name, or a source point. Coordinates are compared with
Haversine distance against every same-country `sites` row with a configured
`catchment_radius_km`: the six launch areas use 5 km and Dobrich region uses 30 km.
A point inside exactly one radius is only a review suggestion; overlaps and unknown
locations remain quarantined. No external geocoding is used.

A human reviews a local JSONL file by adding `decision`, `site_slug`, and, for an
`approved` mapping, `verification_reference`. Apply that reviewed file in one SQLite
transaction:

```powershell
uv run --env-file .env --project services/ml xccontest-site-mappings apply --review-file <mapping-decisions.jsonl>
```

`provisional` and `retired` mappings are never accepted. Incorrect mappings are retired
and replaced; source evidence is not silently reassigned to another site.

Validate an existing parser-v2 run against only approved mappings:

```powershell
uv run --env-file .env --project services/ml xccontest-validate --run-key <uuid>
```

The validator writes non-overwriting `validation-v1/<mapping-snapshot-sha256>/`
outputs: `accepted-flights.jsonl`, `site-quarantine.jsonl`, and
`validation-report.json`. It does not call XCContest or create `ingestion_runs` or
`flight_records`; the later persistence slice owns that transaction. Re-run validation
after mapping approvals to obtain a new mapping-snapshot output.
The collector and parser are separate commands today so a failed downstream
stage can resume from immutable raw evidence without another source request. A
future top-level ingestion command may orchestrate collector, parser,
validation, and persistence in one invocation, but each stage must still pass a
run key plus durable artifacts/staging outputs. It must not depend on ephemeral
`RowObservation` instances surviving in one Python process.

Other Python modules remain planned:

```powershell
uv run --project services/ml pytest
uv run --project services/ml python -m paragliding_forecasts_ml.ingestion
uv run --project services/ml python -m paragliding_forecasts_ml.prediction
```

Do not add placeholder modules that report success without doing the documented
work.

## Integration contract

Python outputs must carry source, units, timestamps, site identifiers, model or
pipeline version, confidence, and data status. Prefer language-neutral storage
or serialization. Avoid coupling the Node API to Python internals or pickled
objects.

For Takt 2, Python reads permitted XCContest inputs into immutable raw artifacts,
parses them into source records, normalizes and validates them, resolves a
canonical project site, and writes accepted flight records to the SQLite schema
owned by `packages/database`. Python is a non-migrating client of that schema:
Drizzle/Drizzle Kit own all DDL and migrations. Ambiguous or rejected records
remain as ignored interim/quarantine outputs rather than entering the canonical
flight table.

T-013's collector slice owns source UI control and raw artifact retention. It
does not drop repeated flight IDs because the umbrella PG view deliberately
overlaps exact-category and rescue-sort views; its repeated-observation count
is operational coverage metadata. The offline `xccontest-parse --run-key <uuid>`
command validates legacy BG-only and v2 manifests plus every artifact hash, then
writes non-overwritable `parser-v2` outputs under
`data/interim/xccontest/<run-key>/`: deduplicated `normalized-flights.jsonl`,
`parse-rejections.jsonl`, and `parse-report.json`. Equal same-run IDs become one
record with all artifact references; conflicting IDs become one conflicted
candidate without a selected value. It never writes or proposes
`source_site_mappings`, retains pilot identity, calls XCContest, or writes
SQLite. The T-013 validation/site-mapping slice now uses durable parser-v2 JSONL,
reviewed `source_site_mappings`, and versioned accepted/quarantine outputs; persistence
still remains a later T-013 slice. T-014 owns cross-run idempotency and persisted
traceability. T-015 owns small, sanitized, permitted frozen fixtures; fixtures are not
the live/raw dataset.

## Collector versioning policy

Every edit that changes collector behaviour, browser/source interaction, retained raw
evidence, run metadata, or the CLI contract must increment `collector_version`. Every
edit that changes manifest fields, shape, semantics, or compatibility must increment
`manifest_schema_version` as well. A collector commit or pull request without the
applicable version bump, focused tests, and corresponding README/decision update is
incomplete. Current values are `xccontest-collector/2` and manifest schema v2. Current
version identifiers live in `ingestion/xccontest/versions.py`; manifest compatibility
policy remains in `manifest.py`.

Ignored raw artifacts and their manifests are immutable: later parser work must support
legacy BG-only manifests as well as v2 country-aware manifests rather than rewriting
historical evidence.

## Parser versioning policy

The parser version is independent of the raw manifest schema version. Any
change to accepted raw compatibility, selectors, parsing or normalization
behaviour, output fields/semantics, deduplication/conflict handling, staging
layout, or parser CLI contract must increment `PARSER_VERSION` and use a new
non-overwriting `parser-vN` output directory. The same change must include
focused legacy/current-manifest tests and update this README and the handoff. The
staging directory is derived from the parser revision in `versions.py`, so the version
identifier and `parser-vN` directory cannot drift. Current parser v2 accepts legacy/v1
and complete manifest-v2 inputs.

## Reproducibility and data safety

- Pin resolved dependencies in `uv.lock`.
- Keep raw downloads, local databases, caches, and trained artifacts out of Git.
- Commit only small, licensed, sanitized samples needed for repeatable tests.
- Preserve source URLs and quality notes when the source permits it.
- Report 100/200/300 km validation separately and avoid false precision for
  sparse labels.
