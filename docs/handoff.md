# Project Handoff

## Requested scoring-count refactor — 2026-11-06

The owner requested plain-language explanations of model selection and a code
change removing unexplained numeric component counts. Added scoring_layout.py:
named policy-derived horizons, validation seasons, C grid and model stages,
explicit evaluated/selection threshold sets, an ordered Cartesian component-key
builder, and derived component/candidate/fit counts. Selection schemas and
arithmetic now use the derived 12-component count; trial schemas/means use
the derived six-component count and nine-candidate count. CLI fold choices,
study grouping/folds and horizon weight allocation use the same named axes.
No C grid, scoring policy, probability calculation, input contract or artifact
version was expanded. Existing report wording is preserved for byte identity.

The current axes still give twelve selection components. A permanent test
checks a changed 3-season/4-horizon/3-threshold layout yields 36 distinct keys,
in addition to current-axis and existing aggregation/gating tests. The model
and weather v1 contracts deliberately retain their version-specific supported
categories/shapes; future extensions need compatible versions and training.
No real product command, selection, fit, download or prediction was run.
The real select stage remains the owner-run checkpoint described below.

Validation: **648 tests passed in 57.12 s**; Ruff lint/format passed for
218 Python files; repo:check and diff whitespace checks passed. Read-only
reload of the real study and both trial IDs passed again with fitting blocked,
including exact report/hash compatibility. Confirmed development population
weight 736 and positive weight totals 212/42/3 for explanatory examples.
The focused follow-up commit is `T-023 derive scoring counts from configured axes`;
temporary planning notes remain excluded.

## Owner-run trial 2024 review and selection/final implementation — 2026-11-05

The second owner-run trial passed review. Trial ID:
`829b1b7e266d397854d3f87f1f1ca366fe5207c4b0e688338948c62eefd5e89e`.
Parent study remains
`0eda3e7d8e582d97e52a76eaf110b92b8209855785dd3a1664334963a1ceab2b`.
Measured command time: **2.358427 s**; published size: **1,464,520 bytes**.
Read-only compact reload verified hashes, source/model/scaler/reference
lineage, all predictions/diagnostics and report. The review blocked fitting,
SQLite, network access and weather-history verification. Independent Brier
calculations matched all 54 components and nine fold means within 1e-15.

Verified six fits, nine candidates, 600 training/360 validation rows and
3,240 prediction records. The p100 models use 200 site-days with 96 positive
100+ outcomes; q200 uses 96 site-days with 23 positive 200+ outcomes. Their
normalized weight sums are 200 and 96 within floating tolerance. Iterations
for C=0.03/0.1/0.3 are 30/47/76 (p100), 21/31/49 (q200). Every p300 is
available and equals p200*2/23. All nine fold mean Brier scores improve on
constant **0.1368382219687292** (log loss **0.42955725195023436**). The lowest
fold mean Brier is **0.11885410818324776** at C100=0.03/C200=0.1, with log loss
**0.36493484124595016**. This is development evidence, not final selection or
independent reliability. Confidence remains low; 2025 remains reserved.

Implemented planned unit four, `T-023 select and persist final XC models`:
`select` requires exactly two distinct validated trials for the same study,
one per chronological fold. It freezes all twelve equally weighted score
components for each candidate and the constant comparator. Brier ties are
anchored to the global minimum within absolute 1e-12, then lower mean log
loss, smaller C100 and C200. Trial argument order does not affect the ID.
No-improvement cases retain the selected logistic recipe and explicit limits.

`train-final` requires a verified selection and revalidates both trials before
two fresh fits on the final weight partitions, using all development rows.
There is no manual C bypass or inherited fold purge. JSON models retain
ordered coordinates/categories, scaler/coefficients/reference/baseline,
support, source-row digests, numerical probes, computed k/n and frozen
confidence/group/template policies. An embedded selection snapshot and stable
manifest identity permit checking selection bytes/parents without opening its
original files. `load_model` verifies the standalone model bundle and numerical
probes without study/trial/dataset/SQLite access. Grouped logit contributions
reconstruct each stage's decision function within absolute 1e-12. Final bundles
have only model.json, policy.json and manifest.json; no redundant report.

Verification: **647 Python tests passed in 60.93 s**; Ruff lint/format passed
for 217 Python files; repository structure and diff whitespace checks passed.
Fourteen new synthetic cases exercise twelve-component aggregation, ordered
tie breaks, missing/duplicate/wrong-source trials, no constant fallback,
selection-gated fitting, convergence failure, full-development refit,
standalone reload, dynamic 2/9 conversion, grouped reconstruction, tampering,
CLI gates and deterministic selection/model reuse. The shared typed XC fixture
moved to conftest; the previous training tests still pass. All fitting in this
implementation unit was synthetic. No real select, final fit, prediction,
download, T-022 replay or SQLite write was performed by the agent.

**Next owner-run checkpoint:** run only selection from the repository root:

```powershell
uv run --project services/ml --locked xc-probability select `
  --study-id 0eda3e7d8e582d97e52a76eaf110b92b8209855785dd3a1664334963a1ceab2b `
  --trial-id 6179a5a6f9878c00b30611390189f687eb4a9fb22fc968b5e8ee7c4e69024d57 `
  --trial-id 829b1b7e266d397854d3f87f1f1ca366fe5207c4b0e688338948c62eefd5e89e
```

Review the returned selection ID, all nine scores, twelve-component means,
tie-break winner, baseline comparison, parents and measured time/bytes.
After that review, provide the already implemented train-final command using
the actual selection ID. Expect 960/480 final fit rows and computed 3/42.
Do not run either real command for the owner. Only after the real final model
is reviewed proceed to planned retained-GFS prediction implementation. T-023
remains In Progress. All three temporary T-023 notes remain uncommitted and
intact; the earlier 2023 review update is included with this implementation.

## Owner-run trial 2023 review — 2026-11-05

The owner ran the first real `train-trials` stage successfully on implementation
commit `a237c9a`. Trial ID:
`6179a5a6f9878c00b30611390189f687eb4a9fb22fc968b5e8ee7c4e69024d57`.
Parent study:
`0eda3e7d8e582d97e52a76eaf110b92b8209855785dd3a1664334963a1ceab2b`.
Owner-measured elapsed time: **2.133453 s**; published bytes: **1,270,006**.

Read-only compact reload passed manifest/file hashes, numerical versions,
parent identity, training-only scalers/references/support, stored sklearn
probes, all validation predictions, recomputed diagnostics and report. The
review explicitly blocked classifier fitting, SQLite/network access and the
joined-weather verifier. An independent calculation also matched all 54
per-candidate/horizon/threshold Brier components and the nine fold means
within absolute 1e-15. No real training was rerun by the agent.

Verified counts: six fits, nine combinations, 282 training/318 validation
rows and 2,862 prediction records. p100 fits used 94 unique site-days and
normalized weight sum 94; q200 used 43 positive-100+ site-days, 10 positive
200+ outcomes and normalized weight sum 43. Iterations for C=0.03/0.1/0.3
were 22/38/53 for p100 and 18/23/36 for q200. The pooled conversion is
unsupported 0/10. Every p300 prediction and every 300+ score is missing with
insufficient_300_support; no zero substitute entered evaluation.

All nine combinations have lower mean weighted development Brier than the
training-only constant comparator (**0.13356361513739132**, log loss
**0.41775464108426236**). The lowest fold Brier is
**0.1216948099846877**, with log loss **0.37016326132742217**, at
C100=0.1/C200=0.03. This is a single-fold diagnostic, not final selection or
independent model validation. Keep the predeclared grid, low confidence and
uncalibrated baseline semantics. The 2025 reserve remains untouched.

**Next owner-run checkpoint:** the already implemented second trial:

```powershell
uv run --project services/ml --locked xc-probability train-trials `
  --study-id 0eda3e7d8e582d97e52a76eaf110b92b8209855785dd3a1664334963a1ceab2b `
  --fold 2024
```

Expect six fits, nine combinations, 600 training/360 validation rows,
3,240 prediction records and supported training k/n=2/23. Review that artifact
after the owner reports execution, then implement the next planned
selection/final-model unit. Do not run the command on the owner's behalf.
No implementation change was needed in this review; the previous full-suite
result remains 633 passed. T-023 remains In Progress. This operational update
can accompany the next planned implementation commit; the three local
temporary T-023 documents remain uncommitted and intact.

## T-023 implementation checkpoint — 2026-11-02

Implemented the first three planned units on `feature/T-023-baseline-XC-model`:
the frozen 67-input/82-coordinate policy/contracts, verified chronological
study preparation and weighted conditional trial training. Commits:
`42de152 T-023 define XC probability policy and artifact contracts`,
`c9a9980 T-023 prepare verified chronological training studies`, followed by
`T-023 train weighted conditional XC baselines`. The exact scikit-learn 1.9.1
dependency and uv lockfile are installed/committed. Selection, final fitting
and retained-GFS prediction remain unimplemented.

`xc-probability prepare` calls the existing joined-v4/correction verifier once,
rechecks the consumed source bytes, joins source seasons from cohort metadata,
separates physical inputs from labels and sampling controls, and publishes a
frozen study. It retains all 67 inputs with unit/quality/provenance, original
sampling metadata, 82 coordinate identities, site categories, temporal folds
and six p100/q200 training-weight partitions. Per-stage unique site-day weights
are normalized then split across horizons without renormalizing rows. Fold
purges do not change the final fit partition. Invalid/missing training evidence
fails instead of silently dropping rows. The compact loader verifies hashes,
schemas, versions, source identity, folds and weights without traversing the
weather history. No classifier is fitted by preparation.

The owner clarified that dependency setup and technical checks are agent-run;
only real prepare/train-trials/select/train-final/predict commands are owner-run.
The owner also accepted removing redundant Markdown reports and separating
runtime metadata from content identity. Study, final-model and prediction
bundles use authoritative JSON; future trial/selection Markdown will summarize
comparisons/limitations. The implemented atomic publisher keeps the first
creation/execution metadata on reuse. Manifest timing is measured before
publication; stdout reports the current command's elapsed time and actual bytes.

The owner ran preparation successfully. Study ID:
`0eda3e7d8e582d97e52a76eaf110b92b8209855785dd3a1664334963a1ceab2b`.
Owner-measured command time: **23.076731 s**; published size:
**46,694,941 bytes** (including the retained per-field provenance). Read-only
`load_study` review passed file/manifest hashes, numerical compatibility,
source identities, regenerated folds and all six weight partitions. Counts:
960 rows, 320 site-days, 235 dates, 160/42/3 positives, original unique
site-day weight sum 736. Fold 2023 has 282/318 training/validation rows,
cutoff 2022-09-28, no purges, k/n=0/10; fold 2024 has 600/360 rows,
cutoff 2023-10-02, no purges, k/n=2/23. Normalized weight sums are
94/43 for p100/q200 in fold 2023, 200/96 in fold 2024 and 320/160 final.
This review did not fit a classifier or rerun the full joined verifier.

`train-trials` now encodes all 82 inputs and fits six weighted stage/C variants
per fold, then composes nine validation candidates. Each stage owns training-only
weighted scaler/reference; only 72 continuous coordinates are standardized.
The sklearn 1.9.1 API expresses L2 through l1_ratio=0.0; the accepted lbfgs,
intercept, C grid, tolerances and one-thread policy are unchanged. Class absence
or convergence warnings fail without retry/fallback/partial publication. Saved
JSON parameters are checked against sklearn on all fit and validation rows
at absolute 1e-12, with compact probes retained for reload. k/n is computed
from unique effective training site-days. A 0/n ratio remains diagnostic;
unsupported 300+ predictions and metrics are missing.

Trial bundles retain six fitted states, validation predictions, weighted
diagnostics and a deterministic comparison report against training-only
constant rates. Brier/log loss, ROC-AUC/AP where defined, raw/weighted confusion
counts, weighted precision/recall at diagnostic 0.5 and five fixed calibration
bins are reported per horizon and pooled. Fold mean selection components give
equal weight to 100+ and final 200+ across three horizons; 300+ is excluded.
No final selection or calibrator is fitted. Reload verifies scaler/reference,
probes, predictions, metrics and report without refitting or weather history.

Verification: the full local Python suite passed **633 tests in 47.87 s**;
Ruff lint/format passed for 214 Python files; `npm.cmd run repo:check` and
`git diff --check` passed. Eleven new synthetic tests cover direction/leap-year
encoding, weighted scalers/reference, leakage, class/convergence failure,
independently computed metrics, six fits/nine candidates, unsupported 300+,
JSON probes, deterministic reuse and semantic tampering. Normal Windows
filesystem permissions were used for existing temporary-file/hard-link tests.
Only synthetic classifiers were fitted. No real trial training, final fit,
prediction, T-022 replay, download or SQLite mutation ran.

**Owner-run checkpoint:** from the repository root, run only this next stage:

```powershell
uv run --project services/ml --locked xc-probability train-trials `
  --study-id 0eda3e7d8e582d97e52a76eaf110b92b8209855785dd3a1664334963a1ceab2b `
  --fold 2023
```

Review the returned JSON and ignored trial artifact after the owner reports
success. Expect six fits, nine candidates, 282 training/318 validation rows,
2,862 validation prediction records and unsupported 300+ with stored 0/10.
Review convergence, all candidate diagnostics, training-only constant rates,
300+ missing reasons and content/reload integrity. Capture actual trial ID,
time and bytes; synthetic tests do not establish real model quality. After
review, the already implemented next owner command uses the same study with
`--fold 2024` (600/360 rows, 3,240 predictions, k/n=2/23). Do not run either
on the owner's behalf. Both successful owner-run trials are needed before
the next planned selection/final-model implementation unit. T-023 remains
In Progress. All three temporary T-023 notes remain local, uncommitted and
intact; durable operation is documented in DEC-070 and the ML README.

## Plan consolidation — 2026-11-02

At the owner's request, updated the locally saved
consolidated implementation plan with the follow-up discussion: required
67-input inventory, automatic reuse of existing dataset verification, no new
generic verify CLI, one predict command with run keys and bundled exact inputs,
computed/stored training k/n for 300+, grouped local stage drivers/templates,
initial per-metric low confidence with reasons, tests/completion gates, manual
workflow, resource estimates and staged development commits. Explanation
implementation details concretize the recommended approach in the plan; they
are not evidence of implemented behavior or statistical validation. Independent
2025 evaluation does not automatically promote confidence or tune a calibrator.
The implementation plan itself must remain local and uncommitted, alongside
the two earlier temporary notes. Future implementation commits must document
necessary behavior in tracked decisions/READMEs without requiring these files.
No code/dependency/data change, training, prediction, staging or commit occurred.
Validation: `npm.cmd run repo:check` and `git diff --check` passed. A read-only
document check confirmed the copied 43+11+13 inventory, balanced code fences,
no trailing whitespace and absence of obsolete manual commands from examples.
The staged file list is empty. No model-quality or product test is claimed.

## Planning follow-up — 2026-11-01

Confidence discussion (recommendation only, not a new accepted policy): define
the Python confidence semantics in T-023; T-025 owns API/UI presentation and
T-026 independent evaluation. Existing contracts use low/medium/high plus a
note, with null confidence for missing metrics. Recommend an explicit v1
evidence policy returning low for every available XC baseline estimate, with
per-threshold reasons and training support; never derive this label from the
probability magnitude or the presence of all required inputs. There is no
documented formula requiring all three levels to appear. Separate calibration
of event probabilities from uncertainty about estimated probabilities.
Official scikit-learn calibration, SciPy bootstrap and MAPIE documentation were
reviewed. No extra confidence dependency is recommended for v1. A later
grouped/temporal-block bootstrap with refitted weighted pipelines could assess
training-data sensitivity, but does not alone establish calibration or cover
forecast error/reporting bias. Do not resample the 960 rows as independent
observations, claim conformal classification sets are probability intervals,
or tune confidence thresholds/calibrators on the reserved 2025 evaluation and
then report it as untouched. Dynamic confidence thresholds need a separate
validated policy; they are not selected in this discussion. No model was fitted.

Owner explicitly accepted that all 67 selected physical inputs are required.
New discussion: brief/Takt-4 and T-025 require confidence/top drivers; the
current UI already renders topDrivers strings in "Why this result", supplied
by the mock API repository. Recommendation under discussion (not yet an
accepted explanation policy): T-023 emits faithful structured local drivers
from grouped coefficient-times-deviation contributions, separately for p100
and q200; T-025 owns real API/UI composition/localization. Explain the 300+
pooled empirical conversion as a method/support note, not an independently
learned weather driver. Do not treat raw coefficients as local contributions,
sum logit contributions as percentage points, or assert physical causality.

Owner requested simpler prediction orchestration: remove the planned public
`prepare-inputs` command and separate input-artifact step. Use one planned
`xc-probability predict --model-id <id> --run-key <uuid>` command (repeat run-key
for explicit batches; retain optional database-url/project-root). Internally
read/validate retained daily GFS features, apply the saved transformer/model,
and publish predictions together with exact inputs and lineage in one bundle.
No inputs-id argument or separately published inputs artifact is required.
Keep reader/transformer/inference as separately testable internal functions.
No download, retraining or flight-label access is added to prediction.

Existing dataset verification belongs to the reusable dataset module, not
exclusively the training preparer: T-021 correction also calls it. Preserve
the documented weather-join audit flag for compatibility, but omit it from
the normal training workflow; prepare calls the function automatically.
The owner questioned CLI conventions; this is a workflow simplification,
not a request to delete existing tested dataset validation.

Existing `weather-join --verify-dataset-id` already validates corrected v4.
Measured read-only verification passed again in 19.119 s (960 rows, zero
exclusions, 20 patches); JSON read/parse alone took 0.282 s in a separate run.
These timings are local observations, not an SLA. No classifier was fitted.

Refine the pending implementation plan to avoid redundant manual audits:
`prepare` reuses the existing verifier once, then creates frozen model inputs,
weights and temporal folds. Later commands automatically verify their consumed
compact artifacts and validate outputs/reload checks. Drop the newly proposed
generic standalone `xc-probability verify` command and its mandatory manual
invocations; keep the existing weather verifier for independent dataset audits.
Do not traverse the full weather acquisition history at every training step.

The current model policy still requires all 67 selected physical inputs;
structural-null fields are outside that list. Partial-input inference is a
possible later model/pipeline revision requiring validation, not just relaxing
request validation. q300 is computed from unique training site-day counts,
then stored with k/n and lineage in each fitted model; inference multiplies
the current p200 by stored q300 without reading training labels again.

Resource arithmetic: the 960x82 float64 matrix is 629,760 bytes; final two-model
coefficients/intercepts/scalers contain 3,632 bytes of numeric values before
JSON/metadata. An illustrative compact source projection serialized in memory
to 3,596,373 bytes. These are measured/computed sizes, not implemented artifact
sizes. Training-time/disk forecasts remain estimates until owner-run commands
exist; scikit-learn is still absent. No data/model files were written.

## Current state — 2026-10-31

Latest owner decision: retain chronological trial fits/regularization comparison
and final fitting on all 2022–2024. For 300+, use the pooled empirical
conditional frequency q=k/n, without smoothing: final development q=3/42.
This explicitly supersedes the earlier Jeffreys selection in DEC-070 and the
notes. Share q across sites/horizons, count unique training site-days, and use
training-fold counts for trials. Preserve insufficient-support handling and
baseline/low-confidence limitations; no model was trained or data changed.
The 67 available predictors were counted in corrected versioned dataset v4
(43 daily + 11 lower-layer + 13 upper-layer), with names separately checked
against SQLite. Raw hourly point samples are not included in that count.

T-023 design clarification: the final model is to fit **all development source
seasons 2022–2024**; temporary development comparisons do not permanently
withhold seasons from that fit. The revised recommended first candidate uses
all **67 available daily/layer metrics**, with regularization, rather than the
unproven 16-feature shortlist. Read-only actual-SQLite schema and corrected-v4
inspection confirmed 43 daily + 11 lower-layer + 13 upper-layer values; raw
hourly samples are not included in that count. The local clarification
discussion covered exact DB columns, development-versus-backtest/calibration roles, binary
labels versus probability output and alternative sparse 300+ methods. All
42 positive 200+ development site-days have inclusion weight one; the selected
empirical conditional rate is 3/42, multiplied by predicted p200.
2025 remains the independent evaluation; no classifier, calibrator,
dependency install, SQLite/data change or real T-022 replay ran in this follow-up.
Documented inventory matched actual SQLite/v4 columns; repository structure
and diff whitespace checks passed. No model-quality test was run.

T-023 has started with a read-only dataset/code/documentation preflight on
`feature/T-023-baseline-XC-model`; implementation and training have not begun.
The local preflight recorded verified counts, the proposed training/completion policy and cloudbase
feature comparison. The existing corrected-v4 artifact verifier passed again
(960 rows, zero exclusions, 20 patched rows). There are 320 unique site-days
on 235 dates, 160/42/3 positive site-days for 100+/200+/300+, and the 2022
source-season subset has no 300+ positives. Installed scikit-learn is absent.
Existing T-022 v2 outputs match only 54/960 training keys. Proposals in the
preflight are not accepted decisions; no real T-022 replay or model training
was run. Keep the 2025 source-season reserve for T-026. The owner's T-022
manual-execution restriction remains in force. `npm.cmd run repo:check` and
`git diff --check` passed; this review changed documentation/status only.

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

Additional owner-run current-forecast smoke: GFS 2026-10-27 06Z D+1 for
2026-10-28, run `91ae8760-fdc2-4bd6-8f3f-af3bedc00e46`, produced cloudbase
artifact `e5a7e9e636e26a9127ffd843319838333769a77a0f1b65b3f672ebb9ed174ea6`.
Read-only hash and contract checks passed for 77 hours/seven daily summaries.
All hours are indeterminate, with all seven daily summaries using the potential
fallback. Vitosha low cloud is approximately 100% all eleven hours; mixed LCL
is 1,392--1,416 m MSL, or -402 to -378 m relative to the 1,793.929 m site.
The model ground is 887.69 m, so terrain mismatch remains material. The owner
reports dark/overcast conditions and clouds entering Vitosha; this is qualitative
consistency only, not an observed cloud-base measurement or accuracy validation.
Sopot also has a negative site-relative daily maximum (-47.95 m). No negative
height was clamped and no real command was rerun by the agent.
Seven 10:00 input rows lack sensible/latent heat flux, producing
`buoyancy_input_missing`; this does not prevent the mixed-LCL calculation.
No source-readiness/profile input issues were recorded. The cause of those
optional first-hour flux gaps was not investigated in this result review.

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
