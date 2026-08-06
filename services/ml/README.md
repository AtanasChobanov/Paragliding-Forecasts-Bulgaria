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
uv run --project services/ml xccontest-collect --season 2025
uv run --project services/ml xccontest-collect --season 2025 --season 2024
```

It is headless by default. Use `--headed` (optionally with `--slow-mo-ms`) for
local UI inspection. The collector selects the season and `BG` country, then
starts with `FAI3` (`PG *`) sorted by descending distance. If the first view is
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
manifest records the category, date and sort for every artifact. `--max-views`
is a fail-closed cap across the full run, rather than a pagination cap.

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

T-013's collector slice owns source UI control and raw artifact retention. Its
parser, normalizer, validation, site assignment, and SQLite import must be
implemented as a later explicitly planned T-013 slice. T-014 owns canonical
duplicate and persisted source-traceability behavior. T-015 owns small,
sanitized, permitted frozen fixtures that test the parser offline; fixtures are
not the live/raw dataset.

## Reproducibility and data safety

- Pin resolved dependencies in `uv.lock`.
- Keep raw downloads, local databases, caches, and trained artifacts out of Git.
- Commit only small, licensed, sanitized samples needed for repeatable tests.
- Preserve source URLs and quality notes when the source permits it.
- Report 100/200/300 km validation separately and avoid false precision for
  sparse labels.
