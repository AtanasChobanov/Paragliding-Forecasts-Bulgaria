# Project Handoff

## Read first

1. `AGENTS.md` for repository rules.
2. This handoff for the active state.
3. T-020 in `docs/tasks.md` for ticket scope and acceptance criteria.
4. [`T-020-xccontest-activity-ingestion-plan.md`](T-020-xccontest-activity-ingestion-plan.md) for the completed flight-ingestion prerequisite.
5. [`T-020-persistent-site-exclusions-plan.md`](T-020-persistent-site-exclusions-plan.md) for durable reviewed source-site exclusions.
6. [`T-020-repaired-flight-label-threshold-analysis-2026-09-30.md`](T-020-repaired-flight-label-threshold-analysis-2026-09-30.md) for the current repaired-data inventory and development comparison of one, two, and three flights for negative examples.
7. [`T-020-flight-label-analysis-2026-09-29.md`](T-020-flight-label-analysis-2026-09-29.md) for the pre-repair historical snapshot and proposed evaluation splits; its exact cohort counts are superseded.
8. [`T-020-offline-flight-label-audit.md`](T-020-offline-flight-label-audit.md) for the implemented phase 2 command, evidence checks, artifacts, and owner-data results.
9. DEC-055 through DEC-063 in `docs/decisions.md`; DEC-023 through DEC-030 define the pre-existing XCContest boundary.
10. Only the relevant sections of `docs/project-brief.md` and `docs/architecture.md`.

Keep durable decisions in `docs/decisions.md`, ticket lifecycle in `docs/tasks.md`, and current operational state here.

## Current state — 2026-10-01

| Field | Current state |
| --- | --- |
| Branch | `feature/T-020-joined-weather-dataset` |
| Ticket | T-020 is **In Progress**. Flight ingestion/repair, persistent exclusions, and **phase 2 offline label auditing are implemented and verified**. Phase 3 cohort/acquisition planning and phase 4 weather join remain. No model or prediction command exists yet. |
| Completed owner operations | The 2024/2023/2022 repair is `9c70c7a0-89f2-4a56-8b8e-a608eb3dde6e`, replacing 85 views and copying 1402 from original `724845c1-7b75-4900-a74c-d61e9de83157`; it persisted 3753 accepted flights and its raw audit reports zero issues among 1487 artifacts. The owner also repaired 2025 as `89841b61-c681-4008-b833-031d4aee636e`, copying 219 views and recollecting the 31 faulty views from `d577156f-7f73-4e62-81ad-eb6881715739`; its 250-artifact audit reports zero issues and offline persistence recorded 1336 accepted flights (284 inserted, 1052 revalidated unchanged). Use these repaired runs, not their source runs. |
| Flight-evidence readiness | Parser v3's dated-view guard passed both repaired runs (2022–2024: 1487 artifacts / 9169 normalized observations; 2025: 250 / 3165). The production label command independently rechecks that guard against the raw artifacts and verifies effective persisted parser-v2/validation evidence without rewriting it. |
| Phase 2 audit | `uv run --project services/ml flight-label-audit` produces audit `cd6c8b99b6898ec41cb631a2ee9913cd6b76df377b1046d777a8fadc91c92a38`. Full-calendar output: 10,227 site-days, 5,090 positive-distance flights, 985 active site-days / 525 dates; 978 all-three-known vectors and 9,249 any-unknown vectors. Threshold-specific positive/negative counts: 100+ = 293/686, 200+ = 65/913, 300+ = 8/970. Results and manifests are ignored local JSONL/JSON artifacts, not a weather-backed training dataset. |
| Repaired-data analysis | The 2026-09-30 read-only review finds 5171 canonical flights, including 5090 in seasons 2022–2025. Across all four source seasons, minimum 1/2/3 flights gives 686/445/301 known 100+ negative site-days against 293 positives; ≥3 is a numerically viable pooled 100+ experiment. For proposed development seasons 2022–2024, the negatives are 524/338/226 against 213 positives, with especially sparse Dobrich, Nevsha, and Pastrina support at ≥3. Retain DEC-056's one-flight default pending chronological sensitivity validation, not because negatives must outnumber positives. Exact report linked above. |
| Local database | `data/local/paragliding.db` already contains `source_site_exclusions`; migration `20260926102539_add_source_site_exclusions` is present in the local migration history. Do not assume a different owner database has been migrated: check it before applying or resuming persistent-exclusion work there. |
| Live-source boundary | XCContest remains rendered-UI collection with conservative pacing. `xccontest-ingest fresh` and `xccontest-repair collect/resume` are explicit live operations. `xccontest-ingest resume` is offline and must not open a browser or create source transport. |
| Weather boundary | T-018 GFS pipeline is implemented and historical 2025/2023 acceptance evidence exists. Phase 2 fixes auditable label eligibility; it does not accept a split or acquisition cohort. Do not start broad GFS acquisition until phase 3's bounded cohort/storage plan is approved. |

## Accepted T-020 business logic

### Forecast issue policy (DEC-055)

- The primary daily issue covers D+1, D+2, and D+3.
- The reproducible cutoff is `20:00 Europe/Sofia` on the issue date.
- Each historical row must use the newest **complete** GFS cycle available by that cutoff and the exact corresponding forecast horizon.
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
- Proposed, not accepted: use 2022–2024 for chronological development/tuning/calibration and reserve repaired 2025 for final historical testing. Reserve whole joined site/date/horizon examples, keeping all sites and horizons of a target date together. Do not fit or calibrate on the final-test outcomes. The pre-repair strict full-label counts were development 736 days with `212/42/3` positives and provisional 2025 183 with `56/17/5`; recompute before adopting this split.
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
