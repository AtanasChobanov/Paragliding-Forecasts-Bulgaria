# Data workspace

This directory defines local data zones without committing real datasets or
generated artifacts.

## Zones

- `raw/` - immutable source downloads or manually provided source files
- `external/` - third-party reference data not owned by this project
- `interim/` - normalized or partially processed data
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
- Use UTC internally for timestamps and preserve the source timezone when
  relevant.
- Include units in schemas and validate coordinate, date, distance-band, and
  missing-value assumptions.
- Keep committed test samples minimal, deterministic, and safe to redistribute.

Large files belong in external storage or a future artifact/data-versioning
solution, not in normal Git history.
