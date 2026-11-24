# Project handoff

## Where to resume

T-020 through T-023 are Done. The current local branch is
`feature/T-025-UI-data-integration`, with the T-024 baseline available.
The 2026-11-11 environment repair did not implement T-025 or change ticket statuses.
Use [tasks.md](tasks.md) for
status and [decisions.md](decisions.md) for accepted policy. Work on the
next requested ticket on top of the branch that supplies its dependencies.

- **T-024 overdevelopment baseline.** The offline `overdevelopment-predict`
  command implements the DEC-057 daily score and critical overrides. It
  verifies retained GFS lineage, publishes an immutable day-level bundle and
  supports read-only replay. T-024 is in Review after owner-run acceptance,
  reverse-order reuse and standalone replay.
- **T-025 confidence and drivers in the UI.** The home dashboard and detailed site/date route read
  published forecasts, including T-024 daily OD, through the SQLite-backed
  API. The ML phase stores validated forecasts in SQLite. The dashboard
  preserves units, provenance, missing states and confidence. Cloudbase has separate
  estimated and conditional LCL maxima. XC exposes low confidence for each
  available threshold, separate grouped contributions for P100 and conditional
  Q200, and a pooled 300+ conversion note. Contributions describe model
  calculations relative to the training reference.
  The [T-025 implementation plan](Т-025-implementation-plan.md) now covers
  the final detailed forecast iteration, including SQLite weather inputs,
  metric-specific explanations, the viewport layout and hourly cloudbase
  regimes. The accepted home dashboard is the starting point. The completed ML phase provides
  `forecast-publish` with the 16:00 Sofia source cutoff and one-shot
  `forecast-prune` for eligible GRIB files at least 48 hours after publication.
  The SQLite schema, transactional batch writer and `forecast-publish`
  orchestration are implemented. The owner applied the migration on the
  local macOS database. A read-only inspection found six new STRICT tables,
  20 applied migrations and an empty `PRAGMA foreign_key_check` result.
  At the publication checkpoint, 729 ML pytest tests, database tests and
  typecheck, `db:check`, repository structure and Ruff checks passed.
  For issue date 2026-11-16 the owner completed weather ingestion for all
  three horizons in a 793-second smoke attempt. The XC worker read the
  wrong return key after writing its bundle, so zero forecast publications
  were committed. The worker now reads `prediction_id`, with a regression
  test. Read-only checks found seven weather snapshots per horizon and
  verified payload digests and sizes for all nine predictor bundles.
  The owner retried offline in 1.38 seconds and reused all weather and
  predictor packages. Read-only SQLite confirmed publication IDs 1, 2 and
  3 for November 17–19, seven forecasts and 77 cloudbase hours each, and no
  foreign-key violations. All three were created at 01:05:14 Sofia on
  November 17 and reported the missed 20:00 November 16 deadline.
  Before 13:00 on November 17, automatic mode finds those three dates
  covered for the same model and exits without weather or predictor jobs.
  On November 17 the owner verified both CLI help screens. The dated
  offline retry took 0.048 seconds and returned the same IDs and creation
  times as `already_published`. The 09:18 Sofia automatic start took
  0.036 seconds and reported all three visible dates as `covered`, with
  no source probes or processing stages. A read-only query confirmed the
  original counts and timestamps after both retries. The owner also ran
  `forecast-prune`. It skipped all three runs as younger than 48 hours,
  freed zero bytes and reported no errors. The first live deletion check
  is available from 01:05:14 Sofia on November 19.
  The full 733-test ML suite passed, followed by a passing targeted schedule
  suite with the additional 01:07 no-op regression. All 255 npm tests,
  `db:check`, repo check, typecheck, lint, formatting, build, Ruff and
  whitespace checks passed. HTTP tests require local sockets and passed
  outside the sandbox. Prune's 48-hour boundary and interrupted cleanup
  were tested with disposable inputs.
  T-025 is in Review pending owner acceptance of the final detail page.
  Resume at the 2026-11-18 detail checkpoint below.
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

## T-025 summary presentation refinement — 2026-11-24

The owner requested three compact probability rows instead of the tall five-column
metric strip. The detail summary now stacks 100+/200+/300+ km with the previous
percentage/progress styling and each metric's own confidence, status and information.
Cloudbase and OD risk sit underneath in two equal columns. The owner then
requested removal of the daily-maximum footer: signed site AGL now appears
directly below MSL in smaller, normal-weight secondary text. The two weather
columns again show a Confidence prefix. Probability confidence levels sit
immediately beside their segments rather than at the far edge. Compact layouts use shorter rows and preserve
missing values and per-metric evidence. This updates the earlier detail presentation
choice; API and model semantics are unchanged. T-025 remains Review pending owner
visual acceptance. Reload the owner's running site to inspect the change.

Verification: all 145 web tests and 28 Playwright tests passed, including the
eight viewport/text settings and missing metrics. Web typecheck/build, root lint,
formatting, repo check and whitespace check passed. Desktop and compact screenshots
were inspected. Product servers and ML commands remain owner-run.

## T-025 detailed forecast checkpoint — 2026-11-18

The detailed forecast iteration is implemented and verified. T-025 is
**Review**, awaiting
owner acceptance of the real-data detail page. The home dashboard and ML
publication phases retain their earlier acceptance. No later ticket was started.
See [DEC-073](decisions.md#dec-073---read-published-details-and-exact-weather-evidence-in-one-viewport)
and the API/web/contracts READMEs for the new in-place local v1 detail shape.

The detail reader shares whole-publication selection, outputs and metadata
with summaries. It pins one prediction ID and reads its mandatory graph in a
short read transaction. The public response contains all 67 fixed XC fields,
eleven hourly OD/cloudbase contexts, five metric explanation groups and eleven
cloudbase hours. Exact provenance, quality, intervals, versions and missing
states survive the boundary. Invalid graphs fail with 5xx instead of mixing
publications or inventing missing values.

The page has the accepted summary design with per-card badges beside the SVG
icons, paginated inputs and explanations, and an SVG chart. It has no detail
map or previous-run placeholder. The chart distinguishes estimated cloudbase,
conditional LCL, blue, other cloud, uncertain and unavailable hours, separates
segments/gradients and marks the estimated-first daily maximum. Keyboard and
touch selection synchronize the hourly inputs. Information and tooltips have
compact pages. Valid direct dates remain exact outside the days window;
selectors, independent Retry and session caching until manual reload are covered.

**Verified automated checks:** 307 npm tests (database 38, contracts 27, API 98,
web 144), all 28 Playwright Chromium tests, repository check, Drizzle `db:check`,
repository-wide typecheck, lint, formatting, build and whitespace check passed.
HTTP/socket tests and Playwright ran outside the sandbox against disposable
fixtures. No product server, ingestion, prediction or replay command was run.
The build succeeds with Vite's advisory about a minified chunk above 500 kB.
Coverage was not rerun; the previously documented database coverage thresholds
remain unchanged.

Browser checks retain the accepted home coverage and exercise detail at
1440×900, 1366×768, 1280×720, 1280×600, 1024×768 and 390×844, plus 125% text
at 1280×720 and 390×844. Checks include section/article scroll extents,
pagination overlap, controls inside the viewport, missing P100/P200/P300,
missing cloudbase/OD, mixed regimes, mouse/keyboard/touch, Retry and no automatic
refetch after waiting, focus, visibility or reconnect. Screenshots of the
short desktop, compact 125% and mixed-regime fixture views were visually inspected.

**Read-only real-data verification:** the local database has nine publications
and 63 predictions covering 42 distinct site/dates (November 15–20). Every
selected detail passed its runtime contract and matched summary outputs,
metadata and publication time. `PRAGMA foreign_key_check` returned no rows.
For Vitosha on November 17, the selected cycle remains November 16 06Z despite
the later import of the November 14 cycle. P100 is 1.5651665136263144% (display
1.57%), OD is Low with score 0, and all 67 XC fields are available. Conditional
LCL appears at 12:00, 13:00 and 14:00 Sofia: 1922.1425605993536,
1995.610748742642 and 2062.375082968888 m MSL. The last is the daily maximum,
268.4460829688878 m site AGL; the other eight hours are blue. Stored P300 support
is 3/42. For November 18 the winner is November 17 06Z, published at 19:00:42
Sofia that evening, with P100 0.6974034959506479% and conditional LCL
1959.0916051993117 m MSL.

**Limits and remaining owner step:** the full consumed T-022 model column is
artifact-only, including levels below the launch. SQL stored weather LCL is
separate context. Exact heat-flux intervals are retained as stored; ambiguous
context stays unavailable while a pinned driver FK may still resolve its exact
interval. Missing exact driver inputs explain the artifact boundary. Forecast
calibration and independent evaluation remain outside T-025. The real-data UI
has not been accepted in the owner's browser yet.

The owner runs product commands. If the development servers are already
running in SQLite mode, reload the page. Otherwise, from the repository root:

```sh
FORECAST_DATA_MODE=sqlite npm run dev
```

Open [Vitosha detail for November 17](http://localhost:5173/forecast?site=sofia-vitosha-kominite&date=2026-11-17).
Confirm the values/time above, input groups and all five explanations, the
three conditional hours and blue gaps, hour synchronization, and `All sites`
return navigation. [November 15](http://localhost:5173/forecast?site=sofia-vitosha-kominite&date=2026-11-15)
is an available direct date outside November 18's five-day window. No new
weather acquisition or prediction is required. Mark Done only after acceptance.

## T-025 home dashboard checkpoint — 2026-11-17

The home route reads the active SQLite site catalog and selects one published
forecast per site and exact Sofia date. It displays per-metric confidence and
limitations in the information panels, keeps unavailable date slots disabled
and fits the overview, comparison cards, date strip and Leaflet map in one
viewport. Mock mode serves the existing detail flow. See
[DEC-072](decisions.md#dec-072---read-published-sqlite-forecasts-on-the-home-dashboard).

Automated verification passed for 268 npm tests and 13 Playwright tests.
Chromium covered 1440×900, 1366×768, 1280×720, 1280×600, 1024×768, 390×844,
and 125% text at 1280×720 and 390×844. The integration gates include
typecheck, lint, build, formatting, repo and Drizzle checks, and
`git diff --check`. The separate root coverage command stopped at the
database workspace's 90% thresholds. Commit `52420d6` also fails those
thresholds with 65.35% lines and 36.84% functions.
The contracts, API and web workspaces passed their coverage thresholds.

Read-only SQL verified seven local publications per date on November 17–19
from the November 16 06Z cycle. They were written at 01:05:14 Sofia time on
November 17. The owner ran the dashboard command and accepted the initial
SQLite integration, then requested the presentation refinements below. From the repository root on macOS:

```sh
FORECAST_DATA_MODE=sqlite npm run dev
```

Open [the dashboard for November 17](http://localhost:5173/?site=sofia-vitosha-kominite&date=2026-11-17).
On the November 17 Sofia date window, the 15th and 16th are disabled and the
17th through 19th are available. Vitosha shows 1.57% P100, Conditional LCL
2,062 m MSL and Low OD risk. Pastrina shows Blue on the 17th. The information
panel should show the GFS cycle and publication time above. The shell prefix
overrides the existing local `.env` mock setting for this launch. Set
`FORECAST_DATA_MODE=sqlite` in `.env` to make that choice persistent.

## T-025 owner presentation refinements — 2026-11-17

The owner accepted the SQLite dashboard and requested a closer initial map,
the P100 status badge beside its percentage, more space below comparison
headings and a slightly taller Other locations section.

The map now uses asymmetric bounds padding and quarter-step zoom fitting.
Browser checks verify all seven pins stay inside the map at every tested
size and the labels fit at desktop sizes. Comparison badges use the P100
metric's own status with compact Baseline/Mock labels. Missing P100 carries
an Unavailable badge and retains the metric's reason. After the owner's screenshot review, the comparison card's flexible free
space sits between the header and percentage row. The confidence footer
follows the cloudbase/OD row directly. Wide grid rows give comparisons
more height while keeping them shorter than overview. The stacked layouts
also retain the viewport fit.

Verification passed for 126 web tests, 13 Playwright tests, strict web
typechecking/build, repository-wide lint, formatting, repo checks and
whitespace checks. Playwright covers the previous eight viewport/text settings,
the comparison/overview height relationship, and all seven map pins.
The owner also requested individual status badges on all five overview
metrics. Each metric now shows its own compact uppercase status beside its icon,
including Unavailable for a missing metric. The owner then requested more
vertical breathing room. Overview metric cards now increase their top and
bottom padding on wide screens in proportion to viewport height. Mixed-status component coverage
and all 13 browser checks passed after this addition.

T-025 remains In Progress for the following detail/explanation iteration.
Reload the owner's running dashboard to inspect these presentation changes.

## Local macOS fresh start — 2026-11-11

The owner intentionally migrated a new empty SQLite database instead of
restoring historical data. Its GFS offline preflight passes, including the
current schema, reviewed site elevations/sampling and local usage policy.
There are zero weather runs and no `data/interim/weather` in this checkout.
The historical run keys and prediction bundles below are prior acceptance
references, not available inference inputs on this machine. New inference
requires a new successful `weather-ingest fresh` run; restoring the old database
or rebuilding the training study is unnecessary.

The inherited uv lockfile omitted the native ecCodes library on macOS/Linux.
Explicitly locked `eccodeslib==2.47.3.23` for those platforms while preserving
`eccodes==2.47.0` and all existing numerical package versions. Removed the
unnecessary direct pandas addition; it remains installed transitively.
Pinned `.python-version` to 3.12.10 and recreated `services/ml/.venv` with uv
to match the retained frozen XC model exactly. The model's manifest, payload
hashes, packaged policy and numerical environment all pass `read_bundle`.
No model or real weather data was modified. The test migration fixture now
uses `npm` on macOS/Linux and `npm.cmd` on Windows.

The ignored local `.vscode/settings.json` now discovers `services/ml/.venv`
instead of preferring system Python. Actual editor interpreter selection was
not verified through the UI. If diagnostics remain, use **Python: Select
Interpreter** → `services/ml/.venv/bin/python`, then **Developer: Reload Window**.
See the [ML environment setup](../services/ml/README.md#environment-setup) for
repeatable setup, checks and zsh/bash fresh-ingestion/prediction templates.

Verification on Apple Silicon macOS: **719 Python tests passed**; Ruff lint
and formatting (232 files), npm repository check, database migration metadata
check, TypeScript typecheck and `git diff --check` passed. ecCodes self-check
finds native API 2.47.3 in the uv environment. GFS and all three prediction
CLI help commands load successfully. A single HTTPS HEAD to the official NOAA
GFS S3 endpoint returned 200 using the managed Python's certificate trust.
No live weather collection, training or real prediction was run; those remain
owner-run operations. Full tests required escaping the agent sandbox because
tsx opens a local IPC socket for disposable test-database migrations.

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
