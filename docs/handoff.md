# Project Handoff

## Current state — 2026-10-28

T-022 is **In Progress** on `feature/T-022-baseline-cloudbase-prediction`.
The cloudbase-only Python batch is implemented and tested with synthetic data.
**Do not execute the real prediction/replay commands on the owner's behalf.**
The owner explicitly reserved those commands for manual execution. No real
cloudbase batch has been produced by this implementation session. T-022 must
not be marked Done before that replay and result review.

### Implemented scope

- Read-only selection of explicitly named persisted GFS 06Z D+1/D+2/D+3 runs,
  with per-hour source readiness by issue-date 16:00 Europe/Sofia.
- Recover the full above-model-ground pressure column from retained compact
  grids, including levels below the actual site omitted by site sampling.
  Verify retained metadata/array hashes and lineage without requiring raw GRIB
  payloads. Raw manifest metadata and run ledgers still need to be present.
- Compute 100-hPa mixed-parcel Romps liquid LCL and MetPy 1.7.1 CCL/convective
  temperature; apply versioned formation rules using existing low cloud,
  surface RH, model PBL and matched surface fluxes. Keep 50/100-hPa and +/-1 K
  sensitivity diagnostics. These thresholds are uncalibrated policy choices.
- Separate `cumulus`, `blue`, `other_cloud`, `indeterminate` and `missing`.
  Only cumulus has an estimated cloudbase. Potential LCL is a separate value.
  Blue is not a useful-thermal or clear-sky guarantee. No usable thermal height,
  Hcrit, cloud top, entrainment or glider-performance model is included.
- Keep MSL, model AGL and signed site AGL; retain terrain-mismatch warnings.
  Produce eleven hourly records per site (10:00--20:00 inclusive Sofia).
  Daily maximum uses only estimated cumulus bases; one numeric hour suffices,
  with coverage warnings where needed. Only eleven blue hours make a blue day.
- Publish immutable content-addressed local JSON/JSONL, exact inputs, policy,
  provenance, library versions and a Markdown report. Changed or incomplete
  existing artifacts are rejected; repeat builds preserve their identity.

SQLite, stored weather profiles, the joined dataset and T-023 training inputs
remain unchanged. The owner explicitly deferred any training-feature review
or correction. No new GFS fields, downloads or external provider are added.
API/UI integration is also deferred. DEC-058 and the ML README now describe
the accepted scope and exact algorithm/thresholds.

Implementation commits so far: `4d272ed` (contracts/policy/dependency),
`2f28ce4` (physics/CCL), `da9fdaf` (retained model column), `1b8959d`
(formation/aggregation/input guards) and `43fc32d` (CLI/artifacts/report).
The following documentation commit records the owner-run checkpoint.

### Verification

- Full local Python suite: **569 passed** (includes nine disposable experiment
  tests that are intentionally not committed).
- Permanent suite, excluding that disposable test file: **560 passed**.
  This comprises the existing 499 tests plus 61 new cloudbase tests.
- Ruff lint and format checks passed; `npm.cmd run repo:check` passed;
  `git diff --check` passed. No TypeScript behavior changed.
- Synthetic tests cover model/site elevation differences, recovered low levels,
  deleted raw GRIB with retained metadata, read-only SQLite, malformed/tampered
  evidence, strict sampling, units, timing/cutoff, CCL ambiguity, formation-rule
  boundaries, missing states, daily maxima/coverage, DST, no-network operation
  and deterministic immutable outputs.
- Actual retained-source compatibility, output regime distribution and runtime
  remain unverified until the owner runs the commands below. Synthetic success
  does not establish cloudbase accuracy or a delivery SLA.

### Owner-run checkpoint

Run from the repository root. First process one existing run (all seven sites):

```powershell
uv run --project services/ml cloudbase-predict --run-key 93b7b0b5-f3fe-4f8e-8781-01aca0689661
```

For the retained experiment sample, the owner can then select its existing
run keys without downloading anything:

```powershell
$cloudbaseRunKeys = Get-Content 'data/processed/t022-cloudbase-spike/retained-hourly-inputs.jsonl' |
    ForEach-Object { ($_ | ConvertFrom-Json).run_key } |
    Sort-Object -Unique
$cloudbaseArguments = @()
foreach ($runKey in $cloudbaseRunKeys) {
    $cloudbaseArguments += @('--run-key', $runKey)
}
uv run --project services/ml cloudbase-predict @cloudbaseArguments
```

Expected sample sizes, if the real replay succeeds: 77 hourly/7 daily records
for the first command; 36 runs, 2,772 hourly/252 daily records for the second.
The command prints counts and `output_directory`; inspect that directory's
`report.md`, `manifest.json`, `hourly.jsonl` and `daily.jsonl` after the owner
reports execution. Review missing/indeterminate reasons, terrain warnings,
coverage, base heights and stored-versus-full-column differences. Do not
interpret computational agreement as observed forecast accuracy. Only after
this review should T-022 completion or necessary fixes be considered.

### Local files deliberately excluded from Git

The session research notes (sounding/cloudbase note, GFS experiment findings,
physical method options and profile/terrain audit), disposable spike script,
its tests and generated experiment data remain local. Do not stage them or
remove them during implementation. The owner intends to delete temporary
research files after T-022 is completed; that cleanup is not authorized yet.
Durable commands and policy are documented in `services/ml/README.md`.

## Previously verified state — 2026-10-21

T-020 and T-021 are **Done**. T-021 was completed on
`test/T-021-feature-calculation-tests`. The feature test commits are
`cf64d13`, `a252b86` and `1401867`. The fixes and correction layer are
`36235a0` (IGRA), `94d1ea8` (wind), `c339d9d` (thermal) and `c8aa2c5`
(versioned correction).

The IGRA RH/dew-point/CIN provenance defects, calm-wind/source-quality
discrepancies and the thermal 2 m anchor rule have local fixes and tests.
The new feature policy is v5; old v4 remains packaged for historical v3
verification. `igra-ingest reprocess` forks retained IGRA source evidence into
a new offline run with the corrected normalizer version; it leaves completed
old artifacts unchanged.

The chosen versioned correction layer reads the retained SQLite hourly inputs
without writing SQLite or restoring GFS raw files. It produced correction ID
`22c8d088635217bdd78792c1a1c1b1514ce92b8f8365d271a156739051a45c51`
and joined v4 dataset ID
`5e88d13ff67e201ce8b0f23ed2d517d5af188e6185cd1496cab8798316bf7394`.
Artifact-only verification passed for both. A repeat build returned identical
IDs. The v4 dataset has 960 training rows, zero exclusions and **20 patched
rows / 80 recovered daily values**; 940 other lines are byte-identical to v3.
The earlier 19/1 expectation was wrong: Pastrina's missing 08:00 UTC flux
belongs to the preceding interval, outside the 08:00–18:00 UTC flying window.
The parent v3 ID is
`c294ebdf21cb2380548a52ec46b1f174ec85ce381e7561f88d6c55a3245c1c38`.
The correction JSONL SHA-256 is
`d0c46e246ac80a9bc3c64be80c5b273e5bf0ada0260789620db574506541d57b`;
the v4 training JSONL SHA-256 is
`42ae3a7a7ddc34ba156348a7e1bc9ba7a27c3ba6b05050e6e866e12820893150`.
The correction artifact retains exact inputs and old/new values for every
patched row. Reproduction and verification commands are in `services/ml/README.md`.

The full offline Python suite passed **499 tests** using normal Windows
filesystem permissions for hard links. Focused IGRA reprocess and synthetic
correction/tamper tests passed. Ruff check, Ruff format, repository structure,
`git diff --check`, both installed CLI help commands, and artifact-only v3,
correction and v4 verification passed. The final diff review found only T-021
source, tests, documentation and the permitted ticket-status change; a final
focused rerun passed 36 tests. Do not begin
T-022/T-023 modeling as part of this ticket.

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

## Dataset context and limits

- The T-020 v3 artifact retains the packaged `weather-feature-policy-v4.json`.
  The corrected builder defaults to v5 with the same 46-feature contract; the
  v3 verifier explicitly loads v4, and the v4 joined verifier checks only the
  four allowlisted daily thermal replacements and correction locator.
- Across the 960 joined rows, the three provider cloud-base daily fields are
  unsupported in every row. The four thermal/buoyancy daily summary fields
  remain missing in 20 rows of v3 and are finite derived values in those same
  20 v4 rows. Profile-layer fields remain unchanged and derived.
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
