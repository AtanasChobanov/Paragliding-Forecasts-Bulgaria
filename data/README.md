# Data workspace

This directory defines local data zones without committing real datasets or
generated artifacts.

## Zones

- `raw/` - immutable source downloads or manually provided source files; an
  ingestion run owns its exact XCContest input here before parsing
- `external/` - third-party reference data not owned by this project and not
  captured as one ingestion run, such as later reference datasets
- `interim/` - normalized, partially processed, rejected, or quarantined data
- `processed/` - model-ready tables and feature sets
- `models/` - trained model artifacts, metrics bundles, and serialized outputs
- `local/` - local SQLite databases and other runtime state
- `samples/` - small, sanitized, frozen fixtures that may be committed for tests

All zones except `samples/` are ignored by `data/.gitignore`. Their `.gitkeep`
files preserve the intended layout only.

## Rules

- Never commit credentials, tokens, private pilot data, or data prohibited by a
  source's terms.
- Keep source URLs, retrieval times, licensing/attribution notes, and quality
  flags beside ingested records when permitted.
- Treat raw inputs as immutable; derive new versions into `interim/` or
  `processed/`.
- Store run-captured XCContest payloads under `raw/xccontest/<run-id>/`, with
  an immutable `manifest.json` sidecar. The manifest inventories each artifact's
  safe relative path, redacted source URL, retrieval time, content hash, and
  optional ETag; the corresponding ingestion run records permission basis and
  pipeline version. Re-fetching creates a new artifact rather than overwriting
  an old one.
- Store normalized accepted/rejected/quarantine JSONL and run reports under
  `interim/xccontest/<run-id>/`. These artifacts are not the canonical
  application store; accepted records are persisted in the ignored SQLite file
  under `local/` after validation and site matching.
- Use UTC internally for timestamps and preserve the source timezone when
  relevant.
- Include units in schemas and validate coordinate, date, distance-band, and
  missing-value assumptions.
- Keep committed test samples minimal, deterministic, and safe to redistribute.

Large files belong in external storage or a future artifact/data-versioning
solution, not in normal Git history.
