# T-020 phase 4 — development joined dataset verification

Verified on 18 October 2026. The 2022–2024 **source-season** development
cohort is complete. This report describes dataset production and validation,
not model skill, forecast safety, or the reserved 2025 backtest.

## Frozen inputs and output

| Evidence | Identity / result |
| --- | --- |
| XCContest label audit | `f30cf3707dc91a310a26938a6c3eb7ca9acacd933d7cfe5f4db6505e5f1ed714` |
| 06Z cohort | `e75ee4091e9eaaec446a457e8ef09cbb5f02235ff37c38062a3129df64191c14` |
| Development acquisition | `ea7b5dcbbb3e1f9dac97d377946310153fabd4fa7e69cbf077903d881d862492` |
| Joined dataset | `c294ebdf21cb2380548a52ec46b1f174ec85ce381e7561f88d6c55a3245c1c38` |
| Output contract | `weather-flight-joined-dataset/3` |
| Input coverage | 705 finalized ready date/horizon jobs; 705 matching succeeded SQLite runs |
| Output coverage | 320 selected site-days, 235 distinct target dates, seven sites; 960 examples, 320 at each D+1/D+2/D+3; zero excluded |

Run from the repository root:

```powershell
uv run --project services/ml weather-join `
  --acquisition-id ea7b5dcbbb3e1f9dac97d377946310153fabd4fa7e69cbf077903d881d862492
uv run --project services/ml weather-join `
  --verify-dataset-id c294ebdf21cb2380548a52ec46b1f174ec85ce381e7561f88d6c55a3245c1c38
```

The first command reads SQLite and retained acquisition/cohort/label artifacts
and publishes under `data/processed/joined-weather/<dataset-id>/`. The second
command is artifact-only. Neither command requests GFS data or writes SQLite.
Rebuilding twice returned the same dataset ID. The two output files match
their manifest byte counts and SHA-256 hashes.

## Phase-4 acceptance checks

- Every selected site-day has exactly one D+1, D+2 and D+3 row. Site/date/
  horizon keys are unique. Rows match the frozen label hash, sampling weight,
  06Z acquisition receipt, issue date, source cutoff and delivery deadline.
- Each ready row has the correct eleven Sofia flying-window UTC hours and
  numeric GFS leads. Its product cycle, run key and source-ready timestamp
  match the receipt; source readiness is no later than the 16:00 local cutoff.
- All 960 rows have known, nested 100/200/300 km labels and mature activity
  evidence. Counts are 480/480 positive/negative rows for 100+, 126/834 for
  200+, and 9/951 for 300+. These are repeated horizon rows, representing
  160, 42 and three positive site-days respectively.
- The verifier checks the exact 46 daily feature keys, two profile layers and
  their applicable 24 profile fields against the packaged feature policy.
  Every output value has a unique field provenance identity and the catalogue
  unit; null values have missing/unsupported quality and a reason, while
  available values are finite. Across 960 rows, daily field states are
  41,200 derived, 2,880 unsupported and 80 missing; all 23,040 applicable
  profile fields are derived. Provider cloud-base fields are explicitly
  unsupported. Twenty rows each lack the two convective-velocity and two
  buoyancy-flux summaries; T-021 can investigate their calculation and
  missingness, without treating them as zero.
- The actual acquisition has zero excluded rows. Synthetic tests verify that
  `missing_weather` and `late_source` each produce an explicit excluded
  horizon, never a substituted later forecast or a training row. Tests also
  reject an altered output hash, unknown/non-nested labels, wrong lead and
  missing or inconsistent hourly source timing.

SQLite `quick_check` returned `ok`; `foreign_key_check` found no violations.
The final focused, full-suite, lint, structure, and diff results are in
`docs/handoff.md`. The 2025 weather acquisition is intentionally reserved for
T-026. T-020 does not train or calibrate models, estimate cloudbase, or join
IGRA observations (DEC-054).

The development cohort deliberately balances 160 100+ positive and 160
negative site-days. Its apparent 50% positive frequency is a sampling
property, not a population probability. T-023/T-026 must group all horizons
and sites of a target date in chronological validation and account for the
sampling policy when interpreting probabilities. The three 300+ positive
development site-days remain exploratory support only.
