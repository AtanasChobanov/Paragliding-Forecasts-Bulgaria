# Project Handoff

## Active blocker: per-job GFS source availability — 2026-10-06

The owner successfully resumed 2021-10-02 D+1 offline, then ran the same
75-job batch with `--max-jobs 71`. Job 5, 2021-10-02 D+2 run
`84d75951-1bd2-47ae-89fc-28bb50d9a64d`, completed all 583 GRIB ranges and
offline stages but failed its atomic SQLite transaction with the error
`Weather product natural key collides with different immutable timing.` Read-only inspection
shows four succeeded jobs, this fifth job with a complete raw manifest and no
database row, and 70 jobs not yet fetched. SQLite `quick_check` is `ok`; no
batch writer lock exists. The agent ran no weather product command and made
no code change for this new failure.

The existing product row for `gfs.20210930/06/atmos` has the correct
2021-09-30T06:00:00Z reference but `available_at_utc` is
`2021-09-30T09:44:37Z` from the 2021-10-01 D+1 selected lead set. The failed
job uses the same native product cycle and reference but its different
selected lead set was ready at `2021-09-30T09:51:16Z`. The GFS planner
defines this timestamp as the maximum GRIB/index Last-Modified over each
job's selected ranges. Persistence incorrectly treats it as an immutable
attribute of the shared product cycle, and `weather-join` also reads it
from that shared row for an exact per-job as-of check. All 17 product keys
shared by more than one job in this frozen batch have differing selected-range
availability. The collision will recur; a simple retry cannot fix it.

Recommended architectural correction, not yet accepted or implemented:
retain `weather_product_runs` for native source/cycle identity and move the
selected-range ready timestamp into immutable `weather_ingestion_runs`
evidence. Add a Drizzle migration, backfill existing run values from verified
manifest evidence (the 23 currently persisted runs have no mismatch with
their product rows), adjust persistence/replay and the horizon-matched join,
and test two target/horizon jobs sharing one product with different
availability. Do not overwrite the existing product row's timestamp to make
the fifth job pass; that would make the first job's provenance incorrect.
After a reviewed correction, the fifth run can resume offline without GFS
refetch, then the same batch can continue its 70 unstarted jobs. T-020
remains In Progress. The previous section records the completed shortwave
repair and the earlier operator state.

## Active 06Z batch repair — 2026-10-06

The owner-created acquisition `ea7b5dcbbb3e1f9dac97d377946310153fabd4fa7e69cbf077903d881d862492`
has batch `6c381854cc2136382413b7f9a89b286c0531c1aa0de11b4026361cf0d9fe834e`
with 75 jobs. Read-only SQLite/artifact inspection found the first three
2021-10-01 jobs succeeded, 2021-10-02 D+1 run
`09ca9a80-37c4-4777-9bb4-b086b3aaa9a9` has a complete 583-range raw
manifest and no database row after persistence rollback, and the other 71
jobs have not fetched raw payloads. No batch writer lock exists.

The owner approved an empirical -0.20 W/m² near-zero tolerance for
**reconstructed** GFS downward shortwave radiation. `gfs-normalizer/9`
now rejects negative native DSWRF, clamps reconstructed values within that
bound, records an immutable per-interval correction report and method, and
fails larger negatives before SQLite. Existing compact `/8` artifacts remain
readable. The 2021-10-02 raw GRIB f034/f035 messages were hash-verified and
decoded directly: a grid cell had 290.18 and 232.12 W/m² averages over
30–34 h and 30–35 h, giving -0.12 W/m² for the adjacent hour. The two
messages' 0.02 W/m² packing increments imply a 0.09 W/m² simple packing
error bound, so the exact source of the additional discrepancy is unproven.
Across 22 local parsed runs, native DSWRF was nonnegative and -0.12 W/m²
was the lowest reconstructed value. DEC-067 records the accepted policy.

The agent has run no weather product command. Code validation: full ML suite
413 passed; Ruff lint, Ruff format, `npm.cmd run repo:check`, and `git diff
--check` passed for the shortwave repair. The owner subsequently ran
`weather-ingest resume` for 2021-10-02 D+1 successfully; the new collision
and current operator action are recorded above.

## Implementation in progress — 2026-10-05

The owner selected fixed 06Z for all three historical horizons and a 16:00
Europe/Sofia source-ready cutoff, leaving the separate 20:00 delivery
deadline. DEC-066 and the `/2` cohort policy now record that rule. The 12Z
five-date/15-job sample described below remains verified technical evidence,
but its run identities cannot enter the new 06Z joined dataset.

Code for `weather-backfill resolve`/`resolution-status` and bounded
`batch-create`/`batch-run`/`batch-status`/resume/recover, reversible
`weather-artifacts archive`/`archive-batch`/`evict-local`/`evict-batch`/`restore`
and `weather-join` has been added. The new workflow is documented in
`services/ml/README.md`. The owner ran `weather-cohort` on 6 October 2026;
the fixed-06Z plan is
`e75ee4091e9eaaec446a457e8ef09cbb5f02235ff37c38062a3129df64191c14`.
Its reported counts match the selected 320 development site-days/235 dates,
242 reserved backtest site-days/131 dates, and 1,098 three-horizon jobs.
The agent has run no product command; the owner has since generated the
metadata acquisition and first batch described above. Archives and the
joined dataset have not yet been generated. Only unit tests, lint and repo
checks may be run by the agent. Do not present T-020 as Done
until the owner completes the 06Z development acquisition and join.

The first acquisition split is 2022–2024 development: 320 site-days, 235
target dates and 705 date/horizon jobs under the unchanged label selection.
The 2025 backtest split (242 site-days, 131 dates, 393 jobs) remains reserved
and can be fetched later before T-026. Fifteen measured 06Z inventories
averaged 1.081 GiB/job; this implies about 762 GiB raw for development and
425 GiB additional for 2025, excluding staging/retention overhead. At the
15-job technical sample's 14.41-minute/job average, serial development is
about 169 hours; full 1,098-job scope about 264 hours. These extrapolations
must be replaced with the owner's finalized metadata byte sum and actual
batch measurements. Cold archive preserves full raw on another volume; local
eviction removes only hash-verified GRIB payloads. Irreversible raw pruning
is not accepted or implemented.

Validation in this coding session: the final full ML suite passed **412
tests**; Ruff lint and format checks, `npm.cmd run repo:check`, and `git diff
--check` passed. Focused resolver/join/retention tests passed **4 tests**
after the CLI error-handling edit. No real product command, source request,
archive action, or joined-dataset build was executed by the agent; the new
cohort plan above was generated by the owner.

## Read first

1. `AGENTS.md` for repository rules.
2. This handoff for the active state.
3. T-020 in `docs/tasks.md` for ticket scope and acceptance criteria.
4. [`T-020-xccontest-activity-ingestion-plan.md`](T-020-xccontest-activity-ingestion-plan.md) for the completed flight-ingestion prerequisite.
5. [`T-020-persistent-site-exclusions-plan.md`](T-020-persistent-site-exclusions-plan.md) for durable reviewed source-site exclusions.
6. [`T-020-repaired-flight-label-threshold-analysis-2026-09-30.md`](T-020-repaired-flight-label-threshold-analysis-2026-09-30.md) for the current repaired-data inventory and development comparison of one, two, and three flights for negative examples.
7. [`T-020-flight-label-analysis-2026-09-29.md`](T-020-flight-label-analysis-2026-09-29.md) for the pre-repair historical snapshot and proposed evaluation splits; its exact cohort counts are superseded.
8. [`T-020-offline-flight-label-audit.md`](T-020-offline-flight-label-audit.md) for the implemented phase 2 command, evidence checks, artifacts, and owner-data results.
9. [`T-020-phase-3-gfs-cohort-acquisition-plan.md`](T-020-phase-3-gfs-cohort-acquisition-plan.md) for the 2022–2024 training / 2025 backtest proposal, three-horizon GFS acquisition, live resume design, storage gate, and existing-run inventory.
10. [`T-020-gfs-metadata-timing-probe-2026-10-04.md`](T-020-gfs-metadata-timing-probe-2026-10-04.md) for the one-off 12Z/06Z timing evidence and the strict 20:00 delivery gate.
11. DEC-055 through DEC-065 in `docs/decisions.md`; DEC-023 through DEC-030 define the pre-existing XCContest boundary.
12. Only the relevant sections of `docs/project-brief.md` and `docs/architecture.md`.

Keep durable decisions in `docs/decisions.md`, ticket lifecycle in `docs/tasks.md`, and current operational state here.

## Previous operational snapshot — 2026-10-04

| Field | Current state |
| --- | --- |
| Branch | `feature/T-020-joined-weather-dataset` |
| Ticket | T-020 is **In Progress**. Flight ingestion/repair, persistent exclusions, phase 2 label audit, the phase 3 offline cohort planner, and bounded technical-sample `weather-backfill` commands are implemented. The pinned cohort is DEC-064. The one-off 114-inventory timing survey is complete. All 15 jobs across the five-date 12Z technical sample are now persisted locally. Full 1,098-job metadata resolution, broad batching, storage lifecycle, and the operational as-of rule remain. Phase 4 weather join remains. No model, prediction, or alert command exists yet. |
| Completed owner operations | The 2024/2023/2022 repair is `9c70c7a0-89f2-4a56-8b8e-a608eb3dde6e`, replacing 85 views and copying 1402 from original `724845c1-7b75-4900-a74c-d61e9de83157`; it persisted 3753 accepted flights and its raw audit reports zero issues among 1487 artifacts. The owner also repaired 2025 as `89841b61-c681-4008-b833-031d4aee636e`, copying 219 views and recollecting the 31 faulty views from `d577156f-7f73-4e62-81ad-eb6881715739`; its 250-artifact audit reports zero issues and offline persistence recorded 1336 accepted flights (284 inserted, 1052 revalidated unchanged). Use these repaired runs, not their source runs. |
| Flight-evidence readiness | Parser v3's dated-view guard passed both repaired runs (2022–2024: 1487 artifacts / 9169 normalized observations; 2025: 250 / 3165). The production label command independently rechecks that guard against the raw artifacts and verifies effective persisted parser-v2/validation evidence without rewriting it. |
| Phase 2 audit | The verified **v1** snapshot is `cd6c8b99b6898ec41cb631a2ee9913cd6b76df377b1046d777a8fadc91c92a38`: 10,227 site-days, 5,090 positive-distance flights, 985 active site-days / 525 dates; 978 all-three-known vectors and 9,249 any-unknown vectors. Threshold-specific positive/negative counts: 100+ = 293/686, 200+ = 65/913, 300+ = 8/970. **v2** reads sites from SQLite and snapshots/seasons/maturity from JSON. A real v2 artifact directory `f30cf3707dc91a310a26938a6c3eb7ca9acacd933d7cfe5f4db6505e5f1ed714` is now present locally; its four output hashes and database-file SHA-256 match its manifest in a read-only check. This session did not rerun the full label-audit command. Preserve both v1 directories and this v2 directory. |
| Repaired-data analysis | The 2026-09-30 read-only review finds 5171 canonical flights, including 5090 in seasons 2022–2025. Across all four source seasons, minimum 1/2/3 flights gives 686/445/301 known 100+ negative site-days against 293 positives; ≥3 is a numerically viable pooled 100+ experiment. For proposed development seasons 2022–2024, the negatives are 524/338/226 against 213 positives, with especially sparse Dobrich, Nevsha, and Pastrina support at ≥3. Retain DEC-056's one-flight default pending chronological sensitivity validation, not because negatives must outnumber positives. Exact report linked above. |
| Local database | `data/local/paragliding.db` already contains `source_site_exclusions`; migration `20260926102539_add_source_site_exclusions` is present in the local migration history. Do not assume a different owner database has been migrated: check it before applying or resuming persistent-exclusion work there. |
| Live-source boundary | XCContest remains rendered-UI collection with conservative pacing. `xccontest-ingest fresh` and `xccontest-repair collect/resume` are explicit live operations. `xccontest-ingest resume` is offline and must not open a browser or create source transport. |
| Weather boundary | T-018 GFS pipeline is implemented and historical 2025/2023 acceptance evidence exists. `weather-cohort` pins 2022–2024 development and 2025 untouched backtesting as plan `2ed9a4d3c46480dc730958894beca1dcb954b07c737b910f64ea7dac4f9c8cad`: 320 development site-days/235 dates, 242 backtest site-days/131 dates, 1,098 unique three-horizon jobs; 2026 is excluded. The one-off survey verified 15 historical jobs' 12Z/06Z selector/byte metadata and fourteen recent issue dates' 12Z/06Z source presence, **not the full cohort**. Latest recent 12Z metadata proxy: 19:18:58 Sofia; 06Z: 13:09:21. DEC-065 requires prediction and alert delivery by 20:00, so the pinned 20:00 *source* cutoff is not yet a safe training-acquisition rule. All 15 jobs in the five-date 12Z technical sample are persisted. A live-issue rehearsal still needs prediction/alert code. Raw selected GFS messages retain global grids; derived matrices are compact. About 390 GiB was free on D: at the 2 October inspection, less than the estimated full backfill. Broad storage-bounded batches and controlled hybrid retention remain unimplemented. Direct untracked deletion remains unsupported. |
| 2026 exclusion | The source season ended 30 September, but XCContest flights may still be entered or checked. Current SQLite has only 81 canonical flights on 29 2026-season dates, all created by the 7 August legacy threshold run `f1032827-a98d-4c01-969e-e67b4885f90d`. Its manifest has `minimum_scored_distance_km: 100` and no all-distance daily activity coverage; DEC-056 negatives are unavailable. The current label-audit policy declares only mature repaired 2022–2025 runs. **Do not generate 2026 flight labels, GFS acquisition jobs, or dataset rows in this plan.** |

The T-020 technical-sample operator sequence is documented under **Bounded GFS
technical sample** in `services/ml/README.md`. It needs no new dates JSON:
`weather-backfill probe` selects one or more of the five pinned dates from the
cohort plan and one explicit 12Z/06Z cycle, then `run`/`resume-live` completes
jobs through SQLite with per-range checkpoints; `status` and `recover-lock`
are offline. The default local GFS usage-policy file and migrated SQLite must
be present. All five pinned dates' three horizons are now persisted; preserve
the sample's raw evidence while reviewing capacity and the broader protocol.
The historical three-horizon sample uses three different issue dates and does
not by itself prove the live 20:00 dispatch deadline. No GFS payload or new
weather SQLite rows were produced in this implementation session.
An owner-run 2022-05-01 12Z sample now has all three jobs `persisted` under
`8cb0eb77a969b656f0d967e9de5aad5bc60d0ca6a83ae2c842f489f99d2d9bd1`.
The 2026-10-04 metadata-only probe for the other four pinned dates produced
sample `e55717e0bee76952f34f3058e65e534f89fc38451c4f42f9263a106d48af5ff0`:
12 jobs, 13,906,952,025 selected bytes (12.95 GiB); the probe downloaded no
GRIB ranges. Read-only follow-up on 5 October 2026 found all 12 jobs
`persisted` and no writer lock. SQLite independently reports all 12 run UUIDs
as `succeeded`: each has 77/77 accepted hourly site samples, zero
rejected/quarantined samples, seven daily snapshots (one per configured site),
and 11 valid hours. Every daily snapshot has exactly 11 input samples from its
own ingestion/product run; no cross-run inputs were found. The three 12Z
reference dates per target date identify D+1/D+2/D+3, with lead ranges
f019–f029, f043–f053, and f067–f077 respectively. The preceding 2022-05-01
sample's three jobs also have seven snapshots and 77/77 accepted samples each,
so the bounded five-date/15-job technical sample is now persisted. SQLite
`quick_check` is `ok` and `foreign_key_check` found zero violations. An
effective artifact audit of the 2025-08-02 D+3 run verified seven boundaries;
the other 14 artifact chains were not re-audited in this follow-up. Saved
feature-quality reports for the new 12 jobs each show 1,001 `real`, 854
`derived`, and 98 `unsupported` feature states; provider cloud base is one
explicitly unsupported field. The sample proves bounded historical ingestion,
not the 20:00 delivery rule, full-cohort source availability, broad storage
lifecycle, or the phase-4 horizon-matched join. `weather_daily_feature_snapshots`
is unique by ingestion run/site footprint/feature version; issue/horizon
identity comes from the run's target date and product reference time and the
linked hourly valid times. The later join must constrain all of these keys
and the selected cycle, since another cycle can exist for the same target
date and horizon.
Synthetic validation on 4 October: full ML suite **408 passed**, including
an interrupted second-range download followed by resume without repeating a
verified first range; fake source-revision rejection; and an immutable
three-horizon sample-manifest test. Ruff, `npm.cmd run repo:check`, and
`git diff --check` pass after final formatting. These checks do not prove
real source availability, disk throughput, SQLite persistence, or alert timing.

## Accepted T-020 business logic

### Forecast issue policy (DEC-055, delivery amendment DEC-065)

- The primary daily issue covers D+1, D+2, and D+3.
- DEC-055's provisional source cutoff is `20:00 Europe/Sofia` on the issue date; DEC-065 requires the **prediction and alert to be dispatched by that time**.
- The final historical as-of policy must match a measured operational latest-safe source deadline, cycle/fallback rule, and the exact forecast horizon. The current 20:00 cohort candidate cycles must not be used for broad acquisition until then.
- No later GFS run, same-day evidence, observation, or reanalysis may replace missing pre-cutoff data.
- A future morning refresh is a distinct issue-time cohort; it must not be mixed into the MVP evening cohort.

### Flight labels (DEC-056)

For every canonical site and local flying date, build three nested labels:

- `100+`, `200+`, and `300+` are inclusive confirmed-flight thresholds.
- A threshold is positive when at least one accepted mapped flight reaches it.
- A threshold is negative only when accepted **positive-distance** flight activity exists and threshold/mapping coverage is complete and mature, yet no accepted flight reaches that threshold.
- A day with no accepted activity, partial/saturated coverage, unresolved mapping, or incomplete evidence is `unknown`; it is never silently treated as negative.
- One accepted positive-distance short flight is the MVP activity minimum. Preserve flight count, maximum distance, coverage, and reason fields so a later stricter activity threshold can be audited without recollection.
- Labels must obey `label_300 <= label_200 <= label_100`; later T-023 outputs must preserve the equivalent probability order.

DEC-063 accepts the two repaired 2022–2025 runs as mature historical snapshots,
as explicitly approved by the owner on 1 October 2026. This does not define a
waiting period for another run or future season and does not waive coverage or
mapping checks. Phase 2 uses conservative complete parent daily coverage for
negatives; confirmed positives retain their independent evidence even when
higher-threshold absence is unknown.

Those snapshot declarations now live in
`services/ml/src/paragliding_forecasts_ml/datasets/resources/flight-label-audit-policy.json`.
The ordinary command selects seasons from that default; use repeated `--season`
for a subset and `--policy-file` for another explicitly chosen snapshot set.
No generic late-upload age rule has been accepted. Adding seasons or run IDs
requires configuration data, not Python edits. `mature: false` preserves
positive evidence but keeps absence unknown. The site catalog is read from SQLite.

The any-unknown file deliberately partitions whole three-threshold vectors:
Shumen 2023-10-17, 107.88 km, is positive for 100+ and unknown for 200+/300+.
All seven active unknown vectors are outside the collected daily activity window.
Read-only inspection found no mistaken 100+ unknown on that confirmed flight.
The two v1 directories have identical label JSONL bytes; their summaries
differ because statistics were expanded during initial implementation. The later
v2 directory is separate and has matching local manifest/output/database hashes.

`docs/tasks.md` has been restored to its pre-implementation content. Root
`AGENTS.md` now permits only status-column changes there; keep implementation
notes/results in this handoff or focused documentation.

### Overdevelopment and cloudbase context

- T-024 uses the accepted configurable hybrid decision-tree plus smooth-score baseline (DEC-057), including critical high-risk overrides, reasons, configurable thresholds, and explicit missing-input behavior. It is not part of the T-020 training dataset implementation.
- Cloudbase is deferred. T-022 evaluates deterministic cloudbase/thermal-top/inversion diagnostics from existing GFS forecast-model profiles and must retain a `blue` day state. IGRA is real observed balloon evidence for Sofia and remains validation evidence, not a required training join (DEC-054/058).

## T-020 flight-ingestion prerequisite

### Pre-repair exploratory inventory — 2026-09-29

- **Current counts and policy comparison are in the 2026-09-30 repaired-data report linked above.** The following figures describe only the older snapshot and should not be used to freeze a cohort.
- All numbers in this subsection and in the linked report are a **pre-2025-repair snapshot**. They remain useful for deciding what the label audit must report, especially negative-policy sensitivity, but are not a current candidate inventory and must not be used to choose a weather or evaluation cohort. The local database now has 5171 canonical positive-distance flights after the repaired 2025 persistence; the production offline audit must recompute its counts from the repaired evidence.
- The snapshot contained 4887 unique positive-distance flights. Its 2022–2025 subset had 4806 flights / 972 active site-days / 521 distinct dates, observed maximum-distance bands `000/100/110/111` = `679/228/57/8`, and 100+/200+/300+ positives `293/65/8`. The 2026 legacy rows were threshold-only and remain outside the negative cohort.
- In that snapshot, among 679 below-100 site-days, 247 had one flight, 141 had two, and 72 had three. Applying a future activity threshold of 2/3/5 flights would have reduced known 100+ negatives from 651 to 422/286/145. The label audit must preserve the count and reason for every row so that such a policy can be reviewed and versioned; DEC-056's current MVP minimum remains one accepted positive-distance flight.
- Both effective all-distance runs had zero actionable mapping quarantines. The 2025 validation's 865 `review_required` rows are resolved by its matching run-local reviewed rejection file; 2022–2024 has 2222 persistent exclusions plus 374 coordinate-based rejections. Six invalid-duration parser rows were below 1.4 km and cannot conceal threshold positives.
- The snapshot showed evidence at all seven sites in every season but sparse Pastrina and Dobrich activity, and only eight 300+ positive site-days across seven calendar dates. The repair may change every current count; the production audit, rather than this exploration, is the basis for deciding whether pooled 100+/200+ experiments or any 300+ evaluation are supportable.
- At the time of this pre-repair snapshot, the 2022–2024 development / 2025 test split was only proposed. The owner selected that split on 3 October 2026; the current plan linked above uses the later v2 audit, not these pre-repair counts. Reserve whole joined site/date/horizon examples, keeping all sites and horizons of a target date together. Do not fit or calibrate on the 2025 backtest outcomes. The old strict full-label counts were development 736 days with `212/42/3` positives and provisional 2025 183 with `56/17/5`; the latter has been superseded by the repaired v2 audit.
- Weather SQLite has 28 snapshots across four runs, but only two historical target dates (2025-08-02 and 2023-10-03), and their newest-cycle/evening-cutoff compliance is not yet established. Broad GFS acquisition remains gated.
- The detailed report and local ignored scratch script/output locations are documented in [`T-020-flight-label-analysis-2026-09-29.md`](T-020-flight-label-analysis-2026-09-29.md). T-020 remains In Progress; no new accepted decision or later-ticket implementation was added.

### Implemented collection policy

- The public command still selects repeated `--season`; users do not need date-range flags.
- The collector preserves threshold-first discovery of 100+ flights, then performs all-distance activity collection for the source-offered Bulgarian XC season (15 February–15 October).
- It captures the source-default parent view first. A non-paginated parent view is complete as captured, including exactly 100 rows.
- Only a paginated parent falls back to exact glider-category views. Only a paginated exact category receives the explicit rescue sorts.
- The threshold collector first observes the unsorted date view; it skips a distance sort when that full view has no next page. This preserves 100+ discovery while avoiding needless slow sorts on empty/small dates.
- Finite observed distances from 0 through 2000 km can persist. Later label construction must use only positive distance as activity evidence.
- The collector’s source-default all-distance mode must remain `PG*` (not a leftover threshold category such as `CCC`). This was corrected before the current multi-season run.

### Persistent reviewed source-site exclusions (DEC-061)

- `source_site_exclusions` stores only reviewed exact XCContest `source_site_token` or `source_takeoff_id` identities that are confirmed outside the supported seven-site scope.
- A durable exclusion never maps a flight to a canonical site and never creates a negative flight label.
- In `fresh` and offline `resume`, the v4 mapping stage reads active exclusions with the mapping catalog. Exact stable-key evidence is automatically rejected only when fresh coordinate/mapping evidence does not conflict.
- Name-only rejections, geometry ambiguity, country conflicts, and coordinate-only outside-catchment cases are not reusable durable exclusions. A new in-scope/ambiguous coordinate or conflicting active mapping produces explicit review instead of silently applying an old exclusion.
- A normal offline `xccontest-ingest resume` applies the sibling reviewed mapping file transactionally before revalidation. The focused manual command and explicit retirement command are documented in `services/ml/README.md`.

### Verified repair gate before T-020 flight-label audit

1. Repaired 2022–2024 run `9c70c7a0-89f2-4a56-8b8e-a608eb3dde6e` and repaired 2025 run `89841b61-c681-4008-b833-031d4aee636e` both pass `xccontest-repair audit` with zero issues. The original 2025 run remains historical provenance only because its 31 stale dated views are superseded by the repair run.
2. Parser v3 additionally makes a stale or foreign dated raw artifact a hard offline failure: the selected date in the saved document and every rendered result-row date must equal the manifest `date_filter`. The 2022–2025 repaired evidence passes that new guard.
3. The deterministic production offline label audit is now implemented and verified. It uses persisted accepted evidence, repaired mature complete coverage for negatives, explicit unknowns, and hashes/reasons/activity counts. The earlier Shumen 2023-10-17 accepted flight retains its verified 100+ positive only; it does not provide negative coverage.
4. Do not launch broad GFS collection solely because raw XCContest repair is complete. First produce and review the offline flight-label audit.

## T-020 joined-dataset plan

T-020 is a reproducible dataset-building task, not a model-training task. Its output must be a versioned, auditable local dataset and manifest, never a manually curated spreadsheet or a database table with unstated provenance.

### Phase 1 — complete flight evidence

1. The 2022–2025 collection, repair, mapping, validation, and persistence are complete in the repaired runs; parser v3 has replayed both repaired raw sets successfully.
2. The production audit confirms no 300+ positives in 2022 and only eight across all four seasons, on seven distinct dates. Scarcity remains unresolved. The label inventory is reproduced; no evaluation split or weather acquisition cohort has been accepted.
3. Earlier legacy collection without complete short-flight coverage may contribute positive threshold evidence, but cannot manufacture reliable negatives until re-collected under the activity policy. Keep the 2026 legacy subset separate.

### Phase 2 — offline label audit (implemented; no GFS download)

For every site-day in the candidate seasons, emit a deterministic `site_day_label_audit.jsonl` record with:

- canonical site/date/season identity;
- accepted positive-distance flight count, maximum distance, and threshold-positive evidence;
- threshold/mapping/activity coverage state and reasons;
- each tri-state label (`positive`, `negative`, `unknown`) plus its reason;
- source run/manifests, mapping snapshot, query/collector revisions, and hashes needed to reproduce the conclusion.

Exclude `unknown` rows from supervised training. Keep them in a separate audited output because later coverage repair may make them usable.

The supported command and verified results are in
[`T-020-offline-flight-label-audit.md`](T-020-offline-flight-label-audit.md) and
`services/ml/README.md`. Outputs enumerate every source-season calendar day for
each site; this expands the unknown denominator compared with the exploratory
collected-date script. The known output contains 978 complete vectors, with
292/65/8 positives; the full threshold audit retains 293/65/8 positives.

Planning checkpoints after the audit: target roughly 100 positive and 100 negative known site-days for 100+, roughly 50 positives for 200+, and at least 30 independent 300+ positive site-days across seasons/sites before interpreting a 300+ result as more than exploratory. These are planning thresholds, not proof of model quality. The production audit confirms 293/65/8 threshold-specific positives across 2022–2025; the 300+ checkpoint remains unmet.

### Phase 3 — freeze the weather cohort and acquisition plan

1. Select only known-label site-days for the MVP weather cohort. Retain every scarce 300+ positive day; sample abundant 100+ negatives/positives reproducibly, stratified by site, season/month, and threshold status rather than hand-picking weather.
2. Generate a dry-run acquisition manifest that maps every selected site-day and D+1/D+2/D+3 issue to its required GFS cycle, valid-time windows, and exact issue cutoff under DEC-055.
3. Verify a small bounded multi-season technical sample end-to-end before requesting broad downloads. The sample must include at least one positive and one negative, every supported forecast horizon, every site footprint, and scarce 300+ examples if present.
4. Estimate retained raw and derived storage from the actual compact-artifact implementation and approve a bounded batch. Historic GFS artifacts must be recoverable from the provider for each planned issue date before the main run starts.

### Phase 4 — build and validate the joined dataset

1. Run the approved GFS collection/persistence batch from the frozen manifest, preserving run identity, product validity, feature version, units, missingness, source/provider provenance, and cutoff evidence.
2. Join labels only to weather features with matching site/date/issue/horizon identity. Reject duplicate, later-than-cutoff, missing, or ambiguous weather evidence instead of choosing a convenient row.
3. Emit local versioned outputs such as `training_examples.jsonl`, `excluded_examples.jsonl`, and `manifest.json`. Each training row contains feature values plus units/missingness/provenance, the three labels, and pointers/hashes to its label and weather evidence.
4. Validate schema, row uniqueness, complete provenance, tri-state exclusion, nested labels, and deterministic replay. Split future model evaluation chronologically and by season to avoid training on evidence from the future.

### Explicit non-goals for T-020

- No classifier, calibrated probability, alert, T-023 cloudbase prediction, or T-024 overdevelopment ML model is built here.
- No rule may call a no-flight day a negative merely because XCContest has no visible row.
- No GFS data is collected at a later run merely to fill an earlier cutoff gap.

## Relevant weather and sounding state

### T-018 GFS

The weather pipeline has historic acceptance evidence:

```powershell
uv run --project services/ml weather-ingest fresh `
  --purpose historical_forecast `
  --local-date 2025-08-02 `
  --explicit-run-at 2025-08-01T00:00:00Z `
  --maximum-total-mib 1113 `
  --policy-file data/local/gfs-usage-policy.json `
  --allow-live-network
```

The 2023-10-03 retry succeeded after a bounded shortwave numerical-noise fix. Current raw/derived retention remains a storage risk; the compact site-footprint design must be used and broad backfill remains gated by Phase 3.

### T-019 IGRA

T-019 is in Review. It collects official NOAA/NCEI IGRA v2.2 observations for Sofia `BUM00015614`, preserves immutable raw/normalized/validated artifacts, and has no SQLite or training-join role. It may support later GFS validation (T-039), but it is not a predictor for T-020.

## Verification and commit context

- On 2026-10-04, `weather-cohort` was implemented and run offline against the
  hash-verified v2 label audit. The content-derived plan is
  `2ed9a4d3c46480dc730958894beca1dcb954b07c737b910f64ea7dac4f9c8cad`
  under ignored `data/processed/weather-cohorts/`. It selected 320 development
  site-days (160 known 100+ positives and 160 negatives) on 235 dates, kept all
  242 known 2025 backtest site-days on 131 dates, and emitted 1,098 unique
  date/horizon requests with DST-aware issue cutoffs, valid hours, candidate
  cycles, and per-site sampling fractions/weights. All 42 development 200+
  positives, all three development 300+ positives, and all five 2025 300+
  positives are present. Repeating the real command returned the same plan ID
  and byte-identical directory. The command made no network request, weather
  download, SQLite write, weather join, or model output. Dataset tests passed
  53/53, full ML tests 404/404, Ruff lint/format, and `repo:check`; run a final
  diff check after any documentation or code follow-up. Metadata-only source
  availability and byte probing is the next implementation step.

- On 2026-10-03, the phase 3 plan was refined around the owner's available
  storage and evening-forecast requirement. It now specifies immutable
  date/capacity batches in which every GFS date/horizon job completes raw,
  compacting, validation, feature construction, and verified SQLite persistence
  before the next job. It proposes a hybrid retention policy: keep full raw for
  the 15-job technical sample, new protocol evidence, and failures; preserve
  compact Bulgarian/site evidence plus provenance and receipts for most
  successful broad jobs; then prune only their global selected-message bytes.
  This lifecycle and its DEC-046 impact are not implemented or recorded as an
  accepted decision yet. The plan also confirms DEC-055's 20:00 Sofia cutoff:
  12Z is the expected newest cycle, 06Z is the completeness fallback, and the
  required 12Z leads are f019–f077 in summer or f020–f078 in winter. An official
  NOMADS listing showed f077/f078 around 15:52–15:53 UTC for a recent 12Z run,
  leaving roughly one summer hour before cutoff; the implementation must still
  resolve every historical job from its own availability metadata. No payload
  acquisition was run.

- The owner clarified the production prediction shape: one evening issue
  predicts three **different** target dates at D+1, D+2, and D+3. The phase 3
  plan now makes the final dataset grain explicit as one
  `(site_id, target_local_date, horizon, issue_local_date, selected_cycle)`
  example. A sampled site-day expands to up to three separately sourced rows
  with a shared flight outcome; the provisional 320 development site-days mean
  at most 960 training examples, and 242 reserved 2025 site-days mean at most
  726 backtest examples. Split/fold/uncertainty grouping remains by whole target
  date. No phase-4 join or model was implemented in this planning clarification.

- On 2026-10-03, a read-only SQLite/manifest check found the limited 2026
  threshold-only evidence described above. After reviewing that evidence, the
  owner chose 2022–2024 for development/training and 2025 as the untouched
  backtest, excluding 2026 from the present cohort and acquisition. The phase 3
  proposal was updated accordingly. No flight collection, GFS acquisition,
  model training, or split command ran in this review. The exact 131-date 2025
  table still matches the v2 audit; `npm.cmd run repo:check` and
  `git diff --check` passed.

- The same planning follow-up confirmed that daily weather values, profile
  layers, quality/missing states, source-native provenance, and manifest hashes
  persist in SQLite (the current database is about 19 MiB). The later join can
  therefore be database-first. The plan now specifies verified per-run cold
  archival to laptop/USB storage and safe local eviction, plus canonical restore
  for full audit/replay. Current commands do not implement this lifecycle yet;
  manually deleting raw paths would break offline resume, artifact audits, and
  duplicate-acquisition verification.

- The 2026-10-02 phase 3 planning session inspected the GFS collector, planner,
  weather pipeline, compact-grid implementation, the v2 label output, SQLite
  weather runs, and raw/interim disk use without changing source data. It
  verified the 131 known 2025 target dates/242 site-days, checked v2 output
  and SQLite file hashes against the manifest, and issued read-only HEAD probes
  for one 2022 and one 2023 historical AWS GRIB object (both HTTP 200). No
  GFS payload was downloaded and no phase 3 command or joined dataset exists.
  The plan's printed 131-date holdout table was checked against every 2025
  known date in the v2 audit. `npm.cmd run repo:check`, `git diff --check`,
  and a trailing-whitespace scan of the new plan passed. See the linked phase
  3 proposal for the sample, capacity estimates, and cleanup candidates.

- Follow-up v2 verification passes **49 dataset tests / 400 full ML tests**,
  Ruff lint/format, repository structure, and Git diff checks. Site catalogs
  and run/season policy inputs are now data-driven, including synthetic tests
  for an added site, future season, another snapshot UUID, and false maturity.
  Existing v1 artifacts were inspected read-only to explain the seven active
  any-unknown vectors and the differing summary versions. **No updated real
  audit was executed at that earlier verification point**; the v2 directory
  described in the current-state table appeared later. Both previous v1
  directories remain retained.

- The 2026-10-01 phase 2 implementation has 36 focused dataset tests. The full
  ML suite passes **387 tests**; Ruff lint/format over `services/ml`,
  `npm.cmd run repo:check`, and `git diff --check` pass. Two final supported-command
  replays produce the same audit identity and byte-identical output. SQLite
  bytes remain unchanged. No TypeScript/browser product code changed, so those
  product suites were not rerun. Generated outputs and local databases remain
  ignored. The owner-approved maturity policy is DEC-063. The next work is
  phase 3 planning, only when requested; broad GFS remains gated.

- Commit `1234419` (`T-020 skip complete threshold date sorts`) added the non-paginated threshold sort avoidance. Focused collector tests (15), Ruff check, and format check passed.
- Commit `a27f6df` recorded persistent site exclusions and the dataset plan; `3d26309` added resumable raw repair. The 2022–2024 persistence artifacts now demonstrate actual use of persistent exclusions and repaired raw evidence.
- The 2026-09-29 review ran read-only raw audits (2022–2024: zero issues; 2025: 31 issues), SQLite quick/foreign-key checks, effective stage-hash and accepted-row reconciliation, terminal mapping review, nested-label/count assertions, and database-byte preservation checks. Two final replays produced identical summary/site-day bytes; scratch Ruff lint/format, `repo:check`, and `git diff --check` passed. No product code changed; product suites were not rerun. The detailed report is an analysis, not a claim of completing the production T-020 audit or weather join.
- The owner completed 2025 repair run `89841b61-c681-4008-b833-031d4aee636e`: its 250-artifact raw audit reports zero issues, and its offline persistence recorded 1336 accepted flights. Parser v3's selected-date and rendered-row-date guard passed replay of both repaired runs (2022–2024: 1487 artifacts / 9169 normalized observations; 2025: 250 / 3165). Focused XCContest tests pass `117 passed`; the full ML suite passes `351 passed`, `npm.cmd run repo:check` passes, and `git diff --check` passes.
- A new read-only 2026-09-30 exploratory replay uses the two repaired runs, verifies DB/stage provenance and nested labels, and produces byte-identical local summary/site-day/threshold-comparison files on repeat. Its ignored scratch scripts pass Ruff check/format. Four-season 100+ known negatives are 686/445/301 for minimum 1/2/3 flights against 293 positives; development-only negatives are 524/338/226 against 213 positives. The ≥3 pooled class balance is viable by count, but local scarcity and asymmetric activity selection remain. This is analysis evidence, not the production T-020 label command or a model-quality result.
- A Vite build retains its existing >500 kB chunk warning; it is not a T-020 failure.

## Commands and safety

Use `uv run --project services/ml ...` for ML commands. `xccontest-ingest resume` must remain offline; collector recovery and `xccontest-repair collect/resume` are distinct explicitly authorized live operations. Do not store raw downloads, databases, model artifacts, or generated datasets in Git. Do not change business logic while an owner collection is active.
