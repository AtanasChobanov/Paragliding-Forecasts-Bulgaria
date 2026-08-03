# Data and ML service

## Status

The Python project metadata and source boundary are scaffolded. Data ingestion,
feature engineering, training, and prediction entry points start in later
Takts.

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

## Planned commands

Exact commands will be added with their executable modules. Expected patterns:

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

T-013 owns the first parser/import pipeline. T-014 hardens duplicate and source
traceability behavior. T-015 adds small, sanitized, permitted frozen fixtures
that test the parser offline; fixtures are not the live/raw dataset.

## Reproducibility and data safety

- Pin resolved dependencies in `uv.lock`.
- Keep raw downloads, local databases, caches, and trained artifacts out of Git.
- Commit only small, licensed, sanitized samples needed for repeatable tests.
- Preserve source URLs and quality notes when the source permits it.
- Report 100/200/300 km validation separately and avoid false precision for
  sparse labels.
