# Project Handoff

## Read first

1. `AGENTS.md` for repository rules.
2. `docs/tasks.md` for ticket status and scope.
3. This handoff for the active T-020 state.
4. [`T-020-xccontest-activity-ingestion-plan.md`](T-020-xccontest-activity-ingestion-plan.md)
   for the flight-ingestion prerequisite only.
5. [`T-022-sounding-cloudbase-research-note.md`](T-022-sounding-cloudbase-research-note.md)
   for the cloudbase/sounding investigation.
6. DEC-055 through DEC-060 in `docs/decisions.md`, plus DEC-023 through
   DEC-030 for the existing XCContest boundary.
7. The relevant sections of `docs/project-brief.md` and
   `docs/architecture.md` for product/system constraints.

Keep durable decisions in `docs/decisions.md`, ticket lifecycle in
`docs/tasks.md`, and only current actionable state here.

## Current state - 2026-09-25

| Field | Value |
| --- | --- |
| Branch | `feature/T-020-joined-weather-dataset` |
| Ticket | T-020 remains **In Progress**: the focused XCContest 0--2000 km ingestion prerequisite is implemented and locally verified, but the joined flight/weather dataset is still not implemented. The bounded headed live acceptance was deliberately not run in this session at the owner request. T-018 and T-019 remain in Review; ERA5 remains deferred to T-038. |
| Product decisions | The Project Owner accepted the prior-evening forecast cutoff, tri-state flight labels based on recorded activity, and the configurable hybrid overdevelopment baseline. The owner also confirmed that blue days may still be flyable and asked that sounding-derived cloudbase, thermal-top, inversion, and overdevelopment diagnostics be evaluated. |
| XCContest state | The collector now captures source-default season evidence, preserves threshold-first 100+ coverage, and then scans 15 February--15 October source-offered dates for all-distance activity. Manifest-v5/parser/validator/persistence and SQLite accept finite 0--2000 km rows. Exact skipped out-of-window dates are retained as coverage evidence; partial/saturated coverage is not a known-negative result. |
| Implemented ingestion design | The user-facing scope remains repeated `--season`. After threshold-first coverage, each supported activity date captures one source-default parent view. Any parent without an active next page is complete as captured, including exactly 100 rows. Only paginated parents fall back to exact glider classes, and only a paginated exact class runs the eight explicit rescue sorts. Date/category controls change in place on the current season page, preserving XCContest current and archived year-prefixed URLs without root/season/country reconstruction. Observed 0..2000 km records can persist, while later labels must require positive distance for activity evidence. |
| Database scope | Migration `20260925150010_widen_flight_distance_constraint` changes only `flight_records.scored_distance_km` from 100..2000 to 0..2000. It preserves `STRICT`, FKs, unique identity, and existing indexes; no table, column, or index was added. |
| Site-mapping policy | `fresh` and offline `resume` now apply immutable `site-mapping-v3` automatic decisions before residual proposals. Only a valid, same-country coordinate inside one catchment creates approved point/token/takeoff-ID mappings. A valid point outside every catchment is audit-only, rejected without a human-review pause or canonical persistence. No-coordinate, ambiguous, country-mismatched, and contradictory existing mappings remain human review. |
| Implementation plan | [`T-020-xccontest-activity-ingestion-plan.md`](T-020-xccontest-activity-ingestion-plan.md) includes activity ingestion, recovery, bounded live acceptance, and the deterministic automatic coordinate mapping disposition. It does not implement the joined dataset. |
| Sounding finding | IGRA is real balloon observation data and the current pipeline covers Sofia only. A forecast/model sounding from existing GFS profiles works at all seven locations. NOAA READY is a GFS sounding interface, not independent observations, and is not recommended as a production dependency. |
| Historical GFS evidence | The owner collected 2025-08-02 successfully. The 2023-10-03 run initially rolled back on numerical shortwave noise; weather-spatial/7 now clamps only absolute values at most `1e-12` and the retained run resumed offline and inserted seven site snapshots. |
| Next work | The owner may run one bounded headed `xccontest-collect --season <recent-year>` acceptance under the normal 30-second pace and a reviewed explicit view cap; the default 2,000 views remains fail-closed rather than a full-season guarantee. Inspect the manifest-v5 skipped-date audit, source-default evidence, sub-100 parsing, persistence, and honest complete/partial scope status. Do not start a multi-season backfill. After genuine acceptance, record its exact evidence and continue the joined-dataset work separately. |
| Live-source gate | No real XCContest collection, browser pipeline, or ingestion command was run in this session at the owner request. Before any bounded headed acceptance or larger all-distance backfill, confirm the retained XCContest authority covers the rendered-UI workload. Keep sequential 30-second pacing; do not parallelize years or countries. |
| Local verification | After the pagination-first/in-place-navigation correction, the full XCContest suite passed (96 tests), the full ML suite passed (330 tests), Ruff check and Ruff format check passed across ML source/tests, and `npm.cmd run format:check` passed. No live ingestion command was run for this correction. The earlier `typecheck`, `test` (249 tests), `build`, `repo:check`, and database `db:check` results remain valid for their unchanged areas. `npm.cmd run lint` fails in the unmodified `packages/database/test/migration-foundation.test.ts` at lines 450 and 457 (array-type/restrict-template-expressions); it was not changed by this task. The Vite build retains its existing >500 kB chunk warning. |
| T-020 commits | `fe1a39f`, `b67f594`, `2806e78`, `2e6096f`, `da5b619`, `628929d`, `0b49132`, `d8bd2ef`, `7d78b75`, and `1408fa1` implement the verified local slices through the activity-window optimization. The latest T-020 commit removes redundant daily sort/root-reset transitions. The bounded headed acceptance-record commit remains unmade because the owner run failed before collecting evidence. |
| Storage risk | Current retained GFS derived artifacts are too large for an unbounded negative-day backfill. Before broader GFS acquisition, use the compact site-footprint design or an explicitly bounded sample. |

## Accepted T-020 business logic

### Forecast issue policy

- The main daily issue covers D+1, D+2, and D+3.
- The reproducible MVP cutoff is `20:00 Europe/Sofia` on the issue date.
- Historical rows use only the newest complete GFS cycle available by that
  cutoff and the matching forecast horizon.
- A later or same-day run may not replace missing pre-cutoff evidence.
- A morning refresh is optional after MVP and is a separate issue-time cohort.

### XC distance labels

- `100+`, `200+`, and `300+` are inclusive thresholds.
- A confirmed accepted flight at/above a threshold is positive.
- A negative requires accepted positive-distance activity plus mature, complete
  threshold and mapping evidence showing no flight reached the threshold.
- No accepted flight is unknown, not negative.
- One accepted short flight is the MVP activity minimum; counts and distances
  remain in the audit so stricter sensitivity checks need no new collection.
- Known labels are nested: `label_300 <= label_200 <= label_100`. T-023 must
  preserve the equivalent probability order.

### Overdevelopment baseline

T-024 uses the DEC-057 configurable decision tree plus smooth score. It includes
precipitation, instability/convective evidence, cloud/base combinations,
duration/window effects, and a critical `High` override for configured severe
precipitation/overdevelopment evidence or wind over `10 m/s` in the named
policy field/window. API/UI output must include main reasons. Missing critical
inputs cannot silently return `Low`. The result is informational and does not
replace pilot judgement.

### Sounding and cloudbase direction

"Sounding" may mean a real balloon profile or a virtual forecast-model profile.
T-019 already supplies the real NOAA IGRA Sofia observations, but they arrive
after the event and do not cover all seven sites. They remain validation
evidence under T-039.

T-022 should evaluate a deterministic sounding calculation from the existing
GFS profiles at every site. The current pipeline already produces mixed-layer
LCL and PBL-minus-LCL features. The output must preserve a distinct `blue`
state because a dry thermic day may be flyable without a visible cloud base.
Exact parcel policy, inversion threshold, usable-thermal-top rule, display time,
and MSL/AGL presentation remain open. See
[`T-022-sounding-cloudbase-research-note.md`](T-022-sounding-cloudbase-research-note.md).

## T-019 implementation and operational boundary

The accepted T-019 boundary is recorded in DEC-054. The operational
implementation documentation and commands are in
[`../services/ml/README.md`](../services/ml/README.md). The task is now in
**Review**, not Done: its scoped implementation and evidence are ready for
review, while follow-on work remains deliberately separate.

- Source: official NOAA/NCEI IGRA v2.2 raw and provider-derived station ZIPs
  for Sofia `BUM00015614`; station snapshots update daily and observations are
  normally published with roughly two days of delay.
- Command boundary: live HEAD-only `igra-ingest inventory`, bounded live
  `fresh`, then hash-verified offline `resume`, for explicit UTC dates.
- Storage: immutable raw station snapshots plus selected, normalized, and
  validated JSONL/report artifacts only. No SQLite or Drizzle work belongs in
  T-019.
- Time policy: every actual sounding on the requested UTC dates is retained.
  The Sofia 10:00–20:00 flying window is classified later, not filtered here.
- ML boundary: T-020 joins flight labels only to pre-flight exact GFS features.
  IGRA observations are not predictors and are not a required join.
- Comparison boundary: T-039 may consume the effective validated manifest to
  compare GFS at the exact IGRA station and nominal time, then quantify
  profile error and calibration/bias evidence.

### Verified pipeline evidence

The successful fresh command was:

```powershell
uv run --project services/ml igra-ingest fresh `
  --station-id BUM00015614 `
  --date 2025-08-02 `
  --date 2025-08-11 `
  --archive period-of-record `
  --maximum-total-mib 80 `
  --allow-live-network
```

It published run `5ae72afe-e71e-4c32-ade8-cd57426533e8` and its effective
validator manifest at:

```text
data/interim/soundings/5ae72afe-e71e-4c32-ade8-cd57426533e8/validator-v1/af4e1b3b9a8a2aa11de719ae11fd8ec51dafe179d3dea12675b4ddc872b72300/stage-manifest.json
```

`fresh` first checks all five remote objects with HEAD, enforces the compressed
byte cap before any GET, then stores/reuses hash-verified source evidence. It
streams the selected ZIP members, parses fixed-width raw and derived records,
normalizes units/provenance, validates them, partitions accepted/quarantined/
missing evidence, and writes the effective `stage-manifest.json`. Its terminal
JSON is sorted and pretty-printed; `validated_manifest` is the trustworthy
handoff reference for T-039.

The offline replay was:

```powershell
uv run --project services/ml igra-ingest resume `
  --run-key 5ae72afe-e71e-4c32-ade8-cd57426533e8
```

It performed no live transport, verified the artifact chain, and returned the
same outcome and manifest identity. This is the command to use for safe local
inspection or recovery of an interrupted offline stage. New fresh runs use the
explicit `source-snapshot-reference.json` source-stage reference; the old
extensionless `snapshot` reference is intentionally unsupported and old runs
must be re-collected.

Prior local verification passed Ruff and the full ML suite (293 tests). The
current JSON presentation change also passed its formatter, focused Ruff check,
and three focused CLI tests. These local checks use fixtures/fake transport;
the owner commands above are the recorded real NOAA acceptance.
### Storage scaling

The retained GFS run is dominated by derived global arrays, not SQLite rows:
raw payloads are about 1.09 GiB, active parser v5 artifacts about 10.92 GiB,
and active normalizer v7 artifacts about 12.01 GiB; spatial/validator/features
total only about 18 MiB. With superseded history, one retained day is about
47 GiB, so naive 100-day retention is not viable.

The compact design is locked:

- Decode and validate the full GRIB message in memory, preserving bitmap and
  sentinel semantics; persist only the deterministic rectangular crop required
  by configured site footprints.
- The current seven sites need 77 unique nodes inside an 8 × 24 (192-cell)
  crop, versus the provider's 1440 × 721 global grid. Derive this crop from the
  immutable site snapshot and sampling policy; do not hard-code it.
- A rectangle, rather than sparse nodes, preserves current bilinear/radius
  sampling. Preserve float64 values, packed masks, global-to-local node
  translation, and `gfs_0p25_global` SQLite identity.
- Bind site-config SHA, sampling-policy SHA, and crop-selection version into
  acquisition/artifact identity. Changed footprint inputs may not silently
  reuse a compact or persisted graph.
- Keep raw source evidence and existing completed artifacts. Do not introduce
  raw pruning, new dependencies, or SQLite columns.

Given identical raw GRIB, site snapshot, and policy, selected-node canonical
and SQLite business values must be unchanged. Only derived on-disk representation
and repeated verification work may change.

## Commands and safety

Use `uv run --project services/ml ...` for ML commands. Do not make a live
network request unless the current phase explicitly calls for the owner-
authorized bounded fresh operation. Resume must not construct or call a source
transport. Do not mark S09, S10, or T-018 complete without the documented
operational evidence.
