# T-020 phase 3 — GFS cohort, evaluation reserve, and resumable acquisition plan

**Status:** implementation proposal, updated 3 October 2026. This document plans phase 3 and the later phase 4 acquisition; it does not authorize or execute a broad download, change DEC-055/056, or mark T-020 complete. Freeze the choices below in a versioned acquisition manifest after the phase 3 implementation and bounded verification. Generated manifests, weather data, and the local database stay ignored by Git.

## Source snapshot and scope

- Ticket: T-020 in `docs/tasks.md`; phase 3 in `docs/handoff.md`. The output is an auditable local dataset, not a model. T-021 feature-calculation testing and T-023/T-026 model/backtest work remain separate tickets.
- Accepted rules: DEC-055 (20:00 `Europe/Sofia` issue cutoff, D+1/2/3 and newest complete pre-cutoff GFS cycle), DEC-056 (tri-state nested flight labels), DEC-063 (mature repaired 2022–2025 XCContest evidence), DEC-046/047 (immutable weather evidence and explicit local training-use policy).
- Freeze input to the locally present phase-2 v2 audit `f30cf3707dc91a310a26938a6c3eb7ca9acacd933d7cfe5f4db6505e5f1ed714`. Its `known_site_day_labels.jsonl` SHA-256 is `0704d322eea69e81a986b6d0202691984d509efb6da48abcc6f68d712ba1a838`; all four output hashes match the manifest and the current SQLite file matches its recorded database SHA-256. A changed audit, label policy, site sampling policy, or database snapshot requires a new cohort/plan identity, never silent reuse. The older v1 audit remains historical evidence.
- The v2 known cohort is 978 complete label vectors on 518 distinct local dates. The full threshold audit has one extra confirmed 100+ positive with unknown 200+/300+ labels; do not put that vector in this complete-vector MVP cohort. No-activity and other unknown vectors remain outside supervised data.

## What the current GFS implementation actually does

`weather-ingest fresh --local-date ...` is **one target local date and one GFS cycle**. `sofia_window_instants()` generates 10:00 through 20:00 inclusive, exactly **11 hourly valid instants**, DST-aware. The caller selects an explicit cycle or asks for the newest complete one before a UTC cutoff. The planner HEADs each required GRIB object, reads each `.idx`, resolves selected fields/levels and their exact byte ranges, checks all 11 valid times, byte caps, and GRIB `Last-Modified` against a `--newest-complete-before` cutoff. It probes at most eight six-hour cycles by default. There is presently no multi-date command and no issue-horizon field in a weather run.

The collector downloads **only selected GRIB messages by HTTP Range**, not each entire GFS product file. However, each selected message still contains the **global 0.25° grid**. A range cannot crop geography inside a GRIB message. The raw `data/raw/weather/<run-key>/payloads/` therefore retains global selected fields. Parser v6 decodes them in memory, then stores only the footprint crop; the verified recent derived artifact was 8 × 24 cells covering 77 required nodes for all seven configured sites. Site sampling and neighbourhood calculations reuse that single run's compact grid for every site, so Sofia and Shumen on the same target date/cycle must not trigger separate acquisition. The `gfs_0p25_global` geometry in metadata describes the source; it does not mean the derived matrix stores the globe.

Current `weather-ingest resume --run-key` is **strictly offline**. It can finish parsing, sampling, validation, features, and SQLite persistence from a complete raw manifest. It **cannot continue a partial raw download**: a partial raw run is terminal and `fresh` creates a new UUID. The `fresh` duplicate gate only recognizes an exact already successful acquisition after inventory probing; it is not a batch checkpoint. Thus neither a shell loop nor repeated `fresh` alone meets the requested long-running resume behavior.

Local disk measurements (read-only inventory, 2 October 2026): complete 11-hour raw runs use 1,025.85–1,115.76 MiB each; recent compact interim runs use 25.32–43.98 MiB. D: had about 390 GiB free at inspection. The 2026-09-11 older parser/normalizer history alone uses about 46 GiB, despite that run being successfully persisted. Those are measurements, not a promise for every historical lead/cycle.

Official [NCEP GFS product documentation](https://www.emc.ncep.noaa.gov/emc/pages/numerical_forecast_systems/gfs.php) says the model produces hourly output through forecast hour 120, so D+3 is structurally feasible under this 11-hour policy. [NCEI's GFS page](https://www.ncei.noaa.gov/products/weather-climate-models/global-forecast) describes a trailing 30-day AWS cloud window, whereas read-only HEAD probes on this repository's AWS object path returned HTTP 200 and historical `Last-Modified` for a 2023-10-02 object and a 2022-05-01 object. This is evidence for **two objects**, not archive completeness for the cohort. Treat exact-cycle and every-lead recoverability as a hard per-job preflight; do not infer it from a provider description or two successes. [NOMADS Grib Filter](https://nomads.ncep.noaa.gov/info.php?page=opendap_grib_migration) supports geographic subregions for its served files, but its historical coverage and equivalence to the existing AWS archive are not established for this backfill.

## Chronological evaluation reserve: exact 2025 dates

Reserve the whole source season 2025 (local dates from 2024-10-01 through 2025-09-30) as the **untouched historical backtest** while selecting/tuning an initial pooled model on 2022–2024. Within the v2 complete-vector audit this is **131 distinct target dates, 242 site-days**, with 80/23/5 positive site-days at 100+/200+/300+ and 162/219/237 corresponding negatives. The five 300+ site-days occur on four target dates: 2025-07-19, 2025-08-02, 2025-08-14, and 2025-08-15. Exclude all 2025 site-days **and all three horizons for each of those dates** from model fitting, feature selection, label-policy choice, hyperparameter tuning, calibration fitting, and threshold tuning. Phase 4 should publish these rows as `backtest_2025_examples.jsonl`, separate from `training_examples.jsonl`. Keep unknown rows separately audited, not as negatives.

The exact 131 dates, grouped by month (day of month), are:

| Month | Days | Count |
| --- | --- | ---: |
| 2024-10 | 02, 03, 04, 06, 08, 09, 11, 12, 13, 15 | 10 |
| 2025-03 | 03, 05, 06, 07, 08, 09, 21 | 7 |
| 2025-04 | 13, 16, 20, 21, 22, 23, 24, 25, 28, 30 | 10 |
| 2025-05 | 02, 03, 04, 05, 10, 11, 13, 14, 18, 31 | 10 |
| 2025-06 | 01, 02, 03, 04, 05, 06, 07, 08, 11, 13, 14, 15, 16, 17, 18, 19, 21, 22, 23, 24, 25, 26, 27, 29, 30 | 25 |
| 2025-07 | 01, 02, 03, 04, 05, 06, 08, 09, 12, 13, 14, 15, 17, 18, 19, 20, 21, 23, 24, 25, 26, 27 | 22 |
| 2025-08 | 01, 02, 03, 04, 05, 06, 07, 08, 09, 10, 11, 12, 13, 14, 15, 16, 17, 20, 21, 22, 25, 26, 27, 28, 29, 30 | 26 |
| 2025-09 | 02, 03, 04, 05, 06, 07, 08, 09, 11, 12, 13, 14, 16, 18, 19, 20, 21, 22, 23, 27, 28 | 21 |

Why keep 2025 separate: it is the latest complete, separately repaired/mature season and gives a forward-in-time assessment. It contains every site's available 2025 known examples, 80 confirmed 100+ positives and 23 confirmed 200+ positives, and five of the eight scarce 300+ positive site-days. Reserving **whole target dates** prevents the same weather event at another site or at another horizon leaking across train/test. Do not claim 242 independent events: the unit for uncertainty intervals and resampling is the date, with sites and horizons clustered within it. Keep 2025 out of training and tuning throughout this T-020 cohort and its T-023/T-026 evaluation. Any later choice to train on it would require a new versioned split and a different untouched test; do not silently reuse the 2025 backtest as independent evidence.

**Exclude source season 2026 entirely from this acquisition and joined dataset.** Its calendar season ended on 30 September 2026, but XCContest flights may still be entered or checked. On 3 October the local SQLite has only **81 canonical 2026-season flights on 29 dates**, created by the 7 August 2026 legacy run `f1032827-a98d-4c01-969e-e67b4885f90d`. Its raw manifest has 12 season-wide threshold artifacts and `minimum_scored_distance_km: 100`; it has no all-distance daily activity coverage, so it cannot supply DEC-056 negatives. The current audit policy declares only the repaired 2022–2025 runs. Do not generate 2026 label rows, GFS jobs, or training/backtest examples in this plan; a future 2026 project decision must first establish complete, mature evidence and a new dataset version.

Development seasons 2022–2024 have 736 complete site-days on 387 dates, with 212/42/3 positive site-days at 100+/200+/300+. This is enough to attempt a **pooled** 100+ baseline and chronological validation, thin for 200+ (42 positives), and inadequate for a defensible 300+ probability (three positives). These are label counts **before** GFS as-of availability and weather-quality exclusions, so they do not guarantee final training size or accuracy. The implemented first cohort selects **160 of the 212 development 100+ positives** and **160 of the 524 development 100+ negatives**. All 42 development 200+ positives are mandatory, thereby retaining all three 300+ positives (2023-08-21, 2023-08-22, 2024-06-29); every positive at a site with 20 or fewer development positives and all known development rows on the technical sample dates are also mandatory. Remaining seats are allocated with at least one per nonmandatory site/season/month/threshold-vector stratum and proportional largest remainders, then selected by a pinned hash rank without looking at weather or model scores. The emitted inclusion fractions and weights are conditional on this frozen policy and audit. The output has **320 development site-days on 235 target dates**, with every selected date's D+1/2/3 examples kept together. If all three horizons have eligible weather, it expands to **960 horizon-specific training examples**; the final count can be lower after as-of/weather-quality exclusions. The planner also records 416 eligible-but-unselected development site-days. The 2025 backtest is **not sampled**. Sampling can help fit/rank but changes prevalence: calibration and final metrics must use an explicitly defined population/weighting and must not present the balanced training sample as an unconditional flying-day probability. A later change to the seed, quotas, or strata requires a new policy and plan identity before weather acquisition.

Use 2022–2024 only for development: chronological rolling-origin validation with whole-date folds, e.g. fit 2022 → predict 2023, then fit 2022–2023 → predict 2024. Tune only on development predictions; fit a calibrator from out-of-fold development predictions, not in-sample scores, and state the label/activity population it calibrates. Once policy and tuning are frozen, refit on allowed development rows and evaluate once on 2025. Report per-horizon and pooled metrics, false positives/negatives, site and season coverage, Brier/reliability where support permits, and date-clustered uncertainty. Do not treat repeated horizons as independent observations. Three development 300+ positives and four 2025 positive dates do **not** support a precise 300+ calibration or accuracy claim; report it as exploratory with broad uncertainty. These model/evaluation actions belong to T-023/T-026, not phase 3.

## Acquisition identity and as-of flow

### Training and prediction example grain

The final supervised row has **one site, one target local date, and one horizon**. Its stable key includes `(site_id, target_local_date, horizon, issue_local_date, issue_cutoff_utc, selected_cycle)` and the cohort/policy identity. It contains weather features from only that horizon's as-of GFS run plus the target site-day's flight-label vector; it must not contain the other two horizons' feature vectors as columns. The flight outcome is a site-day fact, so it is deliberately repeated across up to three rows with different forecast evidence.

For example, an issue on 2025-08-01 produces three prediction inputs per site: `(2025-08-02, D+1)`, `(2025-08-03, D+2)`, and `(2025-08-04, D+3)`. Historical training also observes the **same** target date through separate prior issues: `(2025-08-02, D+1)` uses the issue on 2025-08-01, `(2025-08-02, D+2)` uses 2025-07-31, and `(2025-08-02, D+3)` uses 2025-07-30. These are three separate rows with three different GFS issue cycles/lead ranges and one shared outcome. A D+1 row describes tomorrow's 10:00–20:00 local window from the prior-evening issue; `D+1` is a calendar-horizon label, not a claim that every valid hour is exactly 24 hours after issue time.

The phase-3 cohort sampler selects **site-days** so all available horizons of a selected site-day enter the same split. The phase-4 join expands those site-days to horizon-specific rows and records a missing/exclusion reason per horizon when a required as-of forecast is unavailable. The 242 known 2025 backtest site-days would yield at most **726** backtest rows; 320 selected development site-days would yield at most **960** training rows. Never infer three independent flight events from those rows. For a pooled model, include `horizon` and exact numeric lead/forecast-age information as features and report performance by horizon; separate horizon models remain a later modeling comparison. Validation folds, backtest assignment, calibration assessment, and uncertainty estimates group by target date so the same flight outcome and weather day cannot cross folds. At inference, build exactly one row for each requested `(issue date, site, target date, horizon)` and apply the same feature schema.

One planned **job** is `(cohort_id, target_local_date, horizon D+N, issue_local_date, issue_cutoff_utc, source_product_key/cycle, 11 valid UTC times, source/selectors/catalogue versions, site/sampling/feature-policy hashes, usage-policy hash)`. The issue date is `target_local_date − N local calendar days`; its cutoff is `20:00 Europe/Sofia` converted independently to UTC (17:00 UTC in summer, 18:00 UTC in winter). A target day thus normally has **three separate issue/cycle jobs**, not one weather run reused for all horizons. Example: for target 2025-08-02, issue dates are 2025-08-01, 2025-07-31, and 2025-07-30. The same target day at Sofia and Shumen shares each of those three jobs and its 11 source-valid hours; both sites are sampled from each job's compact grid. No job is keyed by flight ID or site ID.

### Issue cycle, lead hours, and the 20:00 publication target

DEC-055 already accepts `20:00 Europe/Sofia` as the **data-availability cutoff** for an issue. It does not yet define a service-level promise that the final prediction is first published at exactly 20:00. GFS has nominal 00/06/12/18Z cycles. At the accepted cutoff it is 17:00 UTC in summer and 18:00 UTC in winter, so 18Z cannot be a usable completed cycle. The newest expected cycle is therefore **12Z**, with 06Z as the normal fallback only when the complete required 12Z inventory was not available by the cutoff. Keep the selection rule as “newest complete by cutoff”; do not hard-code 12Z and silently use incomplete data.

For a 12Z issue cycle and the 10:00–20:00 Sofia valid-time window, the exact hourly forecast leads are:

| Sofia offset | D+1 | D+2 | D+3 |
| --- | --- | --- | --- |
| UTC+3, summer | f019–f029 | f043–f053 | f067–f077 |
| UTC+2, winter | f020–f030 | f044–f054 | f068–f078 |

These are **forecast lead hours**, not cycle hours. The cycle is normally 12Z; each horizon has eleven different hourly leads. Official NOMADS listings provide a useful current timing check: on [2026-08-03](https://nomads.ncep.noaa.gov/pub/data/nccf/com/gfs/prod/gfs.20260803/12/atmos/) the 12Z 0.25-degree `pgrb2` f077/f078 products were listed around 15:52–15:53 UTC. That would be about 18:52–18:53 Sofia summer time, leaving roughly one hour before the 20:00 cutoff; winter has about two hours of wall-clock margin for the same maximum lead. This is operational evidence, not a permanent publication guarantee, so phase 3 must measure availability from source metadata for every historical job and the production scheduler must keep the fallback rule.

For the future operational issue, begin watching the 12Z inventory as it becomes available instead of waiting until 20:00 to start all work. The three issue-date targets D+1/D+2/D+3 share one selected cycle and metadata session but remain separate immutable jobs because they have different valid dates and lead ranges. Fetch/parse them with bounded concurrency or serially as capacity allows, then publish only after all required jobs and predictions pass. The observed roughly 15-minute one-job pipeline suggests three serial jobs can usually finish before 20:00 if the far 12Z leads arrive near 18:53 local, but phase 3 must record real end-to-end timings before promising a publication SLA. If “visible by 20:00” becomes a strict product requirement, record a separate scheduler/SLA decision using measured margin; do not change the historical cutoff or substitute 06Z merely to hide slow processing.

For each job:

1. Read and hash-verify the frozen label audit and cohort manifest. Calculate the exact target valid instants with `sofia-flying-window/1`; derive the issue cutoff with IANA `Europe/Sofia`, including DST boundaries.
2. Probe 00/06/12/18Z candidate cycles backward using the current GFS `.idx`/HEAD selector contract. Require **every** valid hour and required product, exact parameter/level/interval semantics, and a provider availability timestamp no later than the issue cutoff. Persist candidate order, rejection reasons, selected cycle, inventory/index hashes, `Last-Modified`, ETag, planned range bytes, lead hours, and cutoff. An absent or ambiguous pre-cutoff cycle is an explicit `missing_weather` job, never filled with D+1, a later cycle, ERA5, or an observation. Metadata probing must be rate-limited and checkpointed too; archive re-probe changes fail closed and trigger a new plan identity.
3. Sum unique `(cycle, lead, byte range)` resources and exact planned bytes. Enforce per-job and batch byte caps, free-disk reserve, and a reviewed storage destination. Execute in deterministic date/horizon order, one worker initially. Download each planned index/range once per job, parse/compact/sample **all seven approved site footprints once**, then persist via existing offline stages. Select only the audited site-days during the later join, without reacquiring the GFS resource for each site.
4. Verify raw and effective stage hashes, SQLite success and training-use authority, selected cycle's as-of evidence, 11 valid instants, seven daily feature snapshots, and date/horizon uniqueness before marking the job complete. A successful job with zero selected sites on that date is a planning error, not useful work. Write immutable completion/error evidence and aggregate coverage/storage summaries.

Do not assume the current `--newest-complete-before` option is by itself the entire phase-3 dry run: it is currently inside `fresh`, after which payload collection starts. Produce two immutable artifacts: an **offline cohort plan** with site-days, split, horizons, issue cutoffs and candidate cycles; then a **resolved acquisition manifest** from a metadata-only probe with exact selected cycle, lead/range inventory, missing-source dispositions and byte budget. The probe may contact the source for HEAD/`.idx` only with an explicit metadata-network flag, and must download no GRIB payload. It must never rewrite the offline cohort plan. A changed probe result creates a new resolved acquisition ID; payload execution is pinned to one such ID.

## Options for the full run

| Option and flow | Advantages | Limitations / fit |
| --- | --- | --- |
| Operator PowerShell loop over `weather-ingest fresh` for every date/horizon, saving console output | Minimal new code; useful for a handful of manually reviewed technical jobs | No frozen manifest or job ledger; interruption loses place, raw partial restarts, hard to enforce aggregate bytes/as-of provenance. Unsuitable for the main backfill. |
| One monolithic multi-date GFS run, perhaps grouping all target dates under one cycle | Can reuse source objects and minimize some repeated HEAD/index work | Rewrites the accepted one-local-day run contract, creates huge failure/retry and audit domains, and complicates site/date/cycle evidence. Not the MVP direction. |
| **Manifest-driven local batch orchestrator over one-date weather runs** | Durable exact scope, one fetch per `(target date, horizon)`, bounded batches, retry/skip, date-level leakage controls, hashes and per-job evidence. Fits Python batch + SQLite/local artifacts and reuses T-018 stages. | Requires a metadata planner, batch checkpoint/CLI, and raw-range resume enhancement; current global raw footprint still requires a storage gate. **Recommended.** |
| Cycle/lead content-addressed source-object cache or a local/object-store queue with distributed workers | Can reuse source ranges across repeated cohort versions/reprocessing and support worker leases/observability like larger data platforms | Different target dates have disjoint 11-hour valid windows in the present policy, so cross-date range savings may be negligible. More identity, retention, locking, and cost complexity. Add only after a manifest proves material overlap or multiple workers are needed; do not replace the day-level join identity. |
| Provider-side regional GFS subset, or local crop-and-retain-only-regional GRIB | Potentially cuts long-term raw disk use dramatically | Current AWS byte-range source serves global messages. NOMADS regional filtering is documented, but historical cohort availability/equivalence is unverified. Locally discarding global source bytes changes DEC-046 replay/audit guarantees and needs a versioned retention/evidence decision. Prototype separately before relying on it. |

The recommended design uses the common enterprise pattern of **immutable input manifests, idempotent bounded jobs, explicit lineage, checkpoints, and separate raw/derived storage**. It does not require a cloud service for this local-first product. If retained global raw exceeds the workstation, a reviewed local cold volume or other approved artifact store is the simplest way to keep replayable raw evidence while keeping compact derived data hot. Any new storage root/retention behavior needs a documented architectural decision and audit/restore test before the broad run.

### End-to-end batches that fit the disk

Do not run a “30% collection” that stops after raw download. A batch contains a deterministic set of complete date/horizon jobs, and **every job goes all the way to verified SQLite persistence before it counts as complete**:

1. acquire and hash-check the planned ranges;
2. finalize the immutable raw boundary;
3. parse, crop to the compact Bulgarian/site footprint, sample all sites, validate, and build features;
4. commit the complete provenance graph and seven expected site snapshots to SQLite in the existing transaction boundary;
5. rerun persisted-graph, integrity, uniqueness, and effective-artifact checks;
6. write a completion/retention receipt; only then may the global raw payload be archived or pruned under the accepted retention policy.

Create each batch from the resolved acquisition manifest before execution. Permit both human-friendly target-date bounds and hard capacity bounds. Date ranges make copying and progress reporting understandable; exact planned bytes and minimum free space are the actual safety controls. A percentage is unsuitable because jobs have different byte counts and retry/staging overhead.

The batch planner should choose the largest deterministic prefix that satisfies all configured limits, for example `--target-date-from/--target-date-to`, `--max-jobs`, `--max-new-gib`, and `--minimum-free-gib`. Treat one target date's D+1/D+2/D+3 jobs as the normal placement unit so an operator batch finishes all horizons for that date; a source-missing or quarantined job may still leave an explicit partial-date outcome. Before starting a job, reserve its probed payload bytes plus a conservative measured staging/derived allowance. If that reservation would cross either cap, finish the current job and stop **between jobs** with the batch in a clean resumable state. An unexpected disk or network failure inside a job leaves atomic range/stage checkpoints; `resume-live` finishes that same job before advancing. It must never collect the next raw job while a prior complete-raw job is still waiting for parse/validation/persistence.

After the 25 GiB technical sample measures the real peak, start broad operation conservatively at **100 GiB maximum new bytes and 80 GiB minimum free on D:**. At the observed 1.0–1.1 GiB per job, that is roughly 27–30 complete target dates with three horizons, before exact staging allowance. These are initial operator defaults rather than cohort constants: the immutable batch records their actual values, and later batches may use a smaller cap for a particular USB target or a larger cap only after measured peak and copy/verification time justify it.

This supports the intended physical workflow: run one bounded batch completely into SQLite, verify it, copy or prune eligible global raw, back up the database/catalogue, reclaim hot space, then create or run the next immutable batch. Previously persisted jobs remain join-ready even when their full global raw bytes are no longer on D:, provided the accepted compact-retention receipt exists.

### Rotating hot/cold storage and safe local eviction

Use D: as a bounded **hot working cache**, not as the permanent home of every raw run. A completed run may be moved to a laptop, USB flash drive, or another reviewed volume after all of the following are true:

1. raw collection is complete and every planned index/range hash is verified;
2. parser, compact-grid, sampling, validation, feature building, and SQLite persistence succeeded;
3. SQLite contains the expected seven site snapshots and complete provenance graph, and integrity/foreign-key plus persisted-graph checks pass;
4. the effective artifact audit passes and an archive receipt records run key, source cycle/date/horizon, raw/interim manifest hashes, total files/bytes, bundle or directory-tree SHA-256, destination volume ID, and archive-relative path;
5. the archived copy is independently reread and hash-verified before the local copy is removed.

The future join should be **database-first**: daily feature values, profile layers, missing/quality states, native/source provenance, cycle/valid/lead identity, usage authority, and manifest hashes already live in SQLite. It therefore does not need to open the global raw GRIB payload for every joined row. It must require a valid persistence graph plus an `online` or `archived_verified` artifact disposition and include the archive receipt in the dataset manifest. Full raw/stage audit or offline reconstruction still requires restoring the run to its original `data/raw/weather/<run-key>/` and `data/interim/weather/<run-key>/` paths.

Implement storage commands before the broad backfill; names remain proposed:

```powershell
# Copy one complete run to a named cold volume, verify the destination, keep local bytes.
uv run --project services/ml weather-artifacts archive `
  --run-key <uuid> --destination <volume-root> --verify-all

# Remove only the already verified local copy and retain its archive receipt/catalogue entry.
uv run --project services/ml weather-artifacts evict-local --run-key <uuid>

# Restore to the canonical project paths and verify before audit/replay.
uv run --project services/ml weather-artifacts restore `
  --run-key <uuid> --source <volume-root> --verify-all
```

`evict-local` must refuse partial, quarantined, unpersisted, unaudited, unjoined-required, missing-destination, or hash-mismatched runs. It must resolve and print the exact raw/interim directories, never accept a parent/glob target, and remove them only after verifying the archive receipt against both SQLite manifest hashes and destination bytes. The batch orchestrator should stop before a configurable free-space reserve, then archive or compact-prune eligible completed jobs under the accepted policy before continuing. Store whole full-raw run bundles on one volume where possible; the global archive catalogue may distribute different runs across several named volumes. Do not rely on drive letters alone because Windows can reassign them. Back up the small SQLite database, cohort/acquisition manifests, archive catalogue, compact retained evidence, joined outputs, and policy files on at least two independent media.

This makes the user's proposed rotation viable: after a run is persisted and archived, its approximately 1.0–1.1 GiB raw payload need not remain on D: for the later join. The current SQLite file is only about 19 MiB with four weather runs; recent effective interim evidence is roughly 25–44 MiB per run. Raw GRIB is already compressed, so ordinary ZIP compression should not be counted as meaningful capacity savings. USB flash storage is suitable as a cold copy only after complete reread/hash verification; for irreplaceable evidence, one flash copy by itself is a weak retention boundary.

The aggregate capacity described by the owner is below the unfiltered 1.5–1.7 TiB upper bound, so full-raw retention for every job is not a credible default. Use a **hybrid retention policy** for this backfill, and record it as an accepted decision before implementation:

- Keep full raw for the 15-job technical sample, for the first successful job under every new source/catalogue/parser policy tuple, and for failed or quarantined jobs until they are resolved. These bounded examples preserve source-decode and replay evidence.
- For other successful jobs, retain the request and index metadata, source headers and hashes, lossless compact Bulgarian/site-footprint matrices and masks, effective derived manifests, SQLite provenance/features, validation results, database backup, and a hash-linked pruning receipt. After all checks and a second copy of the small durable evidence exist, a command may remove only the global selected-message payload.
- A laptop or USB copy can be a temporary safety copy while a batch is checked, but the plan does not assume that every global raw bundle remains there forever. Failed/quarantined evidence is never pruned merely to make space.

The two supported retention outcomes are therefore:

- **Full-raw cold retention (strongest replay):** retain every source byte externally; evict only the D: copy. This preserves current audit and exact offline replay after restore.
- **Compact-evidence retention (recommended for most broad-backfill jobs on the available storage):** after verified SQLite persistence, preserve the bounded evidence listed above and permit versioned deletion of the global selected-message bytes. Phase 4 is database-first and therefore does not need the raw GRIB to perform the join. This preserves the exact seven-site values and model-ready join but can no longer prove or rerun the original GRIB decode locally. It changes DEC-046-style replay guarantees and needs an accepted decision, new audit semantics, a `prune-global-raw` command, and restore/redownload limitation tests before use.

Deleting raw without either a verified cold copy or an accepted compact-evidence pruning receipt is unsupported. Although a simple SQL join may still return feature values, current `weather-ingest resume`, `weather-artifacts audit`, and the duplicate-acquisition gate hash-verify filesystem manifests and would fail when those paths disappear.

## Resume contract to implement

`weather-cohort` is implemented. The probe, batch, live resume, and retention
commands below remain proposed and are **not implemented yet**:

```powershell
# Implemented offline cohort, split, and candidate-cycle job graph; no NOAA traffic.
uv run --project services/ml weather-cohort

# Explicit, bounded metadata-only archive check: HEAD and .idx, no GRIB payload.
# Repeating this command resumes verified probe jobs; completion emits an acquisition ID.
uv run --project services/ml weather-backfill probe --cohort-plan-id <id> --max-jobs 15 --allow-metadata-network

# Freeze one executable batch by dates and/or capacity. The planner may stop earlier
# than the requested date range so the exact jobs fit every limit.
uv run --project services/ml weather-backfill batch-create `
  --acquisition-id <id> `
  --target-date-from <YYYY-MM-DD> --target-date-to <YYYY-MM-DD> `
  --max-jobs <N> --max-new-gib <GiB> --minimum-free-gib <GiB>

# Execute only that immutable batch; every completed job reaches SQLite.
uv run --project services/ml weather-backfill run --batch-id <id> --allow-live-network

# After interruption: live range/job recovery, still explicit about network.
uv run --project services/ml weather-backfill resume-live --batch-id <id> --allow-live-network

# After persistence/audit and under the accepted hybrid retention decision only.
uv run --project services/ml weather-artifacts prune-global-raw --run-key <uuid>

# Existing command remains offline and never creates a NOAA transport.
uv run --project services/ml weather-ingest resume --run-key <complete-raw-run-uuid>
```

The resolved acquisition manifest and every derived batch manifest are immutable and content-hashed; the ignored local checkpoint is append-only per job/attempt. `batch-create` excludes already verified completed jobs and records exact planned raw/staging bytes, starting free space, required reserve, target-date bounds, ordered jobs, and retention policy. The metadata probe has its own per-job checkpoint so repeating `probe` resumes missing inventories and emits the resolved manifest only after the requested cohort or sample scope has been classified. On payload restart, re-verify that manifest, all completed raw/stage hashes and SQLite result, skip verified completed jobs, finish offline stages for complete-raw jobs, and fetch only missing ranges for a partially downloaded current job. Write each range to a temporary file, length/hash-verify and atomically publish it, then append a checkpoint. Interrupted temporary files are discarded after validation; completed ranges are never redownloaded merely because a process stopped. Use one writer/lock initially and record host/PID/attempt timestamps; stale-lock recovery must verify evidence before taking over. Expose `status`/`audit` with completed, persisted, retention-eligible, pruned/archived, remaining, missing-source, quarantined, bytes planned/written/reclaimed, and next job. `Ctrl-C`, transient network errors, or a full disk must leave a resumable, inspectable state.

This needs a **new versioned raw-collector protocol**: today's partial manifest is terminal, and immutable artifact paths/ledger events cannot be overwritten. Use append-only collection-attempt/checkpoint events and one final effective complete raw boundary when all planned ranges are present. A changed `.idx`, content length, source ETag/`Last-Modified`, policy hash, or planned byte range must quarantine the attempt instead of merging two source revisions. Preserve `weather-ingest resume` as offline-only; name the network-capable recovery command `resume-live` so operators cannot confuse them. If a job is irrecoverably partial, record a superseding attempt and reuse only verified source-identical ranges; never forge a completed old run. Test crash points after plan, index, range, raw manifest, each offline stage, and committed SQLite transaction.

## Bounded sample, capacity gate, and actual later execution

Run the first end-to-end technical sample on **five target dates × three horizons = 15 planned jobs**: 2022-05-01, 2023-08-22, 2024-06-29, 2025-07-19, and 2025-08-02. Their known rows collectively cover all seven site footprints, positive and negative 100+ outcomes, all four source seasons, several rare 300+ positives, and all horizons. `2025-08-02` also exercises the existing historical run, **only if** the selected as-of cycle and acquisition identity match; the stored 00Z run is not automatically accepted as the newest pre-cutoff D+1 cycle. Probe every sample issue/cycle/lead first. At the observed approximately 1.0–1.1 GiB raw per job, 15 jobs would use roughly 15–17 GiB raw plus derived/staging headroom; use the probe's exact byte sum and a conservative 25 GiB sample cap, then stop and review. Check DST dates in synthetic planner tests even if this sample does not hit a transition.

The **unfiltered** 2022–2025 complete-vector inventory would require up to 518 dates × 3 = 1,554 day/horizon jobs, approximately **1.5–1.7 TiB raw** at observed per-job sizes, plus derived and safety headroom. The **unsampled 2025 backtest alone** is 131 × 3 = 393 jobs, roughly **0.39–0.43 TiB raw**, already near or beyond the currently free 390 GiB. The implemented cohort planner reduces development to 235 target dates × 3 = 705 jobs; with the 393 backtest jobs, its exact offline scope is **366 unique target dates and 1,098 date/horizon jobs**. At the observed 1.0–1.1 GiB per job, this suggests roughly **1.1–1.2 TiB raw** before derived and safety headroom; exact planned bytes still require metadata probing. **No 2026 date or GFS job is included.** Existing raw is already compressed GRIB; do not budget on speculative generic compression. No broad job starts until a measured plan states selected dates, cycles, exact range-byte sum, expected derived bytes, compact-retained bytes, peak per-job staging, free space after a safety reserve, and the accepted hybrid retention policy. Use bounded end-to-end batches (for example, 5–15 jobs initially), persist and audit every job, apply its retention action, back up the small durable state, reclaim hot space, and only then expand. The previously measured complete 11-hour run took about 15 minutes; 1,000+ serial jobs would take many days before retries, so resumability is a requirement, not a convenience.

Phase 4 then consumes the frozen manifest in batches, joins only matching `site_id + target_local_date + issue_local_date + horizon + selected cycle` weather evidence, rejects duplicates/after-cutoff/missing/ambiguous rows, and publishes versioned `training_examples.jsonl` (2022–2024), `backtest_2025_examples.jsonl`, `excluded_examples.jsonl`, and a hashed split manifest. Each JSONL record is **one site/target-date/horizon prediction example**, not a site/day record with three forecast vectors nested together. No target's 2025 backtest row may be written to the training file; no 2026 row is emitted. Keep units, quality/missing states, provenance, flight-label reasons, policies and source hashes. The join must use no flight count/distance as a forecast predictor; those remain label/audit evidence.

## Existing GFS disk artifacts: read-only cleanup assessment

| Run key | Local evidence | Phase-3 relevance and action |
| --- | --- | --- |
| `e5c7d44f-93a3-4052-b774-642dbdc340ce` | 2025-08-02 historical, succeeded; ~1,114 MiB raw, ~25 MiB interim | A reserved 300+ backtest date. Preserve; reuse only if exact as-of cycle/horizon/identity passes the new manifest. |
| `45a58867-ad60-43f6-b926-07b077503ee5` | 2023-10-03 historical, succeeded; ~1,026 MiB raw, ~44 MiB interim | Known positive/negative site-days. Preserve pending cohort and as-of check. |
| `0200117a-2638-4e98-ac42-534db32315dd` | 2026-09-14 operational, succeeded; ~1,110 MiB raw, ~25 MiB interim | Not in audited 2022–2025 training cohort; retain accepted T-018 replay evidence. |
| `403c5135-8ced-4b54-a999-1c27e7ec78a3` | 2026-09-11 operational, succeeded; ~1,116 MiB raw, **~47,097 MiB interim** | Not in training cohort. Older superseded parser/normalizer stages dominate disk, but the persisted run and all-history ledger may still reference them. Candidate for a separate, verified archival/retention migration; do not manually delete stage folders. |
| `0e2c4771-acbc-42ab-b6f3-4b5f36946270` and `baa31654-3f5d-4ade-8e87-0a599cb81c53` | One-hour 2026-08-21 low-level test scopes, complete raw but **no SQLite ingestion row**; together ~59 MiB raw + ~1,418 MiB interim | Not 11-hour cohort evidence and cannot become D+1/2/3 training rows. Best initial archive/delete candidates **after** a reference scan, effective/all artifact audit, and recoverable backup; expected saving ~1.44 GiB. No deletion is part of this planning request. |

Before any cleanup implementation: enumerate all raw/interim run UUIDs, SQLite manifest pointers, ledger references, docs/test references, effective/all audit results, exact sizes and SHA-256s into a dry-run report. Preserve succeeded-run DB references and immutable chain; only a reviewed retention command with archive/restore verification may remove local bytes. Freeing the 1.44 GiB tests or even the 46 GiB old history does **not** make a 1+ TiB backfill fit this disk.

## Implementation order, verification, and proposed commits

The offline cohort planner in step 1 is implemented and was run against the pinned v2 audit, producing plan `2ed9a4d3c46480dc730958894beca1dcb954b07c737b910f64ea7dac4f9c8cad`. It verifies the label audit and emits candidate cycles; it makes no claim that a candidate source object exists or met the cutoff. The **next implementation step is the metadata-only probe**, followed by the resumable end-to-end batch protocol. The current one-date command cannot resume a partial raw download, stop safely by aggregate storage, or record compact-retention receipts. After steps 2–3, run the metadata-only five-date probe. Only after its exact bytes/cycles are reviewed should the 15-job live sample run. Broad 2022–2025 batches come after the sample and retention lifecycle pass.

1. **Phase-3 cohort policy and planner — implemented:** data-driven policy tied to v2 audit hash; deterministic 2025 backtest reserve and 2022–2024 development sampler; row/date grouping; offline `weather-cohort`; schema and manifest hashes. Verified 131 test dates, 242 test site-days, 320 development site-days, all eight 300+ positives across development/test, no unknown or split crossover, and byte-identical replay. Reject any 2026 row/job under this cohort policy. Focused DST, site grouping, integrity, and stratum inclusion tests pass.
2. **Metadata-only as-of probe:** share the existing GFS selector/inventory logic without payload GET; record candidate completeness/availability and exact bytes for D+1/2/3. Test summer/winter cutoffs, multiple sites on one date, no complete cycle, changed inventory, unavailable historical lead, and fail-closed behavior. Do a bounded read-only archive probe of the five-date sample.
3. **Resumable end-to-end batch protocol:** implement immutable `batch-create` plus per-range atomic checkpoints and `weather-backfill run/resume-live/status/audit` with job/resource identity, date bounds, byte/free-space budgets, locks, explicit network flag, and the existing offline stage service. A job is complete only after SQLite verification; never advance while complete raw is waiting for offline stages. Keep `weather-ingest resume` offline. Test interruption at every boundary and that a resumed run does not re-request a verified range or duplicate SQLite rows; test clean stop before a cap, unexpected full disk, corrupt/checkpoint/source-change quarantine, and exclusion of already persisted jobs from later batches.
4. **Bounded live sample only after byte/storage review:** execute at most the 15 sample jobs with an approved exact byte cap and local GFS usage policy; compare manifest plans to actual cycles/lead hours, raw size, compact size, seven site snapshots, hash audits, elapsed time and no duplicate date/horizon acquisition. Report missing/unavailable jobs honestly; do not turn failures into later-cycle substitutes.
5. **Storage and phase-4 gate:** record the hybrid retention decision, then implement and test the archive catalogue plus `archive`/`evict-local`/`restore` and `prune-global-raw` lifecycle against disposable synthetic and bounded real runs. Measure copy/reread throughput on each intended volume, require an explicit free-space reserve, prove that an archived run restores and fully replays, and prove that a compact-retained run still passes the new persisted/compact audit and database-first join preflight while honestly refusing raw replay. Freeze the exact broad manifest, batch layout, peak hot bytes, and retained bytes before broad acquisition. Update `services/ml/README.md`, root setup only if needed, `docs/handoff.md`, and `docs/decisions.md` for the accepted storage/protocol choice. Leave T-020 In Progress until the actual phase-4 join and all required validation pass.

Suggested short-lived, imperative commits during implementation (split further if review warrants):

1. `T-020 freeze phase-3 cohort and 2025 backtest reserve`
2. `T-020 add metadata-only GFS as-of acquisition planner`
3. `T-020 checkpoint resumable GFS raw ranges`
4. `T-020 orchestrate bounded weather backfill jobs`
5. `T-020 archive and prune completed weather runs`
6. `T-020 verify multi-season three-horizon sample`
7. Later phase 4: `T-020 join horizon-matched weather and flight labels`
8. Later phase 4: `T-020 validate and document joined dataset replay`

Run focused ML tests, the full ML test suite, Ruff lint/format, `npm.cmd run repo:check`, `git diff --check`, effective/all weather artifact audits where applicable, and read-only SQLite integrity/foreign-key and replay checks. Review the final diff for unrelated changes. No model, alert, or aviation-safety claim is implied by a completed dataset.
