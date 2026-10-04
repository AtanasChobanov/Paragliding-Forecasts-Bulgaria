# T-020 one-off GFS metadata timing probe — 4 October 2026

## Purpose and method

The owner requires the D+1/D+2/D+3 predictions **and alert dispatch to finish by 20:00 Europe/Sofia**. This is a delivery deadline, so source availability at 20:00 is too late. This read-only probe checked the existing NOAA Open Data on AWS 0.25° GFS product path for five pinned technical target dates and fourteen recent issue dates (20 September–3 October 2026). For each issue/horizon, it checked all eleven local 10:00–20:00 valid hours for both 12Z and 06Z. The historical sample used GRIB `HEAD` plus `.idx` `GET`, parsed the index with the repository's selectors, and summed selected GRIB byte ranges. The recent dates used `HEAD` on both GRIB and `.idx` for timing only. **No GRIB payload was downloaded or persisted.** The disposable, ignored local checkpoint is `data/local/gfs-timing-probe-2026-10-04/`; it is not a product command or committed dataset.

All 114 job/cycle inventories returned the required eleven GRIB and index objects. All 30 historical inventories passed the current index selector contract. This validates the 15 sampled cohort jobs, **not** the other 1,083 planned cohort jobs; the recent issue dates are outside the frozen cohort. The source `Last-Modified` maximum across the eleven GRIB and index objects is used below as an availability proxy. It is not a logged first-publication event, a promise of future timing, or proof that a historical object was already accessible at that time. Source object replacement could move it later. The current planner checks the GRIB `Last-Modified` but does **not** include index `Last-Modified` in its as-of check; the production metadata resolver must fix that and retain both timestamps.

## Measured completion proxy

Every time below is local `Europe/Sofia` daylight time (UTC+3). Bulgaria uses UTC+2 in winter; use IANA timezone conversion per issue date, not a fixed offset. The source product has four nominal daily cycles, 00/06/12/18Z; only 12Z and 06Z were measured here. Official [NCEP GFS documentation](https://www.emc.ncep.noaa.gov/emc/pages/numerical_forecast_systems/gfs.php) confirms hourly output through forecast hour 120, covering the required D+3 leads.

| Historical target date | D+1 issue / 12Z latest | D+2 issue / 12Z latest | D+3 issue / 12Z latest |
| --- | --- | --- | --- |
| 2022-05-01 | 30 Apr / 18:43:11 | 29 Apr / 18:48:40 | 28 Apr / 18:57:07 |
| 2023-08-22 | 21 Aug / 18:40:17 | 20 Aug / 18:46:11 | 19 Aug / 19:05:17 |
| 2024-06-29 | 28 Jun / 18:52:49 | 27 Jun / 19:07:18 | 26 Jun / 19:07:02 |
| 2025-07-19 | 18 Jul / 18:56:07 | 17 Jul / 19:03:07 | 16 Jul / 19:08:01 |
| 2025-08-02 | 1 Aug / 18:57:01 | 31 Jul / 19:02:46 | 30 Jul / 19:06:26 |

The historical selected raw byte ranges are **1.056–1.101 GiB per eleven-hour job** for 12Z (06Z has a similar footprint). These are selected *global* GRIB messages; the cropped derived matrices are much smaller.

| Recent issue date, 2026 | 12Z D+1 | 12Z D+2 | 12Z D+3 | Latest of three |
| --- | --- | --- | --- | --- |
| 20 Sep | 18:53:35 | 19:02:34 | 19:07:24 | 19:07:24 |
| 21 Sep | 18:56:20 | 19:02:21 | 19:08:37 | 19:08:37 |
| 22 Sep | 18:54:51 | 19:00:46 | 19:05:28 | 19:05:28 |
| 23 Sep | 18:54:50 | 18:48:05 | 19:07:33 | 19:07:33 |
| 24 Sep | 18:55:10 | 19:02:31 | 19:08:08 | 19:08:08 |
| 25 Sep | 18:42:13 | 18:47:38 | 18:54:47 | 18:54:47 |
| 26 Sep | 18:57:57 | 18:48:10 | 19:07:41 | 19:07:41 |
| 27 Sep | 18:42:26 | 19:02:26 | 19:09:26 | 19:09:26 |
| 28 Sep | 18:54:30 | 18:49:33 | 18:54:28 | 18:54:30 |
| 29 Sep | 18:56:50 | 19:02:14 | 19:07:11 | 19:07:11 |
| 30 Sep | 18:58:47 | 19:03:37 | 19:09:17 | 19:09:17 |
| 1 Oct | 18:44:19 | 19:18:58 | 19:09:46 | **19:18:58** |
| 2 Oct | 18:56:17 | 19:02:39 | 18:55:01 | 19:02:39 |
| 3 Oct | 18:54:11 | 19:16:31 | 18:55:04 | **19:16:31** |

The latest historical 12Z job in this sample was **19:08:01**; the latest recent one was **19:18:58**, leaving only **41 minutes 2 seconds** before the dispatch deadline. The latest 06Z completion proxies were **13:11:25** in the historical sample and **13:09:21** in the recent sample. These were observed maxima of a limited sample, not tail-latency bounds. D+1/D+2/D+3 can finish at different times; 1 October's D+2 was later than D+3, so a scheduler cannot assume D+3 always gates the issue.

## Consequences for cycle policy and next experiment

1. Keep **12Z as a candidate**, since the sample generally appears around 18:40–19:19 local, but do not promise 20:00 delivery from source metadata alone. The current roughly 15-minute per-job ingestion observation was not measured here on these 12Z jobs; network throughput, concurrent jobs, feature/prediction runtime, alert dispatch, retries, and failure handling are unmeasured. Three serial roughly 1.1 GiB jobs could use most of the observed margin. Prefetch each horizon as soon as its required fields are complete, use bounded concurrency where supported, and reserve measured time for model output and alert dispatch.
2. **06Z is a viable timing fallback candidate** in these samples, appearing around early afternoon local, but its predictive accuracy relative to 12Z is untested. Preserve the selected cycle and exact lead hours in each horizon row. If a 12Z job cannot finish by the delivery deadline, the fallback must be a fully processed 06Z forecast, not a last-minute switch to unprocessed source data. The production policy must say whether the three horizons may use different cycles and must reproduce that rule in historical rows.
3. Before locking the 1,098-job historical acquisition, run a bounded **end-to-end 12Z issue rehearsal**: fetch all three horizons, parse, validate, persist, form the exact prediction inputs, run an actual predictor when available, and measure alert-dispatch latency or a clearly identified stub timing bound. Repeat for several current summer-like days and adverse network conditions; log source first-seen, GRIB/index metadata, bytes, start/finish per stage, and dispatch completion. Test 06Z fallback and retry paths. The model/prediction and alert pipeline do not exist yet, so strict delivery cannot currently be verified.
4. Freeze a versioned operational selection policy from those measurements: a latest safe source-ready time or per-horizon deadline, explicit fallback and buffer, and one 20:00 **dispatch** deadline. Rebuild the historical acquisition manifest and, if the as-of policy changes, the cohort plan identity to match it. DEC-055's `20:00` data cutoff and DEC-064's reference to it are provisional for actual model training under the newly clarified dispatch requirement. Acquiring the broad cohort under the old rule before this decision risks training on a cycle the live service cannot reliably use.
5. A permanent metadata planner is justified for the **full 1,098-job, multi-batch backfill** because it needs deterministic as-of decisions, exact range/byte accounting, checkpoints, and resume across interruptions. The present small timing survey was a one-off operation and adds no product command.
