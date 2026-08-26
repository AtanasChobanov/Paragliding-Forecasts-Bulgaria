# Project Handoff

## Purpose and source of truth

This is the concise operational snapshot for the next T-018 implementation
slice, not a project history. Read, in order:

1. `AGENTS.md` for repository rules and workflow.
2. `docs/tasks.md` for the T-018 lifecycle status and ticket scope.
3. This handoff for the implemented T-018 slice boundaries.
4. The relevant sections of `docs/project-brief.md` and `docs/architecture.md`
   for product and system constraints.
5. DEC-031 through DEC-037 in `docs/decisions.md` for accepted weather-source,
   schema, protocol, parser, and spatial-sampling decisions.
6. Git history and the owning code/tests for detailed prior implementation and
   validation evidence.

Record durable design choices in `docs/decisions.md`, task status in
`docs/tasks.md`, and only the current operational state here.

## Current state (2026-08-26)

| Field | Value |
| --- | --- |
| Branch | `feature/T-018-weather-ingestion` |
| Task status | `T-018` is In Progress; S01–S06 are complete, S07–S10 remain. |
| Next focus | Implement S07 versioned feature building from S06 accepted artifacts; quarantines must remain blocked. |
| Local storage | SQLite selected by `DATABASE_URL`; local databases, raw source data, and interim artifacts are ignored. |
| Migrations | Weather foundation, sampling/elevation configuration, and provider-PBL-AGL are applied locally. The committed GFS/ERA5 source-registry migration must be applied with `db:migrate` before `weather-validate`. |

## T-018 scope and non-negotiable boundaries

T-018 owns the source-neutral SQLite weather schema and complete GFS and ERA5
pipeline: immutable raw artifacts/manifests, source parsers, canonical
normalization, deterministic site/grid sampling, validation/quarantine,
versioned feature building, and idempotent SQLite persistence. Do not add inert
placeholder collectors.

- GFS is the sole exact-forecast source in this phase, for historical and
  current/future forecast cohorts. Select a complete named run and retain its
  run/availability/retrieval/valid/lead/grid provenance. Do not substitute a
  different model when a run is unavailable; retain the last successful GFS
  result and expose its age.
- ERA5 is a separately collected long-history reanalysis baseline, never a
  live or row-level fallback for GFS. Forecast, reanalysis, and observation
  remain distinct source kinds. Product use of ERA5 requires the applicable
  Copernicus/ECMWF attribution.
- ICON-EU, IFS HRES, CERRA, and IGRA are outside this implementation scope.
  They require their own accepted source decision and adapter; IGRA is T-019.
- Preserve units, source/model/run/valid/lead provenance, confidence, and
  explicit quality/missing states. Do not silently convert a missing or
  sentinel value into a physical value.

## T-018 implementation slices

- `S01` (complete) — Drizzle weather schema, manifest-backed run provenance,
  site/grid/sample/profile/feature identity, generated migration, constraints,
  and indexes.
- `S02` (complete) — shared atmospheric contracts, durable artifacts,
  manifests, component versions, and stage state machine.
- `S03` (complete) — GFS request planner and immutable collector.
- `S04` (complete) — GFS GRIB parsing and T-017 canonical normalization.
- `S05` (complete) — deterministic canonical site/grid sampling and AGL policy.
- `S06` (complete) — source-aware validation, missingness, and quarantine.
- `S07` — versioned meteorological feature builder.
- `S08` — non-migrating SQLite persistence and end-to-end GFS `fresh`/offline
  `resume` walking skeleton.
- `S09` — ERA5 CDS collector/parser/normalizer through the same validation and
  persistence boundaries.
- `S10` — GFS+ERA5 orchestration hardening, offline replay, bounded live
  verification, documentation, and final T-018 validation.

## Prior T-018 slice handoff

### S01 — schema and migration boundary

The final weather section of `docs/T-012-flight-schema.drawio` is the physical
schema source of truth. Drizzle is the only DDL/migration owner. It defines
fourteen weather tables for source/run/product identity; approved site/grid
sampling; canonical samples, pressure levels, repeatable convection and
interval measurements; derived feature snapshots; and per-field provenance.
There is no `weather_artifacts`, `weather_surface_samples`, `weather_profiles`,
or generic multi-point site table.

Important semantics:

- GFS and ERA5 have no fabricated `model_version`; dataset identity,
  `source_product_key`, reference/availability/valid times, manifest hash, and
  pipeline versions provide reproducibility.
- One approved weather coordinate exists per site. Dobrich uses the Kardam
  accepted-flight centroid; the canonical site coordinate remains the map
  centre. Multi-point regional aggregation is deferred.
- Direct scalars stay on `weather_samples`; samples and footprint nodes do not
  repeat `site_id`/`grid_id`. Field `quality_state` belongs only in
  `weather_field_provenance`. Zero is physical; missing/sentinel values are
  `NULL` with explicit provenance.
- SQLite enforces local identity/shape rules. Cross-row rules—including
  interpolation weights, footprint membership, roles, and required
  provenance—are validator/persistence-transaction responsibilities.
- The weather foundation, approved sampling-config, provider-PBL-AGL, and
  Copernicus-elevation migrations are reviewed/applied locally. Never alter an
  applied migration; add a reviewed migration for any schema/data change.

### S02 — durable atmospheric protocol

The sole machine-readable T-017 field catalogue is the packaged resource
`services/ml/src/paragliding_forecasts_ml/ingestion/atmosphere/resources/weather-field-catalogue.json`.
Strict Pydantic contracts validate field codes, canonical units, source IDs,
and quality states against it at runtime; there is no copied Python field enum.

`data/raw/weather/<run-key>/` owns immutable `request-plan.json`, native
payloads, and `manifest.json`. `data/interim/weather/<run-key>/` owns
versioned/fingerprinted parser, normalizer, spatial, validation, feature, and
persistence evidence plus an append-only hash-linked state-event ledger.
`fresh` creates a UUID layout; offline `resume` may append only a legal next
event after prior hashes are verified. `partial` and `persisted` are terminal;
failed parser/normalizer stages may retry from the last complete state; only
validation may emit or resolve `quarantined`.

S02 declares separately versioned source-adapter, parser, normalizer, spatial
aligner, validator, feature-builder, and persistence protocols. It creates no
source request, parser, or SQLite write by itself.

### S03/S04 — GFS collection, parsing, and normalization

GFS collection, parsing, and normalization append only their legal raw,
parsed, and normalized state boundaries. The GFS parser uses explicit
regular-latlon grid geometry and scan order, static model orography, distinct
multi-valid-time artifact identities, and per-time/per-level U/V derivation.
GUST is unsupported; orography is terrain evidence, not a canonical weather
field. Preserve native missing bitmap/sentinel metadata as explicit missingness.

### S05 canonical site/grid sampling handoff

S05 is implemented. Seven committed sampling configs are present before
ingestion: six retain the canonical site coordinate and Dobrich uses the
reviewed Kardam coordinate `43.746321, 28.074025`. A missing config or reviewed
elevation fails preflight; collection and sampling never create configuration
rows. The configured local migration was applied and a second migrator run was
idempotent.

`copernicus-elevations --allow-live-network` is the explicit repeatable review
command for all seven coordinates. It reads OAuth credentials from the ignored
root `.env`, samples Copernicus DEM GLO-30 bilinearly as EGM2008 orthometric MSL
height, writes an ignored JSON artifact, and never writes SQLite. Two
consecutive live calls produced byte-identical output SHA-256
`0b517638eec1ea0f5048eaa5626aeaa9b23cfda87926f2014285f0e652fb4329`.
The seven accepted values and reference are pinned by a guarded data migration;
a later provider difference requires review and a new migration, not refresh or
resume behavior.

The packaged `canonical-site-sampling-policy-v1` implements strict bilinear
point sampling and an inclusive physical 50 km Haversine neighbourhood. Nearest
sampling is not implemented. A missing positive-weight bilinear node yields an
explicit missing value without weight renormalization. U/V are interpolated
before speed/direction are derived. The neighbourhood artifact retains MSL
pressure, surface U/V, and 925 hPa U/V nodes for later S07 spatial features;
S05 does not invent pressure-gradient, convergence, or divergence formulas.

Every sample reports site elevation, interpolated GFS model terrain, and signed
plus absolute mismatch. Pressure-level geopotential height remains MSL evidence;
site-AGL and model-AGL are derived, and a level below either terrain reference
is excluded with an auditable reason. Coarse-model terrain is never hidden or
substituted for reviewed site elevation.

`gfs-sample --run-key <uuid>` is offline-only, reads SQLite read-only, and
consumes only a complete normalized event. It appends the spatial boundary. Its
fingerprint covers the normalized manifest, grid/orography, reviewed config
snapshot, packaged policy, footprints, and version. Integration tests prove
byte-identical samples/fingerprints across independent roots, multi-valid-time
behavior, terrain diagnostics, below-terrain exclusion, no network, and no
database mutation. `sample_identity_key` is artifact-only, not a database
column. Provider PBL AGL storage is separate on `weather_samples`; it is not
the derived PBL AGL feature field.

### S06 implementation guardrails

S06 validates the immutable S05 spatial artifacts and their explicit
missing/exclusion states. It must not recompute footprints, renormalize missing
bilinear contributions, conceal terrain mismatch, replace terrain references,
or introduce S07's radius-derived meteorological formulas. Quarantine is the
only stage allowed to emit or resolve `quarantined`; retain enough source and
artifact provenance for every validation result to be auditable and replayable
offline.

### S06 — source-aware validation and quarantine

`weather-validate --run-key <uuid>` is offline-only and uses SQLite read-only
only to retrieve the active GFS/ERA5 registry row. It hashes that exact row and
the packaged source-aware policy into the immutable validator boundary, verifies
the spatial-to-raw hash chain, and writes accepted, missing, quarantined,
report, snapshot, and stage-manifest evidence. It returns `0` for complete, `2`
for quarantined, and `1` for operational/hash-chain failure. The command reuses
an existing validated boundary without a duplicate event.

S06 owns coverage disposition. GFS has a required lead and 925/850/700 hPa
core profile policy; ERA5 has no lead and requires 1000--700 hPa profiles. No
invented model ID/version, captured HTTP header, manual alias approval, or
endpoint override is used. `weather_sources` is a registry/allow-list and
provenance snapshot; adapters retain their pinned transport endpoints.

## Verification baseline

Final S05 verification on 2026-08-24 passed ML Ruff check and format-check,
all 130 ML tests, database 28 tests, contracts 15 tests, API 82 tests, web 121
tests, root build/typecheck/lint, Drizzle `db:check`, idempotent `db:migrate`,
repository structure, focused Prettier, and `git diff --check`.

The root format check reports only the pre-existing committed
`20260811080029_add_browser_ui_ingestion_method/snapshot.json`; all new T-018
files pass focused formatting.

## Routine commands

From repository root:

```powershell
npm.cmd install
uv sync --project services/ml
Copy-Item .env.example .env
npm.cmd run repo:check
```

For T-018 ML work, use `uv run --project services/ml ruff format --check`,
`uv run --project services/ml ruff check`, and
`uv run --project services/ml pytest`; run focused tests and relevant database
or TypeScript checks for the files changed. Do not make a live network request
unless the T-018 slice explicitly requires it.
