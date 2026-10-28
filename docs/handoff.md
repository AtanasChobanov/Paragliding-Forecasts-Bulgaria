# Project Handoff

## Current state — 2026-10-28

T-022 is **Done** for the accepted Python-batch scope on `feature/T-022-baseline-cloudbase-prediction`.
The cloudbase-only Python batch is implemented and tested with synthetic data.
**Do not execute the real prediction/replay commands on the owner's behalf.**
The owner explicitly reserved those commands for manual execution. The first
owner-run smoke command failed because of the receipt lookup, fixed in
`02d5abc`. The owner subsequently produced artifact
`5fa45293c5eae1e6d3d2054c07fc6c1fd9b29d8fe2513351f20e13df0cf2a71c`.
The owner also produced the 36-run sample artifact
`3417df453eeed80d60d9dd15cd05ea50fee1afb30bf511d44a5ce2cb5089f795`.
The owner-run version 2 replay and read-only review passed. T-022 is Done
for the accepted Python-batch scope. Frontend/API integration remains deferred.

### Version 2 owner-run acceptance review

Artifact: `e0bd128a9ffb56774eb1ffa733dd8562b579be7d21cde21e6687013eff0bcd5a`.
Read-only verification passed: every published file hash/size, content-derived
artifact identity, all 2,772 input/hourly and 252 daily contracts, every expected
and potential maximum and its UTC/local timestamps, all significant-cloud
instants, regime counts and coverage flags. Every daily group has eleven hours.
Input bytes, all hourly LCL/estimated values and every expected daily maximum
are unchanged from version 1. No prediction was rerun by the agent.

Daily results: 65 expected-base summaries, 122 conditional-LCL summaries and
65 all-blue summaries. Every formerly indeterminate daily summary now has a
valid conditional fallback. No missing or unresolved no-height daily summaries
occur in this selected sample. Significant-cloud warnings appear in 70 daily
summaries, covering 253 hours; 23 expected-base days retain these warnings.
In 52 expected-base days the separate potential maximum is higher; expected
base correctly remains the primary quantity. All 65 blue days have no numeric
maximum. The 122 potential-summary heights span 1,309--4,810 m MSL, with no
negative site AGL in those selected daily maxima.

Example, Vitosha D+1 2021-10-01: potential 2,547.68 m MSL / 753.75 m above
site at 16:00 Sofia, while the higher blue-hour LCL is excluded. Nevsha's
conditional maximum is 1,653.33 m MSL at 17:00, with significant-cloud context
for 11:00--15:00 preserved separately.

Together with 570 passing permanent tests and prior Ruff/repository checks,
this completes the accepted T-022 batch functionality and manual replay gate.
It does not establish meteorological accuracy, observational calibration or
operational availability; T-039 validation and later product integration remain
separate work. Temporary research notes and the disposable experiment remain
local and were not staged or deleted.

### Version 2 conditional LCL output implemented

The owner accepted the discussed numeric fallback and cloud-context behavior.
Schema/method/policy are version 2; existing version 1 artifacts remain intact.
Daily output now has `max_potential_base`, `potential_max_at_utc/local` and
`potential_maximum_basis=indeterminate_hours_only`. Only indeterminate hours
with LCL within the retained profile enter that maximum; blue/missing hours
do not. `max_cloudbase` still contains estimated bases only and takes priority.
Without an estimated maximum, a valid conditional maximum produces
`summary_state=potential_base_available`. All-blue and all-missing indicators
are preserved. `coverage_complete` keeps its name and classification semantics.

Low-cloud >=80% or near-surface saturation now means indeterminate cloud type,
with conditional LCL retained, rather than asserting `other_cloud` from those
inputs alone. Reasons/limitations explain uncertain LCL applicability.
`significant_cloud_hours` stores UTC/local instants of >=80% low cloud so later
UI composition can qualify warnings by time, including mixed days with an
estimated maximum. Daily reasons are preserved too. The report displays the
chosen expected/potential quantity and times; manifest and CLI JSON add
`daily_state_counts`. LCL physics and the conservative 250 m/1 K formation
margins are unchanged. No frontend/API integration was performed.

The real command remains owner-run only. Rerun the same one-run smoke command
or the same 36-run Bash invocation below/previously supplied in the conversation;
the version change creates a new output directory. Review report/daily output
for potential_base_available, separate expected/potential maxima, timed cloud
warnings, all-blue no-number days and unchanged coverage semantics. No real
version 2 calculation was executed by the agent.

Version 2 validation: 570 permanent Python tests passed (disposable spike tests
excluded), Ruff lint/format, repository structure and diff whitespace checks
passed. New cases cover potential maxima excluding blue peaks, earliest ties,
estimated-base priority, missing/all-blue no-fallback behavior, out-of-profile
rejection, unknown cloud type, timed mixed-day advisories, report fallback
timestamps and version 2 artifact/CLI round trips.

### Owner clarification and policy research follow-up

Keep the name `coverage_complete`; the owner explicitly rejected renaming it.
The owner expects an explicitly labelled mixed-LCL orientation when formation
is uncertain. Hourly `potential_base` already exists in all 2,772 records;
the implemented daily summary contains no separate potential-height maximum.
Do not describe indeterminate formation as an inability to calculate LCL.
Displaying/aggregating a fallback quantity still needs explicit semantics;
never silently insert potential LCL into `max_cloudbase` or imply it is an
existing stratiform cloud base. Preserve the all-blue no-cloudbase display.

Research recommendations, not applied policy changes: use PBL-LCL as supporting
evidence rather than a universal hard 250 m cloud-existence test; retain
250 m/1 K as explicit sensitivity/transition margins pending validation rather
than hide the potential height; low-cloud >=80% does not identify cloud genus
and should not by itself assert other-cloud type. NOAA's cloud taxonomy includes
cumulus among low clouds. NOAA Skew-T guidance distinguishes heating-driven CCL
from forced lifting (including mountains). MetPy documents the CCL diagnostic,
not our compound 250 m/1 K/80% classification rule. Relevant primary sources:
https://www.noaa.gov/jetstream/clouds/ten-basic-clouds
https://www.weather.gov/source/zhu/ZHU_Training_Page/convective_parameters/skewt/skewtinfo.html
https://unidata.github.io/MetPy/latest/api/generated/metpy.calc.ccl.html
https://journals.ametsoc.org/view/journals/atsc/75/7/jas-d-17-0244.1.xml
No production code, thresholds, output schema or real prediction artifacts were
changed or regenerated during this research follow-up.

### Full owner-run sample review

Read-only review checked file hashes/sizes, all input/hourly/daily Pydantic
contracts, all daily regime counts and numeric maxima against stored hours.
The 36 runs cover 12 dates, all seven sites and D+1/D+2/D+3: 2,772 hours and
252 daily summaries. Every day has eleven present hours, no input issues and
no missing regime. Hourly regimes: 130 cumulus, 1,327 blue, 253 other_cloud,
1,062 indeterminate. Daily states: 65 numeric, 65 all-blue, 122 indeterminate.
All 65 numeric summaries have incomplete regime classification; 23 are based
on a single cumulus hour. Only the 65 all-blue days have coverage_complete=true.
This flag describes classification, not data presence.

The 1,062 unresolved hours comprise 1,010 rule fall-throughs and 52 multiple-CCL
cases. In the 1,010 fall-throughs, 646 have PBL within +/-250 m of LCL and 598
have convective-temperature margin within +/-1 K (overlapping groups). Thus
changing the multiple-CCL choice alone cannot resolve most cases. Numeric
estimated bases range 1,683--4,507 m MSL; none is below its site. Potential LCL
is below site in 36 hours (31 Vitosha, five Sopot), intentionally preserved.

Sensitivity needs careful interpretation: 121/130 cumulus hours have at least
one alternative classified indeterminate, but none switches to blue. With
100-hPa mixing and -1 K perturbation, 118/130 become indeterminate. Changing
only mixing depth to 50 hPa leaves 125/130 cumulus and five indeterminate.
These are formation-threshold sensitivities, not measured cloudbase errors.
The unperturbed central variant matches every stored central regime.

Technical replay and source recovery succeeded for this sample. High abstention,
the >=80% cloud gate, and the ambiguous coverage name remain policy/product
limitations requiring review; meteorological accuracy is unverified. These
12 selected experiment dates are not a representative validation dataset.
No prediction commands were run by the agent, no policy was changed and
T-022 was not marked Done.

### First successful owner-run review

Read-only review verified all six-file manifest hashes/sizes. The 2021-10-01
D+1 run has 77 hourly and seven daily records, all hours present, no input
issues and potential LCL in every hour. Regimes: zero cumulus, 22 blue,
18 other_cloud and 37 indeterminate. Thus there is no estimated-base maximum.
Of the 37 unresolved hours, 11 have multiple CCL intersections and 26 fall
through the policy: 22 have PBL within the +/-250 m LCL margin despite a negative
convective-temperature margin; three fail the blue low-cloud <=20% gate;
one is transitional in both height and temperature. Each site has unresolved
hours, hence every daily summary is indeterminate. `coverage_complete=false`
means incomplete regime classification, not missing source hours (present=11
at every site). These findings expose conservative policy/output limitations,
not evidence of missing profiles or verified cloudbase accuracy. The >=80%
low-cloud gate also excludes all 18 cloudy hours from numeric base estimation.
No thresholds or algorithms were changed during this review. Wider-sample
evaluation and any accepted policy/wording revision remain pending; do not
silently turn potential LCL into estimated cloudbase or relax thresholds to
force numbers. The agent did not rerun the real prediction command.

### Persistence-reader fix after the first owner-run attempt

The `persisted` ledger event references a `StageManifest`, whose outputs include
the `weather_persistence_receipt`. The reader now validates that manifest,
resolves and hash-checks its receipt output, and verifies the receipt's date
and feature lineage. Ingestion, retained source artifacts and SQLite are
unchanged. The original integration fixture incorrectly mocked a direct
receipt as ledger evidence; it now constructs and reads the real ledger chain.
This synthetic regression reproduced the owner's 22 validation errors before
the fix and passes after it. Missing/tampered receipt, wrong feature input and
wrong target date are covered too. The owner should retry the same smoke
command below; the agent has not executed it.

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

- Permanent suite after the persistence-reader fix: **564 passed**.
  This comprises the existing 499 tests plus 65 cloudbase tests. The nine
  disposable experiment tests remain outside Git and were excluded from this
  run. Before the fix, the full local suite had passed 569 tests with the
  inaccurate mocked persistence evidence; that did not prove compatibility.
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
