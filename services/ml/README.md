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

Run a new end-to-end XCContest ingestion pipeline:

```powershell
uv run --env-file .env --project services/ml xccontest-ingest fresh `
  --season 2024 `
  --headed `
  --policy-file data/local/xccontest-import-policy.json
```

`fresh` preserves the explicit human mapping-review gate. `propose` is automatic and
read-only; `apply` is always a human-reviewed SQLite write. If validation finds a mapping-actionable
quarantine without a matching reviewed rejection, it exits with `awaiting_mapping_review` (exit
code 2) before persistence. Copy/review/apply the generated `site-mapping-v2` decisions file, then
continue entirely offline:

```powershell
uv run --env-file .env --project services/ml xccontest-ingest resume `
  --run-key <uuid> `
  --policy-file data/local/xccontest-import-policy.json
```

`resume` reuses valid parser, proposal, and current mapping-snapshot validation artifacts; it
never opens a browser. Persistence then compares each accepted record with the canonical SQLite
flight of the same source identity. Exact repeats revalidate, known values can be enriched, and
conflicts stop with `awaiting_reconciliation_review` (exit code 2) before any database write.
Follow the detailed [T-014 reconciliation and review workflow](../../docs/T-014-flight-reconciliation.md)
to resolve those JSONL decisions. `--persist-approved-only` remains an explicit exceptional path
for the accepted subset; a later reviewed `resume` reconciles the same run rather than losing the
ability to add remaining records. The separate `xccontest-collect`, `xccontest-parse`,
`xccontest-site-mappings`, `xccontest-validate`, and `xccontest-persist` commands remain supported
for focused collection, review, replay, and recovery.
Run the collector for one or more explicitly selected XCContest seasons:

```powershell
uv sync --project services/ml
uv run --env-file .env --project services/ml xccontest-collect --season 2025
uv run --env-file .env --project services/ml xccontest-collect --season 2025 --season 2024
```

It is headless by default. Use `--headed` for local UI inspection. `--slow-mo-ms` is
only a Playwright debugging slowdown, not a rate-limit control. Source-changing browser
operations wait 30 seconds by default. `--source-delay-seconds` may increase that delay;
values from 3 up to but excluding 30 require the explicit
`--acknowledge-rate-limit-risk` flag. No value below 3 is accepted. Before creating a
browser or artifact directory, the command opens the
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

Every navigation and rendered-control transition is sequential and source-paced; this
collector intentionally does not open parallel tabs or retry a failed source operation. A
failed navigation response, challenge, or missing rendered table stops the run for manual
inspection. It writes nonempty exact
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

Manifest schema v3 records the database-derived `all_sites` country scope, per-target country statuses, country-aware artifact paths, source URL, collector lifecycle timestamps,
completion/coverage status, the configured source-pacing delay and risk acknowledgement,
category/date/sort scope, artifact hashes, per-view row counts, qualifying-distance counts,
and run-wide observed/distinct/repeated
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

Parser v2 accepts legacy BG-only manifests plus complete manifest-v2 and manifest-v3 runs. For
v2/v3 it verifies country/season scope, target completion, artifact and run
counters, every SHA-256, and the actual saved row/qualifying counts before
normalizing the numeric flight ID, UTC takeoff timestamp, launch evidence,
route, distance, duration, and both supported XCContest detail URL forms. It
applies the 100--2000 km staging range, removes identical same-run duplicate
records, and keeps every contributing raw artifact reference. Unknown or
ambiguous launch evidence, site mapping approval, and SQLite persistence remain
outside this command.

## Reviewed site mapping and validation

This is a deliberately human-reviewed boundary. A proposal is evidence to inspect,
not permission for the program to assign flights to a project site. No external
geocoding is used and `propose` never changes SQLite.

### 1. Create proposals

Start with a completed parser-v2 run and a migrated local database. From the repository
root, use the normal `.env` database configuration (or pass `--database-url`):

```powershell
npm.cmd run db:migrate --workspace @paragliding-forecasts/database
uv run --env-file .env --project services/ml xccontest-site-mappings propose --run-key <uuid>
```

For a run key such as `f1032827-a98d-4c01-969e-e67b4885f90d`, the command writes its
read-only output here:

```text
data/interim/xccontest/f1032827-a98d-4c01-969e-e67b4885f90d/site-mapping-v2/
  mapping-proposals.jsonl
  proposal-report.json
```

The `data/interim/` directory is ignored by Git. `mapping-proposals.jsonl` is immutable
evidence: do not edit it. It contains one JSON object per line (JSONL), grouped by the
strongest available source evidence. Copy it to a sibling review file, then edit only the
copy:

```powershell
$runKey = 'f1032827-a98d-4c01-969e-e67b4885f90d'
$mappingDir = "data/interim/xccontest/$runKey/site-mapping-v2"
Copy-Item "$mappingDir/mapping-proposals.jsonl" "$mappingDir/mapping-decisions.jsonl"
```

Use this recommended location and filename so the proposed evidence and the human
review stay together. The apply command accepts a file elsewhere too, but the review
file must remain local/ignored: it can contain real source evidence and reviewer notes.

A proposal exposes the evidence to review:

- `key_type` and its matching value identify exactly what will be persisted. Never
  change either to “correct” a source value; reject it or create a separate reviewed
  mapping instead.
- `source_takeoff_id`, `source_site_token`, and `normalized_name` use a non-empty
  string in `key_value`. Keep the proposed value exactly as written. A site token is an
  opaque XCContest token, not a human-readable slug. A normalized name is already
  Unicode-normalized, case-folded, and whitespace-collapsed; do not replace it with
  the display name.
- `source_point` uses `key_value: null` and the exact numeric
  `point_latitude_deg`/`point_longitude_deg` from the proposal (rounded to at most six decimal places).
  Do not round, swap, or otherwise alter the pair.
- `source_display_names`, `sample_source_flight_ids`, `seasons`, and
  `catchment_suggestions` are review context. They are not mapping keys. A unique
  catchment suggestion is still only a suggestion; independently verify the location.
- `recommendation` is `inside_unique_catchment`, `ambiguous_catchment`, or
  `review_required`. None of these is an automatic approval.

### 2. Complete each review decision

Keep one JSON object per line; do not wrap lines in `[` / `]` and do not put commas
between lines. It is safe, and useful for traceability, to retain every field copied from
the proposal. `apply` ignores proposal-only context fields. Add the fields below to every
line you retain.

| Field | Required for | Exact format and meaning |
| --- | --- | --- |
| `decision` | Every retained line | One of `approved`, `provisional`, or `rejected`. This is the reviewer’s decision, not a proposal recommendation. |
| `site_slug` | `approved`, `provisional` | Exact existing canonical `sites.slug` value, such as `sopot`. Use the `site_slug` in a verified catchment suggestion when applicable; otherwise obtain the canonical slug from the sites table. |
| `verification_reference` | `approved` | Non-empty audit reference describing how the reviewer established the mapping. Use the consistent template `<evidence-kind>:<stable-reference>; reviewed-by:<initials-or-id>; reviewed-on:<YYYY-MM-DD>`. Examples: `xccontest-detail:https://www.xcontest.org/world/en/flights/detail:...; reviewed-by:AB; reviewed-on:2026-08-10` or `manual-coordinate-check:site-survey-2026-07; reviewed-by:AB; reviewed-on:2026-08-10`. This is an auditable string, not a URL-only field. |
| `verified_at_utc` | Optional for `approved` | UTC timestamp exactly `YYYY-MM-DDTHH:MM:SSZ`, for example `2026-08-10T14:30:00Z`. If omitted for an approved decision, `apply` records its current UTC time; include it when the review time itself matters. |
| `source_display_name` | Optional | One original human-readable launch label, for example `Sopot`. It aids later audit but is never used as a matching key. |
| `notes` | Optional | Short plain-text reviewer rationale, uncertainty, or pointer to supporting evidence. Do not put secrets or pilot-identifying data here. |

A `provisional` mapping is stored but will never allow a flight through validation. Use
it when the hypothesis is useful to preserve but has not met the approval standard; omit
`verification_reference` and `verified_at_utc`. A `rejected` line writes no mapping and
needs no `site_slug`; retain `proposal_id` and add `notes` so the decision remains
traceable in the local file.

`retired` is a database status for historical mappings; it is **not** an accepted
`decision` value for this command. Do not edit SQLite manually to retire or reassign an
active mapping. The current apply command rejects a conflicting active key and rolls back
the entire file; correction/retirement needs an explicit follow-up workflow.

### 3. Valid examples

The first example approves an opaque source token after manual verification. It is a
complete, ready-to-apply JSONL line; additional copied proposal fields are allowed but
not required:

```json
{"proposal_id":"keep-the-proposal-id-for-local-traceability","source":"xccontest","key_type":"source_site_token","key_value":"exact-token-from-proposal","source_display_name":"Sopot","decision":"approved","site_slug":"sopot","verification_reference":"xccontest-detail:https://www.xcontest.org/world/en/flights/detail:...; reviewed-by:AB; reviewed-on:2026-08-10","verified_at_utc":"2026-08-10T14:30:00Z","notes":"Launch page and source token were checked against the Sopot canonical site."}
```

A coordinate mapping must preserve its exact pair and has no `key_value`:

```json
{"proposal_id":"keep-the-proposal-id-for-local-traceability","source":"xccontest","key_type":"source_point","key_value":null,"point_latitude_deg":42.68733,"point_longitude_deg":24.749962,"source_display_name":"Sopot","decision":"provisional","site_slug":"sopot","notes":"Inside the configured 5 km catchment, but source-side evidence still needs review."}
```

A rejected proposal can be minimal:

```json
{"proposal_id":"keep-the-proposal-id-for-local-traceability","decision":"rejected","notes":"Generic launch name has no reliable evidence linking it to a canonical site."}
```

### 4. Apply the reviewed file

Review the entire file before applying it. The command validates all lines and uses one
SQLite transaction: any invalid line, unknown `site_slug`, missing approval reference, or
conflicting active mapping aborts the whole file without a partial write.

```powershell
$runKey = 'f1032827-a98d-4c01-969e-e67b4885f90d'
uv run --env-file .env --project services/ml xccontest-site-mappings apply `
  --review-file "data/interim/xccontest/$runKey/site-mapping-v2/mapping-decisions.jsonl"
```

The output reports `inserted`, `promoted`, `unchanged`, and `rejected` counts. `approved`
rows become reusable `source_site_mappings` records; a matching existing `provisional`
row for the same site can be promoted to `approved`. Re-run validation after successful
approvals so it reads the new mapping snapshot.
Validate an existing parser-v2 run against only approved mappings:

```powershell
uv run --env-file .env --project services/ml xccontest-validate --run-key <uuid>
```

The validator writes non-overwriting `validation-v2/<mapping-snapshot-sha256>/`
outputs: `accepted-flights.jsonl`, `site-quarantine.jsonl`, and
`validation-report.json`. It does not call XCContest or create `ingestion_runs` or
`flight_records`; the later persistence slice owns that transaction. Re-run validation
after mapping approvals to obtain a new mapping-snapshot output.
The top-level `xccontest-ingest` command orchestrates the same collector, parser, mapping,
validator, and persistence boundaries without passing ephemeral `RowObservation` values. It
writes the same non-overwriting stage outputs in the same locations. The conditional mapping
review gate stops before persistence, preserving the run key and all artifacts for offline
`resume`; it never applies mappings automatically.

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


### Persist validated XCContest flights

`xccontest-persist` is the final T-013 stage. It does not contact XCCont### Persist and reconcile validated XCContest flights

`xccontest-persist` is an offline final stage: it never contacts XCContest or invokes collection,
parsing, or validation. Apply the committed database migrations, validate a run after required
mapping decisions, and create the ignored policy file described below before invoking it:

```powershell
npm.cmd run db:migrate --workspace @paragliding-forecasts/database
uv run --env-file .env --project services/ml xccontest-persist `
  --run-key <uuid-v4> `
  --validation-snapshot <64-lowercase-hex-sha256> `
  --policy-file data/local/xccontest-import-policy.json
```

The policy JSON must contain exactly these booleans and non-empty permission provenance:

```json
{
  "permission_basis": "written_permission",
  "permission_reference": "Written XCContest permission held by the project owner; confirmed 2026-08-10",
  "model_training_allowed": true,
  "operational_use_allowed": true
}
```

`permission_basis` is one of `written_permission`, `source_terms`, `owner_export`,
`official_api_terms`, or `pilot_provided`. The command verifies the raw manifest, parser and
validation reports/files, their SHA-256 values, approved mapping snapshot, current mapping rows,
record fields, and source identity before opening its transaction.

A successful reconciliation writes a canonical `flight_records` row only when no row already
exists for `(source_id, source_flight_id)`. Existing rows are revalidated, enriched, or preserved
under the deterministic T-014 policy. A material contradiction (source URL, site mapping, takeoff
time, distance, two concrete durations/track URLs, or two known route types) creates a local,
immutable proposal artifact and returns `awaiting_reconciliation_review`. It changes neither
flights nor runs until a complete reviewed decisions JSONL file is supplied and `resume` or this
command is rerun.

The full comparison policy, decision-file contract, quality-note JSON schema, data fields, and
troubleshooting are documented in [T-014 reconciliation and review workflow](../../docs/T-014-flight-reconciliation.md).
The concise outcomes in the JSON report are `applied` (with per-outcome counts) or `no_op` for an
exact already-applied replay. The direct persist command returns exit code 0 for `succeeded`, 2
for an outstanding reconciliation review, and 1 for failed validation or invalid decision evidence.
