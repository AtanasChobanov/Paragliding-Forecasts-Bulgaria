# Project Handoff

## Read first

1. `AGENTS.md` for repository rules.
2. This handoff for the active state.
3. T-020 in `docs/tasks.md` for ticket scope and acceptance criteria.
4. [`T-020-xccontest-activity-ingestion-plan.md`](T-020-xccontest-activity-ingestion-plan.md) for the completed flight-ingestion prerequisite.
5. [`T-020-persistent-site-exclusions-plan.md`](T-020-persistent-site-exclusions-plan.md) for durable reviewed source-site exclusions.
6. DEC-055 through DEC-061 in `docs/decisions.md`; DEC-023 through DEC-030 define the pre-existing XCContest boundary.
7. Only the relevant sections of `docs/project-brief.md` and `docs/architecture.md`.

Keep durable decisions in `docs/decisions.md`, ticket lifecycle in `docs/tasks.md`, and current operational state here.

## Current state — 2026-09-27

| Field | Current state |
| --- | --- |
| Branch | `feature/T-020-joined-weather-dataset` |
| Ticket | T-020 is **In Progress**. Its 0–2000 km flight-ingestion prerequisite and persistent reviewed-exclusion support are implemented in the working tree. No joined historical flight/weather dataset, model, or prediction command exists yet. |
| Active owner operation | XCContest raw collection is currently running for source seasons 2024, 2023, and 2022 under run key `724845c1-7b75-4900-a74c-d61e9de83157`. Do not modify collector/business code, stop the run, launch another live collection, or run destructive database commands while it is active. |
| Previous accepted run | 2025 run `d577156f-7f73-4e62-81ad-eb6881715739` completed collection and persistence. It is the first season with all-distance activity coverage under the new collector policy. |
| Local database | `data/local/paragliding.db` already contains `source_site_exclusions`; migration `20260926102539_add_source_site_exclusions` is present in the local migration history. Do not assume a different owner database has been migrated: check it before applying or resuming persistent-exclusion work there. |
| Live-source boundary | XCContest remains rendered-UI collection with conservative pacing. `fresh` is the only live operation. `resume` is offline and must not open a browser or create source transport. |
| Weather boundary | T-018 GFS pipeline is implemented and historical 2025/2023 acceptance evidence exists. Do not start broad GFS historical acquisition until the flight-label audit has fixed the eligible site-day cohort and a bounded storage plan is approved. |

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

### Overdevelopment and cloudbase context

- T-024 uses the accepted configurable hybrid decision-tree plus smooth-score baseline (DEC-057), including critical high-risk overrides, reasons, configurable thresholds, and explicit missing-input behavior. It is not part of the T-020 training dataset implementation.
- Cloudbase is deferred. T-022 evaluates deterministic cloudbase/thermal-top/inversion diagnostics from existing GFS forecast-model profiles and must retain a `blue` day state. IGRA is real observed balloon evidence for Sofia and remains validation evidence, not a required training join (DEC-054/058).

## T-020 flight-ingestion prerequisite

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

### Safe action after the live run

1. Let run `724845c1-7b75-4900-a74c-d61e9de83157` finish or reach its documented pause. Inspect its terminal JSON, raw manifest, checkpoint, and collection report; do not infer completion from a partial artifact count.
2. Run the usual offline `xccontest-ingest resume --run-key <run-key> --policy-file ...`. It reuses collected raw artifacts and advances parser, mapping, validation, and persistence only where each stage is valid.
3. If it returns `awaiting_mapping_review`, inspect the generated immutable proposals, create the complete sibling decisions JSONL, then rerun the same offline `resume`. Rejections of eligible stable keys become durable exclusions through that normal workflow.
4. Review the persistence/reconciliation result before treating a season as usable. A mapping or reconciliation pause means the affected evidence is not yet label-ready.
5. Do not launch GFS collection solely because a raw XCContest run ends. First produce the offline flight-label audit below.

## T-020 joined-dataset plan

T-020 is a reproducible dataset-building task, not a model-training task. Its output must be a versioned, auditable local dataset and manifest, never a manually curated spreadsheet or a database table with unstated provenance.

### Phase 1 — complete flight evidence

1. Complete the currently running 2024/2023/2022 collection through offline mapping, validation, and persistence.
2. Start with 2024 and 2023 for the first audit; include 2022 only if the audit shows that 300+ site-days remain too sparse.
3. Preserve 2025 as the known all-distance reference season. Earlier legacy collection without complete short-flight coverage may contribute positive threshold evidence, but cannot manufacture reliable negatives until re-collected under the activity policy.

### Phase 2 — offline label audit (no GFS download)

For every site-day in the candidate seasons, emit a deterministic `site_day_label_audit.jsonl` record with:

- canonical site/date/season identity;
- accepted positive-distance flight count, maximum distance, and threshold-positive evidence;
- threshold/mapping/activity coverage state and reasons;
- each tri-state label (`positive`, `negative`, `unknown`) plus its reason;
- source run/manifests, mapping snapshot, query/collector revisions, and hashes needed to reproduce the conclusion.

Exclude `unknown` rows from supervised training. Keep them in a separate audited output because later coverage repair may make them usable.

Planning checkpoints after the audit: target roughly 100 positive and 100 negative known site-days for 100+, roughly 50 positives for 200+, and at least 30 independent 300+ positive site-days across seasons/sites before interpreting a 300+ result as more than exploratory. These are planning thresholds, not proof of model quality. Season 2025 alone had approximately 80/23/5 positive site-days for 100+/200+/300+, so multi-season evidence is needed, especially for 300+.

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

- Commit `1234419` (`T-020 skip complete threshold date sorts`) added the non-paginated threshold sort avoidance. Focused collector tests (15), Ruff check, and format check passed.
- The uncommitted persistent-exclusion implementation has focused XCContest tests, database migration tests, and documentation updates pending final verification/commit. Do not claim a run has used that implementation until its actual local artifacts and terminal result are reviewed.
- A Vite build retains its existing >500 kB chunk warning; it is not a T-020 failure.

## Commands and safety

Use `uv run --project services/ml ...` for ML commands. Only `fresh` performs owner-authorized live collection. `resume` must remain offline. Do not store raw downloads, databases, model artifacts, or generated datasets in Git. Do not change business logic while the owner’s multi-season run is active.