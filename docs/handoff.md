# Project Handoff

## Read first

1. `AGENTS.md` for repository rules.
2. `docs/tasks.md` for ticket status and scope.
3. This handoff for the active T-018 operational state.
4. The relevant sections of `docs/project-brief.md` and
   `docs/architecture.md` for product/system constraints.
5. DEC-031 through DEC-053 in `docs/decisions.md` for accepted weather
   decisions, including the ERA5 deferral boundary.

Keep durable decisions in `docs/decisions.md`, ticket lifecycle in
`docs/tasks.md`, and only current actionable state here.

## Current state — 2026-09-14

| Field          | Value                                                                                                                                                                                                                 |
| -------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Branch         | `feature/T-018-weather-ingestion`                                                                                                                                                                                     |
| Ticket         | `T-018` is **Done**. S01–S08 and S10 are complete; S09/ERA5 remains separately deferred to T-038.                                                                                                                  |
| Next work      | Do not extend weather ingestion implicitly. Future ERA5 work starts only under T-038 when the recorded decision gate is met.                                                                                         |
| Fresh evidence | Bounded current-catalogue GFS fresh, same-DB offline no-op, second-DB offline restoration, and effective artifact audit all passed on 2026-09-14.                                                                    |
| Local DB       | The primary and temporary restoration SQLite databases were migrated by the owner for acceptance. They are local ignored artifacts and must not be committed.                                                         |
| User work      | The deletions of the old S07/S08 plan files are user-owned. Do not restore, stage, or commit them without explicit instruction.                                                                                       |

## Active T-018 boundary

T-018 now owns the source-neutral SQLite schema and a complete **GFS** path:
immutable raw artifacts/manifests, parsing, canonical normalization,
site/grid sampling, validation/quarantine, feature building, and idempotent
SQLite persistence.

- GFS is the sole exact-forecast source in this implementation phase. Preserve
  run/availability/retrieval/valid/lead/grid provenance and never substitute a
  model for an unavailable run.
- Preserve units, source/model/run/valid/lead provenance, confidence, and
  explicit missing/quality states. Never turn a sentinel or missing field into
  a physical value.
- No Airflow/scheduler, raw-retention deletion, partial/sampled integrity hash,
  unrelated feature/model work, or SQLite schema expansion belongs in S10.

## S09 / ERA5 decision

ERA5 ingestion is deferred from T-018. The implemented exact GFS source and
feature/persistence path are sufficient for the initial model; the project
brief does not require an ERA5 collector once usable exact forecasts exist.

Create the durable decision and backlog adjustment as S10 Phase 0 (expected
future task: T-038). Start ERA5 only when real joined GFS data, baseline model,
backtests, or calibration show a need for forecast/reanalysis bias pairs,
climatology, weak cloud-base labels, confidence calibration, or fine tuning.

ERA5 must remain a separate `reanalysis` cohort, never a GFS fallback row or a
same-example forecast substitute. Keep its future-compatible source registry,
schema capacity, policy family, provenance rules, and nullable CIN/cloud-base
destinations; do not implement a placeholder collector or CDS credential path.

## Completed S10 operational evidence

The executable plan is retained at `docs/T-018-S10-implementation-plan.md`.
Its required GFS-only implementation, compact artifact migration, and shared
fresh/offline-resume orchestration are complete.

The owner-authorized live acceptance used run
`0200117a-2638-4e98-ac42-534db32315dd` for local date `2026-09-14`, GFS cycle
`2026-09-14T00:00:00Z`, purpose `operational_forecast`, and reviewed cap
`1109 MiB`. The fresh result inserted the graph into the primary SQLite
database. It retained 1,163,650,418 raw bytes, 25.32 MiB of interim artifacts,
an 8 x 24 compact crop covering 77 required nodes, and no global parser or
normalizer arrays. Collection took 15 minutes 8 seconds; fresh end-to-end took
15 minutes 45 seconds. Its verifier processed 597 files / 1,163,650,418 bytes
in 1.225 seconds with 11,916 cache hits.

The same-database resume returned `revalidated_no_op` with unchanged counts.
Offline resume into a separately migrated seeded SQLite database returned
`inserted` with the same 1 run, 77 samples, 308 intervals, 759 profile levels,
154 convection measurements, 7 daily snapshots, 14 profile layers, 77 snapshot
inputs, and 9,554 provenance rows. Both resumes reported no network access and
reused all derived boundaries.

`weather-artifacts audit --scope effective` passed: it verified the eight-event
ledger's seven effective boundaries, hashing 619 files / 1,190,198,723 bytes
and parsing seven manifests. Full-history audit remains optional maintenance.
The raw and SQLite acceptance artifacts are local-only and must not be committed.

## Why S10 is necessary

### Artifact verification performance

`RunStateLedger.load_events()` currently recursively verifies every event
evidence boundary and rehashes predecessor/events. Repeated command calls
repeat artifact and raw-content reads. For the retained old-style 18-event
lineage, one traversal was estimated at roughly 362 GiB of reads before further
command-level repeats.

The fix must not weaken integrity:

- normal fresh/resume verifies only the effective immutable lineage;
- all-history verification remains an explicit audit mode;
- full SHA-256 remains mandatory for trusted effective files;
- cache verified files/manifests/boundaries/matrices only within one command,
  with full identity keys and stat-change invalidation;
- retain atomic publication and snapshot-aware ledger append;
- emit secret-free files/bytes/cache counters in command output, not SQLite.

Existing database SHA fields stay unchanged: `raw_manifest_sha256`,
`feature_manifest_sha256`, and `persistence_input_sha256` identify distinct
provenance boundaries; `persisted_graph_sha` is a receipt.

### Storage scaling

The retained GFS run is dominated by derived global arrays, not SQLite rows:
raw payloads are about 1.09 GiB, active parser v5 artifacts about 10.92 GiB,
and active normalizer v7 artifacts about 12.01 GiB; spatial/validator/features
total only about 18 MiB. With superseded history, one retained day is about
47 GiB, so naive 100-day retention is not viable.

The compact design is locked:

- Decode and validate the full GRIB message in memory, preserving bitmap and
  sentinel semantics; persist only the deterministic rectangular crop required
  by configured site footprints.
- The current seven sites need 77 unique nodes inside an 8 × 24 (192-cell)
  crop, versus the provider's 1440 × 721 global grid. Derive this crop from the
  immutable site snapshot and sampling policy; do not hard-code it.
- A rectangle, rather than sparse nodes, preserves current bilinear/radius
  sampling. Preserve float64 values, packed masks, global-to-local node
  translation, and `gfs_0p25_global` SQLite identity.
- Bind site-config SHA, sampling-policy SHA, and crop-selection version into
  acquisition/artifact identity. Changed footprint inputs may not silently
  reuse a compact or persisted graph.
- Keep raw source evidence and existing completed artifacts. Do not introduce
  raw pruning, new dependencies, or SQLite columns.

Given identical raw GRIB, site snapshot, and policy, selected-node canonical
and SQLite business values must be unchanged. Only derived on-disk representation
and repeated verification work may change.

## Commands and safety

Use `uv run --project services/ml ...` for ML commands. Do not make a live
network request unless the current phase explicitly calls for the owner-
authorized bounded fresh operation. Resume must not construct or call a source
transport. Do not mark S09, S10, or T-018 complete without the documented
operational evidence.
