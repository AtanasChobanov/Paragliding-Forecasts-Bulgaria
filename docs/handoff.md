# Project Handoff

## Purpose and source of truth

This is the concise operational snapshot for the next T-018 implementation
slice, not a project history. Read, in order:

1. `AGENTS.md` for repository rules and workflow.
2. `docs/tasks.md` for the T-018 lifecycle status and ticket scope.
3. This handoff for the implemented T-018 slice boundaries.
4. The relevant sections of `docs/project-brief.md` and `docs/architecture.md`
   for product and system constraints.
5. DEC-031 through DEC-043 in `docs/decisions.md` for accepted weather-source,
   schema, protocol, parser, and spatial-sampling decisions.
6. Git history and the owning code/tests for detailed prior implementation and
   validation evidence.

Record durable design choices in `docs/decisions.md`, task status in
`docs/tasks.md`, and only the current operational state here.

## Current state (2026-09-09)

| Field         | Value                                                                                                                                                                                                                        |
| ------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Branch        | `feature/T-018-weather-ingestion`                                                                                                                                                                                            |
| Task status   | `T-018` is In Progress; S01–S07 are complete, S08–S10 remain.                                                                                                                                                                |
| Next focus    | Implement S08 persistence of the verified S07 v2 feature artifacts; no SQLite writes occur in S07.                                                                                                                         |
| Local storage | SQLite selected by `DATABASE_URL`; local databases, raw source data, and interim artifacts are ignored.                                                                                                                      |
| Migrations    | Earlier weather/configuration migrations, `20260909123754_correct_s07_feature_inputs`, and `20260909165706_remove_s07_inversion_metrics` are applied locally; normal `db:migrate` runs completed idempotently on 2026-09-09 and 2026-09-10. |

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

### S07 persistence preparation — applied and verified

DEC-039 supersedes the S01 weather-storage shape before S07. The Drizzle schema
now separates hourly provider facts from daily model features:

- `weather_product_valid_times` owns exact UTC/lead values beneath a product
  run; a weather ingestion run owns one product run and `target_local_date`
  without repeating `source_id`;
- `weather_point_samples` and their renamed profile/convection/interval
  children are hourly facts; profile rows add `vertical_velocity_pa_s` and
  distinguish persisted site-AGL from artifact-only model-AGL;
- `weather_daily_feature_snapshots` is the typed daily wide row,
  `weather_daily_feature_snapshot_inputs` records all contributing hourly
  rows, and `weather_daily_feature_profile_layers` stores repeatable AGL
  layer results;
- `weather_field_provenance` owns explicit quality/missingness for hourly,
  daily, and daily-layer fields. No snapshot input SHA, footprint SHA/version,
  grid-definition SHA, or grid-point measurements are persisted.

The daily reshape migration was reviewed and applied. Its up-front guard rejects
any non-empty legacy runtime weather graph because the reshape is intentionally
lossy. A follow-up migration corrected the positive-CIN daily extreme from
`min` to `max`; another immediately restored `STRICT` after Drizzle's generated
rename rebuild omitted it. Fresh temporary-database migration, idempotence,
strict-table, foreign-key, constraint, and guard tests pass.

GFS profile selection now covers
1000/975/950/925/900/850/800/750/700/650/600/550/500 hPa for
HGT/TMP/RH/SPFH/UGRD/VGRD/VVEL; 875 hPa is deliberately excluded because the common
`pgrb2.0p25` object does not provide it.
The old GFS-only 925/850/700 validation band is superseded, enabling S07's
strict AGL layer interpolation without a source-specific profile path. The
current `gfs-collect` CLI still uses repeatable `--valid-at` and a 128 MiB
default cap; adding one-run `--local-date` flying-window orchestration and
measuring its reviewed larger cap remain explicit follow-up work.

Verification on 2026-09-09: the configured database accepted the three daily
weather migrations and a second `db:migrate` was idempotent. Drizzle
`db:check`, all 29 database tests, all 139 ML tests, ML Ruff check and format
check, workspace TypeScript typecheck, and `git diff --check` passed. These
changes are intentionally uncommitted for owner review.

### S07 source-contract correction — applied and verified

DEC-041 supersedes the impossible GFS 875 hPa selector in DEC-040. The pipeline
uses only the common `pgrb2.0p25` object and its 13-level
1000/975/950/925/900/850/800/750/700/650/600/550/500 hPa band for the current
HGT/TMP/RH/UGRD/VGRD/VVEL profile inputs. The collector, numeric GRIB parser,
normalizer, and validation boundary were versioned to preserve prior immutable
evidence; the GFS and ERA5 validation-policy contracts declare the same vertical
grain, though the ERA5 adapter remains S09 work. Focused GFS/weather ingestion
tests, Ruff format/lint, and `git diff --check` pass. This was a source-contract
change only: no SQLite migration was necessary.

### S07 source-input contract — committed and locally migrated

DEC-042 extends the DEC-041 common-object profile with direct GFS `SPFH` at 2
m and every retained pressure level, plus surface `SHTFL`/`LHTFL` interval
averages. The normalizer retains q in kg/kg with a `2m_above_ground` dimension
or pressure coordinate, and retains GFS turbulent fluxes as upward-positive
W/m² interval evidence. The source policy requires direct 2 m q and q in every
profile grain. No q is inferred from other GFS fields.

The packaged catalogue is `t017-spike-v2`: `unsupported` is an explicit null
state; spatial sampling preserves it as null evidence. Four unaccepted field
families have been removed from the active catalogue, and the schema/migration
adds nullable `specific_humidity_2m_kg_per_kg` while removing the five matching
unused daily columns. The reviewed forward-only migration is
`20260909123754_correct_s07_feature_inputs`. The owner applied it to the
configured local database on 2026-09-09; the normal `db:migrate` command then
completed idempotently. The five legacy daily columns are no longer present in
that local database.

Component versions are GFS collector/parser `/4`, GRIB profile `v3`,
normalizer `/4`, spatial `/3`, validation policy `/3`, and validator `/4`.
Focused validation on 2026-09-09 passed: 63 ML GFS/atmosphere/weather tests,
ML Ruff check, Drizzle `db:check`, all 29 database tests, focused Prettier,
and `git diff --check`. The database migration test includes the new q range
constraint, fresh migration, idempotence, and SQLite `STRICT` rebuild checks.

### S07 inversion cleanup — applied and verified

DEC-043 removes `inversion_strength_max_k` and `inversion_depth_at_max_m` from
S07 entirely. They were unrequired model-level temperature-profile diagnostics,
not GPS evidence, raw provider fields, or an active catalogue identity. The
S07 plan, vertical helper, and tests no longer calculate them; lapse-rate and
humidity profiles remain the approved stability evidence. The forward-only
SQLite `STRICT` rebuild migration
`20260909165706_remove_s07_inversion_metrics` dropped the two nullable daily
profile-layer columns and their pair constraint from the configured local
database on 2026-09-10. A subsequent normal `db:migrate` completed
idempotently.
### S07 v2 artifact contracts and policy — committed and verified

The S07 v2 boundary now has strict source-neutral contracts for hourly and
daily feature snapshots, feature values, AGL layers, explicit missing-feature
locators, and quality summaries. Daily profile identity is the approved tuple
`(layer_base_agl_m, layer_top_agl_m, feature_key)`; keys therefore stay aligned
with database column names rather than acquiring synthetic layer prefixes.

The hash-pinned `weather-feature-policy-v1.json` declares the fixed Sofia
window, all 37 daily and 13 profile-layer output keys, their catalogue field/
unit identities, derivation versions, and the 0--1500/1500--3000 m AGL layers.
It excludes the DEC-043 inversion metrics. The legacy atmospheric
`FeatureSnapshot` v1 remains untouched for synthetic compatibility. New S07
contract/policy tests plus the complete ML suite (157 tests), Ruff check/format,
and `git diff --check` passed on 2026-09-10. The source-neutral neighbourhood
planar-fit calculation is now also implemented and tested; the next S07 checkpoint
is builder/artifact orchestration.
### S07 profile-layer builder reduction — committed and verified

The builder now reduces the two policy-defined AGL layers directly from accepted
S06 `SiteAlignedSample` evidence. It uses the real 2 m temperature/RH/q and 10
m wind anchors for the lower layer, retains no-extrapolation bounds, applies the
strict eleven-hour window independently per feature, derives direction only
from reduced mean U/V, and emits `lower_boundary_not_bracketed` for lower omega.
Analytic coverage/anchor tests and the complete ML suite (162 tests), Ruff
check/format, and `git diff --check` passed on 2026-09-10. Daily surface/
interval reductions and immutable builder artifact orchestration remain.
### S07 artifact builder and CLI — committed and verified

S07 is complete. `weather-build-features --run-key <uuid>` is an offline-only
resume command. It requires the current `validated/complete` boundary; a
quarantined validator returns `2` and creates neither feature evidence nor a
state event. A successful feature build writes the immutable
`feature_builder/weather-feature-builder-1/<fingerprint>/` boundary with:
`feature-snapshots.json` (hourly v2), `day-feature-snapshots.json` (daily v2),
`feature-quality-report.json`, and its stage manifest, then appends or
supersedes `features_built/complete` in the state ledger. It returns `0` for a
new or reused complete boundary and `1` for operational or hash-chain failure.

The fingerprint includes the validator manifest, accepted and missing S06
artifacts, exact S05 neighbourhood artifact, policy bytes, and v2 contract/
builder versions. Daily values have the fixed eleven Sofia instants and exact
interval coverage; missing values stay explicit, with no partial aggregate.
Neighbourhood fitting consumes only S05 MSL pressure and surface 10 m U/V, not
the retained 925 hPa node fields. S07 writes no SQLite rows; S08 owns that
persistence boundary.

Verification on 2026-09-10: full ML suite (`169 passed`), Ruff check/format,
Python compile check, and `git diff --check` passed. The earlier 875 hPa and
DEC-043 inversion decisions remain authoritative; the ML README now reflects
them. The user-owned `docs/T-018-S07-implementaion-plan.md` remains unstaged.
### S07 daily GFS collection orchestration — committed and verified

DEC-044 implements the previously outstanding `--local-date YYYY-MM-DD` GFS
collection mode. It derives the exact eleven Europe/Sofia 10:00--20:00 UTC
instants through `zoneinfo`, records `target_local_date` and
`sofia-flying-window/1` in the immutable request/resolved plan, and rejects a
mixed `--local-date`/`--valid-at` invocation. The resolved GFS request contract
has an additive schema-v2 daily form and collector `gfs-collector/5`; prior
schema-v1 explicit-UTC plans stay readable. Summer/winter DST, strict date
format, provenance, and CLI exclusivity tests pass.

No larger default byte cap was guessed. A real bounded eleven-hour NOAA
inventory is still needed to select a reviewed explicit daily cap before a
live full-day collection; it is an external operational measurement, not a
fabricated configuration value. The user-owned S07 implementation plan remains
unstaged.
### S02 — durable atmospheric protocol

The sole machine-readable T-017 field catalogue is the packaged resource
`services/ml/src/paragliding_forecasts_ml/ingestion/atmosphere/resources/weather-field-catalogue.json`.
Strict Pydantic contracts validate field codes, canonical units, source IDs,
and quality states against it at runtime; there is no copied Python field enum.

`data/raw/weather/<run-key>/` owns immutable `request-plan.json`, native
payloads, and `manifest.json`. `data/interim/weather/<run-key>/` owns
versioned/fingerprinted parser, normalizer, spatial, validation, feature, and
persistence evidence plus an append-only hash-linked state-event ledger.
`fresh` creates a UUID layout. Offline `resume` may append the legal next event
or a schema-v2 derived-boundary event with `supersedes_sequence`: the latter
must name the current completed boundary for the same stage and publish distinct
hash-verified evidence. Old state-event v1 records remain readable; no artifact
or event is rewritten. `partial` and `persisted` are terminal; only validation
may emit or resolve `quarantined`.

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
consumes only a complete normalized event. It reuses the current exact
version/fingerprint boundary; a changed spatial version or upstream fingerprint
appends a `spatially_aligned` event with `supersedes_sequence` rather than
rewriting the old boundary. Its fingerprint covers the normalized manifest,
grid/orography, reviewed config snapshot, packaged policy, footprints, and
version. Integration tests prove
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
an existing validated boundary only when its validator version and spatial input
are current; otherwise it appends a versioned `validated` event that explicitly
supersedes the prior validation boundary.

S06 owns coverage disposition. GFS has a required lead and both registered
sources require the DEC-041 1000/975/950/925/900/850/800/750/700/650/600/550/500
hPa profile grain; ERA5 has no lead. No
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

### Latest state-supersession verification (2026-08-26)

The S06 run `0e2c4771-acbc-42ab-b6f3-4b5f36946270` now has immutable
`spatial-v1` and `spatial-v2` evidence recorded in order: state event 0008 is
`spatially_aligned/complete` and explicitly supersedes event 0005. Its matching
validator-v2 result is state event 0009 and explicitly supersedes the prior
validator-v2 event 0007. An immediate offline replay of `gfs-sample` then
`weather-validate` returned those v2 boundaries without creating extra events
(9 before, 9 after). Full ML verification passed: 138 tests, Ruff format check,
and Ruff check.

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
