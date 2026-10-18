# Project Handoff

## Current state — 2026-10-18

T-020 is **Done**. The 2022–2024 source-season development cohort has a verified,
versioned XCContest × exact-06Z-GFS dataset. T-021 is the next To Do ticket:
feature calculation tests for weather and sounding fields, units, missingness,
and date/timezone alignment. Read `AGENTS.md`, this handoff, T-021 in
`docs/tasks.md`, and only the relevant architecture/brief sections before
starting it. Do not start T-022/T-023 modeling as part of T-021.

The current branch is `feature/T-020-joined-weather-dataset`. The T-020 closure
changes are in the working tree; preserve them when starting the next task.

## Verified T-020 boundary

- Repaired XCContest label audit:
  `f30cf3707dc91a310a26938a6c3eb7ca9acacd933d7cfe5f4db6505e5f1ed714`.
  Cohort: `e75ee4091e9eaaec446a457e8ef09cbb5f02235ff37c38062a3129df64191c14`.
  Development acquisition:
  `ea7b5dcbbb3e1f9dac97d377946310153fabd4fa7e69cbf077903d881d862492`.
- All 705 acquisition jobs are finalized `ready` and match 705 `succeeded`
  SQLite runs. The cohort selects 320 site-days on 235 dates across seven sites.
- The immutable joined dataset is
  `data/processed/joined-weather/c294ebdf21cb2380548a52ec46b1f174ec85ce381e7561f88d6c55a3245c1c38/`
  under `weather-flight-joined-dataset/3`. It has 960 training rows, exactly
  320 at each D+1/D+2/D+3, and zero actual exclusions. Its two JSONL hashes,
  full cohort coverage, nested labels, as-of identity, units, missingness and
  per-field provenance pass the artifact-only verifier. A second join run
  returned the identical dataset ID.
- Reproduce verification from the repository root:

  ```powershell
  uv run --project services/ml weather-join `
    --verify-dataset-id c294ebdf21cb2380548a52ec46b1f174ec85ce381e7561f88d6c55a3245c1c38
  ```

  It reads retained acquisition/cohort artifacts, never downloads GFS, and
  does not read or write SQLite. The build command and full acceptance report
  are in `docs/T-020-phase-4-joined-dataset-verification.md`.
- Final validation: 420 Python tests passed; Ruff lint/format,
  `npm.cmd run repo:check`, and `git diff --check` passed. SQLite `quick_check`
  returned `ok` with no foreign-key violations. The full Python suite needed
  normal filesystem permissions because the Windows sandbox denies hard links
  used by existing tests. The synthetic join tests cover missing/late source,
  tampered hashes, unknown/non-nested labels, units, missing reasons and timing.

## Next-ticket context and limits

- T-021 should use the packaged `weather-feature-policy-v4.json`, the source-
  neutral feature contracts, and `services/ml/tests/ingestion/weather/features/`.
  The T-020 verifier checks the published values' shapes, catalogue units and
  provenance; T-021 owns calculation-specific tests and date/timezone cases.
- Across the 960 joined rows, the three provider cloud-base daily fields are
  unsupported in every row. Each of four thermal/buoyancy summary fields is
  missing in 20 rows with an explicit reason. Investigate those calculations
  and missing states in T-021; null must not become zero. Profile-layer fields
  are present and marked derived in all joined rows.
- DEC-066 pins the historical evening issue to the issue-date 06Z cycle,
  source readiness by 16:00 Europe/Sofia and delivery by 20:00. DEC-068 stores
  source-ready evidence per valid hour. DEC-056 defines nested XC labels and
  mature activity for negatives. DEC-054 keeps IGRA observations outside the
  training join; IGRA remains separate validation evidence.
- The 2025 weather cohort is reserved for later T-026 backtesting. No model,
  calibration or alert was built in T-020. The development sample is balanced
  at 160 positive/160 negative 100+ site-days, so its frequency is not an
  unconditional probability. There are only three 300+ positive development
  site-days; performance claims for that threshold remain exploratory.

Older T-020 operational checkpoints have been removed from this handoff. The
previously uncommitted October batch interruption notes are preserved in
`docs/T-020-backfill-interruptions-2026-10.md`; the phase-2 label audit, phase-3
acquisition plan, accepted decisions and Git history retain the remaining
historical detail.
