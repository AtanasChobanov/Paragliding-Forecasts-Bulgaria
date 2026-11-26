# Project handoff

## Where to resume

**Owner acceptance — 2026-11-26:** T-025 is complete. The owner committed the
final presentation corrections in `8c39cb0` and authorized the implementation-plan
deletion and completion documentation commit. The requested PR description is a
local, uncommitted draft; do not include it in a commit or open/push a PR implicitly.

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
  The completed detail page includes SQLite weather inputs, metric-specific
  explanations, the viewport layout and hourly cloudbase regimes. Accepted
  behavior is recorded in DEC-071 through DEC-075 and the API/web/contracts
  READMEs; the finished implementation plan has been removed. The completed ML phase provides
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
  T-025 is Done after owner acceptance and the final verification recorded
  in the 2026-11-26 completion checkpoint below.
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

## T-025 completion checkpoint — 2026-11-26

The owner accepted the final detail page and requested a PR description for
`feature/T-025-UI-data-integration` into
`feature/T-024-baseline-overdevelopment-risk`. T-025 is now Done; T-024 remains
Review. Do not start T-026 without a new request.

The completed implementation plan was deleted, and its Markdown links were
replaced with the durable workflow/decision documentation. The local PR draft
is `docs/T-025-pr-description.md`, intentionally uncommitted for the owner to
copy and delete. No remote PR, push or merge was requested.

Final verification on the committed product code (`8c39cb0`):

- `npm run test`: 314 tests passed (38 database, 27 contracts, 98 API, 151 web).
- `npm run test:browser`: all 31 Playwright tests passed, including the six
  desktop/mobile sizes and the two 125% text settings described below.
- `uv run --project services/ml --locked pytest`: 734 tests passed.
- Root typecheck, lint, format check, build, repo check, database `db:check`,
  Ruff lint and Ruff format check passed. Documentation and whitespace checks
  were repeated after the plan removal.

HTTP/browser checks used disposable fixture servers and databases. No product
API/web server, ingestion, prediction, publication or pruning command was run
for this completion check. The existing Vite main-chunk size advisory remains.
Coverage was not rerun; the previously documented database coverage threshold
failure remains a separate limitation. Aged live GRIB deletion has no later
owner acceptance recorded here; boundary/deletion/resume behavior is covered
by disposable tests, while the owner-run check below verified younger-run skips.

Final presentation uses bounded scrolling instead of pagination, 35vh anchored
information popovers, shared left-aligned 60%/40% evidence columns and rounded
presentation values. Hourly evidence retains quality, statistic, source record
ID and actual intervals. Home overview and Other locations information show
common publication metadata; detailed metric explanations stay on the detail
page. These changes are included in `8c39cb0`.

The following entries are historical checkpoints. Their references to
uncommitted work and pending acceptance describe the state at that time;
the completion checkpoint above supersedes them.

## T-025 Recharts migration — 2026-11-25

2026-11-26 owner refinement (uncommitted): Other locations information now also
shows only common source/publication/model metadata, matching overview. Per-metric
notes remain in the detail page. No commit made.

Pagination cleanup audit (2026-11-26, uncommitted): confirmed the Pagination
component/styles and MeasuredPages files are deleted. No pagination imports,
page state, capacity logic or pagination CSS remain in web source. Removed the
stale data-page-row browser selector and paginated-tooltip test wording; updated
obsolete instructions in the implementation plan. Negative assertions verifying
absence of pagination, explanatory documentation and historical decisions remain.
Verified: 151 web tests, web typecheck/build, root lint, formatting/repo and
whitespace checks passed. No product servers or ML commands were run. No commit made.

2026-11-26 owner refinement (uncommitted): the home overview information now
shows only common publication/source/model metadata. Per-output probability,
cloudbase and OD details remain on the detail page; other location cards are
unchanged. No commit made.

2026-11-26 owner refinement (uncommitted): cloudbase and OD result cards show
the value before the label/information button, including compact layouts. Four
targeted browser checks (desktop/mobile/125% text and footer alignment), formatting
and whitespace checks passed. No commit made.

Latest column correction: all input/evidence popovers now use one shared 60%/40%
label/value layout at every screen width, including hourly chart metadata.
Values in the right column are left-aligned (the owner reverted the right-alignment trial).
The hourly and narrow-screen ratio overrides and default definition-value margins
were removed. Two targeted browser tests verify actual column proportions;
formatting and whitespace checks passed. No commit made.

Latest hourly evidence refinement (uncommitted): weather values inside the hourly
chart tooltip use presentation rounding/conversions while statistic, quality,
source record ID and other metadata remain visible. The latest owner correction sets label/value columns to 60%/40%
in this tooltip. Intl range formatting avoids repeated dates in same-day intervals
and retains dates across day boundaries, with Sofia local times. Verified: 151 web
tests, two targeted browser tests, typecheck, lint, formatting and whitespace checks
passed. No product servers or ML commands were run. No commit made.

Latest anchoring fix (uncommitted): detail information popovers remain next to
the triggering icon, above or below according to available space. Long content
no longer moves the box to the viewport's top edge. The maximum stays 35vh,
further limited by space on the chosen side; content scrolls within that box.
This supersedes the earlier viewport-top fallback. Verified: 150 web tests,
three targeted browser tests (including anchor position before/after scrolling),
typecheck, lint, formatting and whitespace checks passed. No commit was made.

Latest uncommitted refinement: detail popovers and hourly tooltips are capped at
35vh, with no fixed pixel cap (latest owner correction). The cap applies to all
detail result popovers as well. The 35vh change passed typecheck, formatting,
whitespace checks and two targeted browser scroll/touch tests. Why this result input values now reuse the same
presentation rounding and unit conversions as Forecast inputs. Verified: 150 web
tests, 31 browser tests, web typecheck/build, lint, formatting, repo and whitespace
checks passed. No product servers or ML commands were run. No commit made.

Current uncommitted scrolling refinement (supersedes pagination notes below):
the owner requested removal of pagination throughout the detail page. Inputs and
Why this result now use `ScrollableList` with every row mounted and internal
vertical overflow. All detail popovers and the hourly tooltip show continuous
structured content, bounded to 420 px / 70% viewport height, with scrolling.
The pagination component, measured page capacity and word-count splitting are
removed. Driver topics remain headings within one scrollable view. Name/value
columns reserve 60%/40% on wide screens and 45%/55% on narrow screens, with intact
numeric values. Home remains unchanged. DEC-075 and the plan/README record the
owner-approved interaction change. Source record ID and compact driver input
pairs from the preceding uncommitted refinement are retained. No commit made.
Verification: all 150 web tests and 31 Playwright tests passed, including all eight
viewport/text settings, keyboard-focusable list scrolling, last-row reachability,
continuous hourly information and long names/whole numeric values at 125% text.
Web typecheck/build, root lint, formatting/repo and whitespace checks passed.
Long-evidence, compact-page and hourly-tooltip screenshots were inspected.
An interrupted test run left two verified fixture API processes; only those test
processes were stopped before the successful rerun. Product servers and ML
commands were not run. T-025 remains Review pending owner visual acceptance.

Current uncommitted refinement: Why this result input evidence now lists only
input names and exact canonical values/units, with explicit Unavailable states.
Statistics, quality, record IDs, timestamps and layer details remain in Forecast
inputs, not repeated in drivers. Its label is now Source record ID. Up to eight
compact pairs stay with the driver calculation; larger sets retain topic pages.
Verification: 150 web tests, 30 browser tests, web typecheck/build, root lint,
formatting/repo and whitespace checks passed. No product servers or ML commands
were run. No commit was made, per the owner's new instruction.

Latest information refinement: shared height-reference/cloud-formation guidance is
now in an information button after the Hourly cloudbase time range. Cloudbase
result information still contains its matching site/model AGL readings. Inputs
use a single labeled metadata view without repeating the row name or rounded
value; canonical numbers remain when they add precision or different units.
Statistics, quality, source records, true intervals and layer bounds are retained.
Why this result now groups explanation/calculation fields and exact inputs with
headings and definition lists. Up to three linked inputs stay with the calculation;
larger sets use meaningful pages grouped by topic, with viewport-aware scrolling
and repositioning. Explanation limitations use one structured view. List pagination
and the hourly point tooltip are unchanged. Home is unchanged.
Verification: 150 web tests and 30 browser tests, web typecheck/build, root lint,
formatting/repo and whitespace checks passed. Product servers and ML commands
were not run; browser tests used disposable fixture servers.

Latest owner refinement: height-reference and cloud-formation guidance now lives
in the cloudbase result's information, not the general metadata popover. The
cloudbase card shows only MSL; matching site/model AGL readings (including signed
site AGL) are in its information. Missing readings remain explicit. Weather-card
body tracks use natural rows instead of a stretched reading track to compensate
for an extra AGL line. Confidence footers remain aligned. The longer cloudbase
popover can use the full viewport height instead of clipping to the anchor side. The hourly chart tooltip
is unchanged. Verification: 147 web tests, 29 browser tests, web typecheck/build,
root lint/formatting/repo and whitespace checks passed. Product servers and ML
commands were not run.

Summary information follow-up: the general popover now reuses the home metadata
layout (source, publication, cycle, horizon, XC model, cloudbase method, OD policy),
followed by shared height-reference/cloud-formation guidance. Per-output evidence
is excluded. P100/P200/P300, cloudbase and OD popovers now show labeled explanation
and limitation sections together without pagination or a repeated status/confidence
page. Known cloudbase/OD limitation flags have explicit user-facing explanations;
unknown codes retain their words with separators removed. Missing reasons remain
visible. Home popovers and input/driver/hourly pagination are unchanged.
Verification: 147 web and 29 browser tests, web typecheck/build, lint, formatting,
repo and whitespace checks passed. Product servers and ML commands remain owner-run.

Owner follow-up: X-axis ticks now show `HH:mm`, with Recharts thinning labels
when needed. The tooltip's first page has a large primary MSL reading, secondary
site/model AGL, the shared confidence meter and a daily-maximum badge when
applicable. Reasons, hour/regime, notes and exact inputs remain paginated after
the summary. The close button was removed; hover leave, outside press and Escape
retain their previous dismissal behavior. Missing numeric values remain explicit.
Verification: 146 web and 29 browser tests, web typecheck/build, root lint,
formatting, repo and whitespace checks passed. The browser checks cover formatted
ticks across all eight viewport/text settings and capture the mobile tooltip.
Product servers and ML commands were not run.

The owner approved Recharts after a read-only comparison of chart libraries.
The hourly cloudbase plot now uses Recharts 3.11.1 for responsive sizing, SVG
axes/grid, linear lines, segment areas and the selected-hour reference line.
`CloudbasePlot` is loaded on demand; the home page does not load Recharts.
The web workspace owns Recharts and an exact `react-is` 19.2.8 dependency,
matching React. A root override scoped to Recharts prevents npm from selecting
the older test-tool peer; `npm ls react-is` verifies both remain correctly
resolved. See DEC-074 and the updated implementation plan/web README.

Each contiguous estimated/conditional segment retains its own gradient, line
style and markers; isolated points and the estimated-first daily maximum remain.
There is no interpolation across missing hours or regime changes. The themed
regime band uses Recharts plot/scale hooks. The adjacent DOM controls preserve
one roving keyboard focus path, all eleven hours (including all-null days),
hover/click/touch, Home/End and synchronization with hourly inputs. The existing
paginated React portal tooltip retains heights, signed AGL, confidence and exact
context. Recharts' parallel keyboard layer and line/area animations are disabled.
The main summary and API/model semantics are unchanged.

Verification: 146 web tests and 29 Playwright tests passed. Tests exercise real
Recharts paths/markers/gradients, null-hour selection, isolated/negative heights,
keyboard and touch, and hour-control/band alignment at all eight viewport/text
settings. Web typecheck/build, root lint, formatting, repo and whitespace checks
passed. Desktop, compact 125% and mixed-regime screenshots were inspected.
The build produces a separate chart chunk (~415 kB minified / 120 kB gzip);
the existing >500 kB main-chunk advisory remains. A repository-wide npm audit
reported 25 advisories in existing dependency locations; none of the newly added
package locations were flagged. Unrelated dependency upgrades were not attempted.
T-025 remains Review pending owner visual acceptance. Reload the owner's running
site to inspect it. Product servers and ML commands remain owner-run; Playwright
used disposable fixture servers.

## T-025 summary presentation refinement — 2026-11-24

The owner requested three compact probability rows instead of the tall five-column
metric strip. The detail summary now stacks 100+/200+/300+ km with the previous
percentage/progress styling and each metric's own confidence, status and information.
Cloudbase and OD risk sit underneath in two equal columns. The owner then
requested removal of the daily-maximum footer: signed site AGL now appears
directly below MSL in smaller, normal-weight secondary text. The two weather
columns again show a Confidence prefix. Probability confidence levels sit
immediately beside their segments rather than at the far edge. A further owner
refinement groups probability icons/status/information on the right, with confidence
on a second row below. Weather cards use equal body/footer tracks, keeping both
confidence strips flush with the bottom border despite the extra AGL line.
The owner tried compact centered weather confidence groups, then requested
restoring the previous spread layout: Confidence left, segments middle and level right.
Compact layouts use shorter rows and preserve
missing values and per-metric evidence. This updates the earlier detail presentation
choice; API and model semantics are unchanged. T-025 remains Review pending owner
visual acceptance. Reload the owner's running site to inspect the change.

The detail inputs and compact explanation selectors now share a `DetailSelect`
presentation with leading SVG icons, a primary border and a custom chevron,
matching the location/date controls. One reusable `Pagination` component serves
measured input/driver lists, information popovers and cloudbase tooltips. It uses
styled arrow buttons and current page / total page text (`1 of 3`), including
disabled boundary arrows and `1 of 1` when everything fits. Measured lists still
recalculate totals from available row capacity. Native select behavior, keyboard
access and accessible arrow names are preserved. The home dashboard is unchanged.
The compact controls also fit at 125% text. No product servers or ML commands
were started; browser tests used their disposable fixture servers.

Verification: all 146 web tests and 29 Playwright tests passed, including the
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
