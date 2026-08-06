# Data and ML service

## Status

The XCContest collector boundary is implemented for the explicitly permitted
browser UI workflow. It captures immutable rendered-list artifacts only; it
does not parse flights, normalize records, assign sites, deduplicate, or write
to SQLite. Feature engineering, training, and prediction entry points start in
later Takts.

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
browser observation keeps the raw flight date, displayed takeoff time and UTC
offset, launch name/country/search URL, route label, distance, duration, numeric
flight ID, and canonical detail URL needed by the next parser slice. Optional
values remain missing for short source rows; the collector does not normalize
them or accept them as database records.

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
is operational coverage metadata, not a canonical duplicate decision. The
T-013 parser/normalizer must collapse same-run observations by XCContest
`source_flight_id` before site assignment while retaining every contributing
artifact reference. Validation, site assignment, and SQLite import remain later
explicitly planned T-013 slices. T-014 owns hardened cross-run idempotency,
conflicting-duplicate detection, and persisted source traceability. T-015 owns
small, sanitized, permitted frozen fixtures that test the parser offline;
fixtures are not the live/raw dataset.

## Collector versioning policy

Every edit that changes collector behaviour, browser/source interaction, retained raw
evidence, run metadata, or the CLI contract must increment `collector_version`. Every
edit that changes manifest fields, shape, semantics, or compatibility must increment
`manifest_schema_version` as well. A collector commit or pull request without the
applicable version bump, focused tests, and corresponding README/decision update is
incomplete. Current values are `xccontest-collector/2` and manifest schema v2.

Ignored raw artifacts and their manifests are immutable: later parser work must support
legacy BG-only manifests as well as v2 country-aware manifests rather than rewriting
historical evidence.
## Reproducibility and data safety

- Pin resolved dependencies in `uv.lock`.
- Keep raw downloads, local databases, caches, and trained artifacts out of Git.
- Commit only small, licensed, sanitized samples needed for repeatable tests.
- Preserve source URLs and quality notes when the source permits it.
- Report 100/200/300 km validation separately and avoid false precision for
  sparse labels.
