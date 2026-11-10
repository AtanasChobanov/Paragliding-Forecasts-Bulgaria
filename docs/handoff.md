# Project handoff

## Where to resume

T-020 through T-023 are Done. The current branch is
`feature/T-024-baseline-overdevelopment-risk`, based on the completed T-023
baseline. Use [tasks.md](tasks.md) for
status and [decisions.md](decisions.md) for accepted policy. Work on the
next requested ticket on top of the branch that supplies its dependencies.

- **T-024 overdevelopment baseline.** The offline `overdevelopment-predict`
  command implements the DEC-057 daily score and critical overrides. It
  verifies retained GFS lineage, publishes an immutable day-level bundle and
  supports read-only replay. T-024 is in Review after owner-run acceptance,
  reverse-order reuse and standalone replay.
- **T-025 confidence and drivers in the UI.** Connect the T-024 daily OD
  output to the forecast API and UI. The API currently serves mock forecast
  data. Resolve the storage design for real predictions during integration. Preserve
  units, provenance, missing states and confidence. Cloudbase has separate
  estimated and conditional LCL maxima. XC exposes low confidence for each
  available threshold, separate grouped contributions for P100 and conditional
  Q200, and a pooled 300+ conversion note. Contributions describe model
  calculations relative to the training reference.
- **T-026 independent backtest.** Use the frozen XC model on the untouched
  **2025 source season**. The cohort reserves 242 site-days on 131 target
  dates. Inventory retained weather first. DEC-066 deferred 2025 acquisition
  and fixes the issue-date GFS 06Z cycle, readiness by 16:00 Europe/Sofia and
  D+1/D+2/D+3 matching. Use DEC-056 for mature labels and DEC-068 for per-hour
  readiness evidence. Keep the holdout out of tuning and calibration.
  Count site-days distinctly from repeated horizon rows and retain sparse
  300+ support and missing coverage in the report.
- **Later alerts.** DEC-065 and DEC-066 set the prior-evening timing. Thresholds,
  channel, and deduplication belong to T-027 through T-031. Forecast guidance
  is informational and carries source and confidence limitations.

## Reusable local inputs and outputs

- Corrected development dataset v4:
  `5e88d13ff67e201ce8b0f23ed2d517d5af188e6185cd1496cab8798316bf7394`.
  See DEC-069 and the [ML workflow](../services/ml/README.md).
- Frozen XC model in `data/models/xc-probability/<model_id>/`:
  `5c469fdfebd87261f2070af6d0479cfbe8177d29982fc858cea27af1687e3cbc`.
  Fits use source seasons 2022–2024. The saved 300+ conversion is 3/42.
  DEC-070 defines the model, confidence and explanation semantics.
- Shared smoke GFS run `91ae8760-fdc2-4bd6-8f3f-af3bedc00e46` (2026-10-27
  06Z, D+1 for 2026-10-28). Use the verified bundles below as examples for
  integration. They establish output consistency. Forecast accuracy remains
  to be evaluated.
  - Cloudbase v2:
    `e5a7e9e636e26a9127ffd843319838333769a77a0f1b65b3f672ebb9ed174ea6`.
  - XC probability:
    `e59fa683563150a1bbb1bbef2590d37ba8e91505c636ffd82a47be3b56e68902`.
- The [ML README](../services/ml/README.md) documents the CLI and output
  contracts. For new XC predictions, retain SQLite, the model, the run ledger,
  raw manifest metadata, and the relevant interim stage manifests, receipt
  and feature batches. The hourly records verify coverage and readiness.
  Inference uses daily and profile-layer features. Archived GRIB payloads
  can stay off the hot workspace.

The owner runs real collection, preparation, training and prediction/replay
commands. The agent runs automated checks and verifies produced artifacts
read-only. Generated datasets, models, forecasts and SQLite remain local.

## T-024 owner acceptance

On 2026-11-10 the owner ran the four-key command. It stopped at the feature
lineage check. A read-only audit confirmed that the three historical examples
have effective builder v4 / contract 3, while the shared 2026 smoke run has
builder v5 / contract 3. All four match their validator input and SQLite
feature-manifest reference. The owner approved v4 support for OD. The reader
now verifies contract 3 and the packaged policy hash for the manifest's
explicitly supported builder version (v4 or v5). A read-only input check
loaded all four runs and 28 site-days with no missing observations.

The owner published that v5 smoke bundle
`1f353d75c7b737288bd6062d4215465715b1ff2f25a1fcd793038816f261292e`.
Read-only payload hash and size checks passed. It has seven results
(two low, five medium, zero high, zero missing).
All 705 distinct runs referenced by the frozen XC development dataset have
effective feature builder v4. The retained v4 D+3 run
`582c0173-2443-4b38-af9f-18d9aa03d2c8` for 2024-06-24 is a candidate for
the high-rain override at Vitosha (Kominite), with a peak of 8.81 mm in one
hour and 17.45 mm across the window. The owner published the mixed-version
bundle `dd62d58df9fdfefc0209b19398e818ba1e86e0238356f8d10e38b031f188bcb8`
with 28 complete site-days (11 low, 14 medium, 3 high). A read-only audit
verified all payload and source hashes, matched all 1,764 saved observations
to the validator samples and independently recalculated contributions, levels
and triggered rules. Vitosha and Zlatitsa triggered rain and convection
overrides, and Sopot triggered convection, all on 2024-06-24. The owner
repeated the batch with reversed run keys and reported the same ID,
`reused: true`, 702,607 published bytes and 0.387 seconds. Standalone replay
verified the same prediction ID and all 28 results.

Automated verification passed: 719 Python tests, including v4/v5 policy hash
checks, the synthetic installed CLI, concurrent publication and standalone
replay. Ruff lint and formatting, repository structure and whitespace checks
also passed.

Reproduce the four-run batch from the repository root:

```powershell
uv run --project services/ml --locked overdevelopment-predict `
  --run-key 91ae8760-fdc2-4bd6-8f3f-af3bedc00e46 `
  --run-key 55476291-4e2f-49a2-bdf9-86c6d863de35 `
  --run-key 6df60d46-a176-4906-8272-1b95ca3f4920 `
  --run-key 582c0173-2443-4b38-af9f-18d9aa03d2c8
```

The [ML workflow](../services/ml/README.md#t-024-offline-overdevelopment-baseline)
documents standalone replay. These acceptance checks establish reproducible
output from retained inputs. Meteorological calibration remains unverified.
