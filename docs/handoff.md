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
| Ticket         | `T-018` remains **In Progress**. S01–S08 are implemented; S09 is deferred, not complete; S10 is planned and unimplemented.                                                                                            |
| Next work      | Execute S10 in order: documentation reconciliation, artifact-verification hardening, compact GFS derived artifacts, shared fresh/offline-resume orchestration, then one owner-authorized bounded live GFS acceptance. |
| Fresh evidence | No successful fresh current-catalogue ingestion exists. The retained run is stale under DEC-052 and cannot close T-018.                                                                                               |
| Local DB       | SQLite is selected by `DATABASE_URL`. The migration `20260911202938_t018_persistence_contract` is un-applied on the configured local database; do not apply it or run persistence there without owner review.         |
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

## S10 locked implementation direction

The full executable plan is
`docs/T-018-S10-implementation-plan.md`. Its required order is:

1. Reconcile `decisions.md`, `tasks.md`, this handoff, architecture, and README
   claims to reflect the ERA5 deferral recorded by DEC-053.
2. Replace deep evidence verification during ledger reads with metadata-only
   `RunStateSnapshot` loading plus explicit effective-lineage verification.
3. Add one command-scoped verification session with conservative identity/stat
   invalidation; retain complete SHA-256 for every trusted effective file and
   explicit all-history audit capability.
4. Replace persisted global parser/normalizer arrays with lossless compact GFS
   crops, then update sampling/orchestration to use them.
5. Run one separately authorized bounded GFS fresh operation, offline replay,
   and restoration into a newly migrated database; report real evidence only.

Integration-test work is intentionally absent from the S10 plan and must not
be added or implied until the owner explicitly requests it.

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
