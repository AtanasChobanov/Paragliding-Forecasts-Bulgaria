# T-018/S08 — Generic persistence and GFS end-to-end walking skeleton

## Status and authority

This is the owner-reviewed implementation plan for the corrective checkpoint
immediately before S08 and for S08 itself. It was prepared on 2026-09-10 after
reviewing the current schema, S01--S07 contracts, the XCContest persistence and
orchestration patterns, and the complete retained GFS run
`403c5135-8ced-4b54-a999-1c27e7ec78a3`.

The choices marked **accepted** below are implementation requirements, not open
design prompts. A future implementation agent should translate them into code
and stop for owner review only if new evidence makes one of them impossible,
unsafe, or internally inconsistent.

This plan does not authorize commits by itself. Preserve the user-owned,
unstaged `docs/T-018-S07-implementaion-plan.md`; do not stage, rewrite, or include
it in any S08 commit.

Durable decisions are recorded in DEC-045 and DEC-046 in `docs/decisions.md`.
Where they conflict with DEC-040 or DEC-042's former unsupported status for
mixed-layer LCL, buoyancy flux, or convective velocity scale, DEC-045
supersedes only that narrow status after the input audit described here.

## Required outcome

Deliver one reproducible GFS pipeline:

```text
collect
  -> parse/decode
  -> normalize, including GFS interval resolution
  -> spatial sample
  -> validate
  -> build hourly and daily features
  -> persist atomically to migrated SQLite
```

It must be runnable as individual stage commands and through:

```text
weather-ingest fresh
weather-ingest resume --run-key <uuid>
```

The final boundary must satisfy all of the following:

- Python owns DML only and never creates or migrates schema.
- Drizzle migrations remain the only SQLite DDL owner.
- One database transaction owns the complete run/product/time/sample/profile/
  convection/interval/daily-feature/provenance graph.
- A successful commit contains a terminal `succeeded` run and the complete
  expected graph; a rollback leaves no partial succeeded run.
- Exact replay revalidates the immutable inputs and persisted graph, performs
  no database mutation, and reports a no-op.
- A natural-key collision with a different immutable payload is a conflict and
  never overwrites or enriches the existing fact in place.
- Missing one supported value does not discard unrelated valid values.
- A valid physical zero is stored as zero, never as missing.
- `resume` is offline by construction and performs zero source requests.
- Existing raw/interim artifacts can restore the database write after the
  database is lost, without downloading GFS again.

## Verified starting point

### Repository and database

- Branch: `feature/T-018-weather-ingestion`.
- T-018 remains `In Progress`; S01--S07 are implemented.
- Local Drizzle migrations are applied through
  `20260909165706_remove_s07_inversion_metrics`.
- The configured local database has zero rows in all runtime weather tables, so
  forward schema correction migrations do not require weather-row conversion.
- S07 writes immutable hourly/daily feature artifacts but no SQLite rows.
- `weather-build-features --run-key <uuid>` is already offline-only.
- Current relevant versions are collector `/5`, parser `/4`, normalizer `/4`,
  spatial `/3`, validator `/4`, feature builder `/1`, feature contract `/2`,
  and feature policy v1. The corrective checkpoint must version every changed
  immutable boundary instead of rewriting old artifacts.

### Real-run evidence

The run `403c5135-8ced-4b54-a999-1c27e7ec78a3` was collected on 2026-09-10
from `gfs.20260910/00/atmos`, but its target Sofia local day is 2026-09-11.
It contains eleven 10:00--20:00 local valid instants for seven sites, 77 hourly
snapshots, seven daily snapshots, and approximately 1.17 GB of retained raw
evidence.

The current quality report has 1,596 values: 1,001 `real`, 441 `derived`, and
154 `missing`. The missing values are:

- 77 hourly GFS provider-cloud-base values;
- 21 daily provider-cloud-base mean/min/max values;
- 42 daily precipitation/radiation/heat-flux values invalidated by unresolved
  accumulated/average interval windows;
- 14 lower-layer omega mean/min values that cannot bracket 0 m AGL.

The GFS run proves that valid zero is already represented correctly. For
example, `precipitation_amount_mm` has `canonical_value: 0.0` and
`quality_state: real`. The daily precipitation result is currently null because
the interval identity is unresolved, not because zero is treated as missing.

### Blocking schema findings

Before persistence, the schema requires a new forward migration because:

1. `weather_field_provenance` cannot store the feature artifacts'
   machine-readable `missing_reason`.
2. Daily and daily-layer provenance uniqueness omits `statistic_type`, so
   mean/min/max provenance for one physical field collides.
3. The accepted mixed-layer LCL, PBL-minus-LCL, buoyancy-flux, and convective
   velocity features need typed hourly and daily destinations.
4. Exact persistence replay needs a typed link from the run to the effective
   feature boundary and persistence input fingerprint rather than an
   unstructured `notes` convention.

Never edit an applied migration. Generate and review one or more new
forward-only migrations.

## Locked semantic decisions

### Valid zero, missing, unsupported, and invalid

Apply this policy at contracts, artifacts, persistence, and tests:

| Situation                                                       | Stored numeric value      | Quality                      | Run effect                                         |
| --------------------------------------------------------------- | ------------------------- | ---------------------------- | -------------------------------------------------- |
| Source or derivation validly reports no phenomenon              | numeric `0.0`             | `real` or `derived`          | continue                                           |
| Active feature is supported but unavailable for this sample/run | `NULL`                    | `missing`                    | persist other valid fields                         |
| Active feature cannot be supplied by this source contract       | `NULL`                    | `unsupported`                | persist other valid fields                         |
| Native bitmap/sentinel says missing                             | `NULL`                    | `sentinel_missing`           | persist other valid fields when validation permits |
| Payload or invariant is invalid                                 | no successful fact        | `invalid_payload`/quarantine | block persistence                                  |
| Metric is not in the active contract                            | no field/value/provenance | none                         | do not fetch or persist it                         |

Examples:

- no forecast precipitation is `0.0 mm`, not null;
- CAPE `0.0 J/kg` is valid;
- calm wind speed is `0.0 m/s`, while direction may be null because direction
  is physically undefined;
- GFS provider cloud base is null/`unsupported` with
  `source_field_unavailable`, not ordinary intermittent missingness;
- a missing accumulation endpoint is null/`missing`, never inferred as zero;
- a formula-domain result that is physically defined as zero must remain zero.

Every null active feature requires a machine-readable reason. Available numeric
values must not carry a missing reason.

### GUST is outside the active contract

Remove `gust_surface` from the default GFS selector profile. Do not request,
download, parse, normalize, sample, persist, or feature-build GUST in this
slice. Remove the current `source_unsupported_selectors = gust_surface`
artifact outcome by versioning the collector/parser/normalizer source boundary.
Do not delete old immutable GFS artifacts.

### GFS interval normalization

The real inventories prove that GFS interval products use forecast-step reset
blocks. For the reviewed run, APCP is published as:

```text
30-31 hour acc
30-32 hour acc
...
30-36 hour acc
36-37 hour acc
36-38 hour acc
...
36-41 hour acc
```

DSWRF, SHTFL, and LHTFL use the same step windows as interval averages. The
generic feature builder must not consume these overlapping source windows as
canonical adjacent intervals.

Implement source-specific interval resolution in the GFS normalization stage,
after native interval metadata is parsed and before canonical site sampling.
The result must be exact, non-overlapping canonical intervals.

For accumulated precipitation `A[a,b]`:

```text
P[t0,t1] = A[a,t1] - A[a,t0]
```

Both endpoints must have the same source/product/field/component/grid/reset
identity. At the first interval after a reset, where `a == t0`, the source
accumulation is already the interval amount.

For a source interval average `Fbar[a,b]`:

```text
F[t0,t1] =
    (Fbar[a,t1] * seconds(t1-a)
     - Fbar[a,t0] * seconds(t0-a))
    / seconds(t1-t0)
```

At a reset boundary, the first source average is already the interval average.

Requirements:

- derive resets from parsed native step metadata; do not assume a globally
  hard-coded six-hour reset;
- require a compatible predecessor within the same reset block;
- preserve both contributing native message references and raw artifact keys;
- record a new normalization method/version for resolved interval values;
- reject ambiguous duplicate source messages rather than choosing by order;
- reject decreasing precipitation accumulation beyond a documented GRIB
  quantization tolerance;
- permit only a tiny negative precipitation delta within that tolerance to be
  normalized to `0.0`, with explicit derivation provenance;
- retain signed sensible and latent heat flux values; negative heat flux is
  physically valid and must not be clamped;
- verify all derived values are finite;
- retain old normalized artifacts unchanged and publish a new fingerprinted
  normalized boundary.

The 10:00--20:00 Sofia daily window consumes exactly ten canonical intervals:

```text
[10:00,11:00), ... , [19:00,20:00)
```

The preceding `[09:00,10:00)` source value may be required as a differencing
baseline but must not contribute to daily totals or means. A missing compatible
baseline makes only the affected resolved interval/feature missing. The feature
builder continues to fail a daily interval feature for gaps, overlaps,
duplicates, non-hourly input where hourly maximum is required, or incomplete
coverage.

### Provider cloud base and derived mixed-layer LCL

Keep provider and project-derived identities separate:

- `provider_cloud_base_agl_m` remains a direct provider field;
- GFS emits it as null/`unsupported` because the reviewed product has no
  accepted cloud-base parameter;
- never map GFS `HGT:cloud ceiling` to cloud base;
- S09 may populate provider cloud base from ERA5 `cloud_base_height` after its
  source-specific validation;
- add `mixed_layer_lcl_agl_m` as a separate project-derived hourly feature;
- add `pbl_minus_lcl_m = provider_pbl_agl_m - mixed_layer_lcl_agl_m` as a
  signed hourly reachability feature.

The mixed-layer LCL is a physical condensation estimate, not proof that a
cloud exists. It is a transparent T-022 baseline/input. ERA5 cloud base may
later be used as a reanalysis/weak training label, but not as a GFS predictor in
the same example. A higher-quality observational label source can calibrate the
model later without changing these feature identities.

#### Mixed parcel

For each site/valid instant:

1. Use surface pressure `p_s`, direct 2 m temperature and direct 2 m specific
   humidity as the lower anchor.
2. Define the mixed layer as `[p_s - 10,000 Pa, p_s]`.
3. Require accepted above-terrain temperature and specific-humidity profile
   evidence to bracket the complete pressure layer; no extrapolation.
4. At an exact missing boundary, interpolate temperature and humidity linearly
   in `ln(p)` between bracketing accepted pressure levels.
5. Convert temperature at each knot to potential temperature with the fixed
   project constants.
6. Calculate pressure-weighted trapezoidal means of potential temperature and
   specific humidity over the full 100 hPa layer.
7. Reconstruct the representative parcel temperature at `p_s`, derive its
   liquid-water relative humidity from `q` and `p_s`, and calculate LCL height
   from that parcel.

Implement the liquid-water exact LCL expression from Romps (2017), equation
22, using `scipy.special.lambertw` on the required real branch. Add SciPy as an
owned ML dependency with `uv add --project services/ml`; commit the resulting
`uv.lock`. Do not add MetPy solely for this formula. Pin all constants and the
formula identity in one module and version it, for example
`romps-liquid-lcl/1`.

Reject or mark only this feature missing for non-finite inputs, nonphysical
pressure/temperature/humidity, incomplete 100 hPa coverage, a non-real solver
result outside the numerical tolerance, or a negative/non-finite LCL. A
saturated parcel may validly produce `0.0 m AGL`.

Daily outputs are strict reductions over the eleven hourly instants:

- `mixed_layer_lcl_agl_mean_m`;
- `mixed_layer_lcl_agl_min_m`;
- `mixed_layer_lcl_agl_max_m`;
- `pbl_minus_lcl_mean_m`;
- `pbl_minus_lcl_max_m`.

If GFS PBL is missing, MLLCL may remain available while PBL-minus-LCL is
missing. Do not collapse either into provider cloud base.

Scientific references:

- Romps, “Exact Expression for the Lifting Condensation Level,” DOI
  `10.1175/JAS-D-17-0102.1`;
- NOAA/NWS parameter guidance describing a mean lowest-100-hPa parcel for
  MLLCL and its use as a cloud-base estimate;
- ECMWF ERA5 `cloud_base_height` documentation for the later S09 provider
  field.

### Thermal strength from surface buoyancy flux and Deardorff velocity

Add two separate hourly project-derived fields:

- `surface_buoyancy_flux_kinematic_m2_s3`, signed;
- `convective_velocity_scale_m_s`, non-negative.

Do not rename VVEL/omega, GUST, TKE, friction velocity, CAPE, or heat flux as
thermal strength. The accepted thermal-strength proxy is the Deardorff
convective velocity scale `w*` derived from validated buoyancy flux and PBL
depth.

#### Inputs and temporal alignment

Use inputs already present in the reviewed GFS source contract:

- surface pressure;
- 2 m temperature;
- 2 m specific humidity;
- pressure-level temperature, specific humidity, pressure, and height;
- provider PBL height `HPBL`;
- resolved one-hour upward-positive SHTFL and LHTFL.

No new GFS field request is needed. The interval correction is a prerequisite.
For each exact one-hour interval, pair the resolved flux with the atmospheric
state at the interval end. Hourly feature snapshots may expose a trailing-hour
thermal estimate. Daily thermal aggregates use only the ten intervals fully
inside `[10:00,20:00)` and their end states; the preceding 09:00--10:00 forcing
does not contribute.

#### Formula contract

Use centrally declared constants with units and tests, including `g`, `R_d`,
`c_p`, `L_v`, reference pressure `p_0`, and `kappa = R_d/c_p`.

Near-surface virtual temperature and density:

```text
T_v = T * (1 + 0.61*q)
rho = p / (R_d*T_v)
```

Surface virtual-potential-temperature flux approximation:

```text
w_theta_v = (p_0/p)^kappa * (
    (1 + 0.61*q) * H/(rho*c_p)
    + 0.61*T * LE/(rho*L_v)
)
```

Compute a height-weighted mixed-layer mean virtual potential temperature from
the accepted surface/profile T/q evidence over `[surface, HPBL]`, with boundary
interpolation and no extrapolation. Require HPBL to be positive and fully
bracketed by accepted profile evidence.

Signed surface buoyancy flux:

```text
B_0 = g / mean_theta_v * w_theta_v
```

Positive-part Deardorff convective velocity scale:

```text
w_star = cbrt(max(B_0, 0) * HPBL)
```

This definition deliberately stores the signed `B_0` separately. If valid
surface forcing is neutral or negative, `w_star` is a meaningful `0.0 m/s`, not
missing. Missing/invalid inputs make the affected derived fields null with an
exact reason. `w*` is a convective scaling velocity and must not be presented
as a guaranteed paraglider climb rate.

Version the methods independently, for example:

- `surface-virtual-potential-temperature-flux/1`;
- `surface-buoyancy-flux/1`;
- `deardorff-convective-velocity/1`.

Daily exact-window outputs:

- `surface_buoyancy_flux_kinematic_mean_m2_s3`;
- `surface_buoyancy_flux_kinematic_max_m2_s3`;
- `convective_velocity_scale_mean_m_s`;
- `convective_velocity_scale_max_m_s`.

The buoyancy-flux values remain signed. The convective-velocity values are
non-negative. Use duration-weighted mean for interval-based means and maximum
over the ten resolved intervals for maxima.

Primary physical reference: the Deardorff scale
`w* = (B_0*z_i)^(1/3)`, with `z_i` represented by accepted provider PBL height.

### Lower-layer omega

Pressure vertical velocity is not a project-brief requirement and is not the
thermal-strength feature. Do not fabricate a 0 m omega anchor and do not derive
lower omega from the current surface divergence alone.

Evolve the feature-policy shape so applicability is explicit per layer:

- 0--1500 m AGL: lapse, RH, q, U/V, speed, direction, and shear; no omega
  feature keys;
- 1500--3000 m AGL: the same fields plus omega mean/min.

Do not drop the shared `vertical_velocity_*` columns from
`weather_daily_feature_profile_layers`, because the upper-layer row uses them.
The lower row keeps these physical columns null, but no lower omega feature or
missing-provenance expectation is emitted or exported to ML.

Use a feature-policy schema in which each layer declares its own field list,
instead of one global profile-field list applied to every layer. Old v1 policy
and v2 artifacts remain readable; new builds use policy v2, feature contract
`weather-feature-contract/3`, and a bumped feature-builder version.

## Corrective checkpoint before SQLite persistence

Implement and verify this checkpoint before writing the persistence adapter:

1. Remove GUST from the GFS selector profile and version affected source
   boundaries.
2. Resolve GFS accumulated/average reset windows into canonical one-hour
   intervals in normalization.
3. Extend tests with the exact retained f031--f041 interval pattern and reset at
   f036/f037.
4. Add mixed-layer parcel and exact LCL helpers and tests.
5. Add PBL-minus-LCL.
6. Add buoyancy-flux and Deardorff `w*` helpers and tests.
7. Evolve feature policy to layer-specific applicability and omit lower omega.
8. Extend hourly/daily artifact contracts and builder outputs.
9. Emit GFS provider cloudbase as `unsupported/source_field_unavailable`.
10. Publish new immutable normalized/validated/feature boundaries for the real
    retained run entirely offline.
11. Confirm the corrected quality report has no interval-based missing values
    when all required native endpoints exist, no lower-omega missing entries,
    and explicit unsupported provider cloudbase.

The corrective rebuild must not overwrite or delete the existing S04--S07
artifacts. Use state-ledger supersession for each changed derived stage.

## Database schema correction

Generate forward-only Drizzle migration(s) after updating `schema.ts`. Apply
them to temporary test databases first. Application to the configured local
database remains an explicit reviewed implementation step; verify it is still
free of runtime weather rows immediately before any lossy table rebuild.

### `weather_ingestion_runs`

Add typed persistence linkage:

- `feature_manifest_path TEXT NOT NULL` for succeeded rows;
- `feature_manifest_sha256 TEXT NOT NULL` for succeeded rows;
- `persistence_input_sha256 TEXT NOT NULL` for succeeded rows.

If SQLite migration mechanics require them to be nullable during `running`,
enforce lifecycle pairing:

- all three null while a new row is `running`;
- all three non-null for `succeeded`;
- a `failed` metadata row, if ever added in a later design, may leave them null.

Paths must be safe repository-relative `data/interim/...` paths and hashes must
be lowercase SHA-256. Do not encode this typed identity in `notes`.

### `weather_point_samples`

Add nullable typed hourly derived columns:

- `mixed_layer_lcl_agl_m` with non-negative check;
- `pbl_minus_lcl_m`, signed;
- `surface_buoyancy_flux_kinematic_m2_s3`, signed;
- `convective_velocity_scale_m_s` with non-negative check.

Provider PBL/cloudbase columns remain unchanged and semantically distinct.

### `weather_daily_feature_snapshots`

Add nullable typed columns:

- `mixed_layer_lcl_agl_mean_m`;
- `mixed_layer_lcl_agl_min_m`;
- `mixed_layer_lcl_agl_max_m`;
- `pbl_minus_lcl_mean_m`;
- `pbl_minus_lcl_max_m`;
- `surface_buoyancy_flux_kinematic_mean_m2_s3`;
- `surface_buoyancy_flux_kinematic_max_m2_s3`;
- `convective_velocity_scale_mean_m_s`;
- `convective_velocity_scale_max_m_s`.

Add order/non-negative checks for LCL and convective velocity. Do not constrain
PBL-minus-LCL or buoyancy flux to non-negative values.

### `weather_field_provenance`

Add nullable `missing_reason_code TEXT` and enforce:

- `missing`, `sentinel_missing`, `unsupported`, and any retained
  `invalid_payload` projection require a non-empty lower-snake-case reason;
- `real` and `derived` require `missing_reason_code IS NULL`;
- absent states require null canonical/native numeric value as already
  applicable;
- available states must have the corresponding owner value non-null, enforced
  by the persistence mapper/cross-row validator where a generic SQL check
  cannot address every owner column.

Drop and recreate only the daily and daily-layer partial unique indexes as:

```text
(daily_feature_snapshot_id, field_code, field_variant, statistic_type)
(daily_feature_profile_layer_id, field_code, field_variant, statistic_type)
```

Require non-null `statistic_type` for daily and daily-layer owners. Keep the
existing natural identities for sample, profile, convection, and interval
owners unless tests prove a collision.

### Schema and feature parity

Replace duplicated hard-coded test lists with a dynamic parity test that loads
the packaged active feature policy and proves:

- every hourly feature key maps to exactly one point/convection destination or
  an explicitly artifact-only key;
- every daily key maps to exactly one daily column;
- every layer-specific key maps to exactly one profile-layer column;
- no active persistence column lacks a policy key, except structural IDs and
  explicitly documented source facts;
- field code, variant, statistic, unit, nullability, and signed/non-negative
  semantics agree;
- provider and derived cloudbase identities never map to the same column.

Update database tests, snapshots, physical schema diagram, and owning database
README. Run fresh migration, migration idempotence, `STRICT`, foreign-key,
index, lifecycle, missing-reason, and numeric-constraint tests.

## Python writable non-migrating SQLite adapter

### Modules and entry point

Add a source-neutral weather persistence package under the existing weather
ingestion boundary, with responsibilities separated approximately as:

```text
ingestion/weather/persistence.py          prepare, map, transact, revalidate
ingestion/weather/persistence_cli.py      weather-persist CLI and exit codes
ingestion/weather/persistence_models.py   prepared graph and receipt contracts
ingestion/weather/pipeline.py             fresh/resume orchestration
ingestion/weather/pipeline_cli.py         weather-ingest CLI
```

Exact filenames may follow repository conventions, but do not place GFS source
logic inside generic persistence. Reuse the existing
`paragliding_forecasts_ml.storage.sqlite` writable connection boundary. Add
scripts:

```text
weather-persist
weather-ingest
```

The adapter must open an existing configured SQLite file, enable/verify foreign
keys through the shared connection helper, verify required migrated tables and
columns, and fail with a configuration/schema error when migration is missing.
It must never run DDL, invoke Drizzle, or silently create a blank database.

### Preparation before transaction

Perform expensive and filesystem-only work before acquiring the write lock:

1. Validate lowercase UUID v4 run key and safe repository-relative paths.
2. Load and hash-verify the complete state ledger.
3. Require the latest effective `validated/complete` and
   `features_built/complete` boundaries; quarantine blocks persistence.
4. Load raw, normalized, sampled, validation, hourly-feature, daily-feature,
   quality-report, policy, and stage manifests through strict contracts.
5. Verify every referenced artifact hash, run key, source/product identity,
   target date, component version, feature contract, and input fingerprint.
6. Reconcile counters and require unique sample/daily/layer identities.
7. Build the complete deterministic row graph in memory.
8. Map every feature key through one explicit registry to a typed DB column and
   provenance identity; unknown or duplicate mappings fail before SQL.
9. Calculate `persistence_input_sha256` from canonical serialized immutable
   input identities, including effective manifest hashes, policy hash, mapping
   registry version, and complete pipeline version tuple.
10. Do not mutate artifacts or SQLite during preparation.

Large raw GRIB payloads must not be loaded for persistence. Verify their hashes
through manifests as required by the existing boundary, then persist from the
compact accepted/feature artifacts.

### Natural keys and reuse rules

Use the accepted natural keys:

| Entity          | Natural key                                                                   |
| --------------- | ----------------------------------------------------------------------------- |
| source          | `code`                                                                        |
| product run     | `(source_id, source_product_key)`                                             |
| valid time      | `(product_run_id, valid_at_utc)`                                              |
| grid            | `(source_id, grid_key)`                                                       |
| grid point      | `(grid_id, latitude_deg, longitude_deg)`                                      |
| point footprint | `(site_id, grid_id, method, method_version)` plus configured radius semantics |
| footprint node  | `(footprint_id, grid_point_id)`                                               |
| ingestion run   | `run_key`                                                                     |
| point sample    | `(ingestion_run_id, point_footprint_id, product_valid_time_id)`               |
| profile level   | `(weather_point_sample_id, pressure_pa)`                                      |
| convection      | existing parcel/layer/method/version partial identity                         |
| interval        | `(sample_id, field_code, component, statistic_type, start, end)`              |
| daily snapshot  | `(ingestion_run_id, point_footprint_id, feature_contract_version)`            |
| daily input     | `(daily_snapshot_id, point_sample_id)`                                        |
| daily layer     | `(daily_snapshot_id, base_agl_m, top_agl_m)`                                  |
| provenance      | owner plus field code, variant, and the accepted statistic identity           |

Shared registry/configuration rows are reusable only when their complete
immutable payload agrees. A matching natural key with different provider,
geometry, method, version, elevation, time, or permission metadata is a
conflict, not an update.

Persistence must not create weather sources, sites, site sampling configs, or
other reviewed configuration. Their absence or mismatch fails preflight.
Product runs, valid times, grids, grid points, footprints, and footprint nodes
may be inserted as run evidence or reused after strict equality checks,
according to their schema ownership.

S06 below-terrain excluded pressure levels remain artifact-only at the
relational persistence boundary: persist accepted profile rows only and do not
invent null profile-level rows. The versioned missing-evidence contract records
the excluded site, valid time, pressure, terrain diagnostics, and affected
required profile fields, while the receipt continues to disclose that no
one-row-per-excluded-level SQLite representation exists.

### Single transaction

Use one explicit `BEGIN IMMEDIATE` transaction. Within it:

1. Recheck schema and reviewed source/configuration rows.
2. Resolve or insert strictly equivalent shared product/grid/footprint rows.
3. Handle an existing `run_key` through the exact replay branch below.
4. Insert the ingestion run as `running`, with zero/finally reconciled counters
   according to one documented order.
5. Insert/reuse product valid times.
6. Insert point samples.
7. Insert profile levels and their provenance.
8. Insert convection measurements and their provenance.
9. Insert resolved canonical interval measurements and their provenance.
10. Insert hourly point-field provenance, including explicit unsupported GFS
    provider cloudbase.
11. Insert daily snapshots and all typed daily values.
12. Insert every daily-to-hourly input join.
13. Insert both daily profile-layer rows, with omega populated only for the
    upper layer.
14. Insert daily and layer provenance with exact statistic identities and
    missing reason codes.
15. Verify expected row counts, owner/value/provenance coverage, foreign-key
    relationships, source/product/date alignment, the exact eleven daily input
    samples, and exact-window interval identities.
16. Set final counters, effective feature manifest/path/hash,
    `persistence_input_sha256`, completion time, and status `succeeded`.
17. Commit.

Any exception before commit rolls back the entire graph. No child row, running
run, or succeeded run from that attempt may remain. Record the failure outside
the transaction as immutable persistence failure evidence/state, not as a
partial successful database graph.

### Persistence receipt

Write or reuse a fingerprinted persistence boundary under the run's interim
artifact directory. Its strict receipt/report must include:

- run key and source/product/target date;
- database identity without credentials or absolute secret-bearing URLs;
- effective feature manifest path/hash;
- persistence input fingerprint;
- pipeline and persistence versions;
- disposition: `inserted`, `revalidated_no_op`, or recovered committed write;
- inserted/reused counts for every weather table;
- deterministic persisted graph fingerprint;
- missing/unsupported counts and reason summary;
- below-terrain artifact-only limitation;
- transaction completion timestamp.

Prepare receipt content before commit where possible, but publish the immutable
receipt only after commit. Handle a crash between commit and receipt as
described below.

## Replay, enrichment, revision, and conflict policy

### Exact replay

When `run_key` already exists:

1. Compare source/product, target date, purpose, method, permissions, raw
   manifest, effective feature manifest, pipeline tuple, and persistence input
   fingerprint.
2. Reconstruct and compare the complete expected row graph, including nulls,
   provenance, input joins, and counts.
3. If semantically identical, issue no INSERT/UPDATE/DELETE, roll back or close
   the read transaction without mutation, and return
   `revalidated_no_op`.
4. Do not alter timestamps, counters, notes, receipt, or state events merely to
   record that a no-op command ran.
5. If any immutable field differs, fail with a conflict report and no writes.

Do not use blind `INSERT OR IGNORE`, `INSERT OR REPLACE`, or broad UPSERT logic.

### Enrichment

Null-to-value change under the same immutable weather natural key is not an
automatic enrichment in S08. Example: replacing unsupported GFS provider
cloudbase with a number under the same run/sample identity is a conflict.

New information must use one of:

- a distinct provider product/source revision;
- a new ingestion run representing an explicitly requested acquisition;
- a new feature-contract/derivation version built offline from retained raw
  evidence, persisted under a new replay run identity.

Do not mutate a persisted terminal run. This is intentionally stricter than
the mutable canonical-flight reconciliation policy.

### Formula revision

Changing LCL mixing depth, constants, interpolation, buoyancy-flux method, or
`w*` formula requires a new method and feature-contract version. Old artifacts
and rows remain reproducible. Never reinterpret a stored column under the same
version.

### Duplicate fresh acquisition

Define a deterministic acquisition fingerprint from source, provider product,
target local date/valid times, selector profile, requested site scope, sampling
scope, request purpose, and source-boundary versions. After fresh planning and
before payload GETs, detect a succeeded identical acquisition. Default to an
`already_succeeded` result pointing to the existing run rather than downloading
and inserting duplicates. A deliberately new acquisition/revision must be an
explicit CLI action and a new run; it never overwrites the prior run.

The required S08 repeat-run gate applies at minimum to exact replay of the same
run key and must prove unchanged row counts and immutable timestamps.

## State-ledger behavior and crash recovery

Update the state contract so persistence attempts can be represented without
claiming success:

- `persisted/persisted` is successful and terminal;
- `persisted/failed` is a retryable failure event with immutable failure
  evidence;
- `partial` raw collection remains terminal and cannot resume;
- an already `persisted/persisted` run may be revalidated by the persistence
  command without appending a new state event;
- derived boundaries may supersede only before successful persistence;
- changing derivations after successful persistence requires a new offline
  replay run identity.

Failure report evidence must contain no secrets and must distinguish prepare,
schema/preflight, transaction, conflict, and receipt-publication failures.

Crash case: SQLite commit succeeds but receipt/state publication does not.
On resume:

1. Find the succeeded run by `run_key`.
2. Compare its persistence fingerprint and entire graph to the immutable
   prepared input.
3. If identical, publish/reuse the deterministic receipt and append the missing
   terminal state event.
4. Report recovered committed write; do not insert again.
5. If different, report conflict and do not alter either side.

## CLI and orchestration contract

### Existing stage commands

Retain the current commands and their source/stage boundaries:

```text
gfs-collect
gfs-parse
gfs-sample
weather-validate
weather-build-features
```

Normalization may remain part of the current parser/normalizer stage command
shape; documentation must describe the actual boundary and must not advertise
a nonexistent command. Add:

```text
weather-persist --run-key <uuid>
```

It is always offline. It accepts no network flag and operates only on the
latest effective complete feature boundary.

### `weather-ingest fresh`

Provide one end-to-end command with explicit source `gfs` and the accepted
local-date/purpose/size/network options. Exact flag spelling should follow the
current GFS CLI conventions. Required behavior:

1. Resolve `DATABASE_URL` and verify migrated schema/configuration before a
   potentially expensive collection.
2. Validate local date, request purpose, permission policy, site scope, and
   byte cap.
3. Require explicit `--allow-live-network` for fresh collection.
4. Plan the GFS product and compute acquisition identity.
5. Return `already_succeeded` before payload GETs for a matching completed
   acquisition unless an explicit new-acquisition mode is requested.
6. Collect immutable raw evidence.
7. Stop with terminal partial coverage if collection is incomplete.
8. Invoke all remaining stages through the same functions used by individual
   CLIs, not subprocess parsing or duplicated business logic.
9. Persist atomically.
10. Return one structured summary containing stage evidence and final
    persistence disposition.

Do not make 1114 MiB a universal default. It was measured only for the retained
2026-09-11 local-date scope. Preserve bounded planning and require a reviewed
cap for each fresh scope.

### `weather-ingest resume --run-key <uuid>`

Resume is offline by construction:

- expose no `--allow-live-network`, URL override, retry-download, or transport
  option;
- do not instantiate or import a live transport on the resume execution path;
- verify the state hash chain and all effective artifact hashes;
- start at the first missing legal derived stage;
- reuse complete matching boundaries;
- supersede an outdated derived boundary only through the existing immutable
  supersession protocol;
- refuse a terminal partial raw run and instruct the caller to start a new
  fresh run;
- stop on quarantine;
- retry `persisted/failed` from the effective feature boundary;
- revalidate and no-op an already persisted run;
- restore an empty newly migrated database entirely from retained raw/interim
  artifacts without source requests.

Use dependency injection in tests so a fail-fast transport spy proves exactly
zero calls during every resume path, including rebuild and DB restoration.

### Exit/status behavior

Use stable structured statuses and document them. At minimum distinguish:

- success inserted;
- success revalidated no-op/already succeeded;
- quarantined or incomplete coverage requiring review/new fresh run;
- conflict;
- operational/configuration/hash/schema failure.

Follow existing CLI conventions where practical, but never collapse conflict
or quarantine into a generic successful exit.

## Integration and regression test plan

### Temporary migrated database harness

Every persistence integration test must use a unique temporary SQLite file.
Apply the real committed Drizzle migrations through the existing database
workspace migration entry point with a test-specific `DATABASE_URL`. Do not
construct tables in Python tests and do not copy schema SQL into fixtures.

The harness must verify:

- migration from a fresh file;
- a second migration run is idempotent;
- foreign keys are enabled;
- required tables/columns/indexes/checks exist;
- the Python adapter refuses an unmigrated or schema-incompatible database.

Use compact frozen/synthetic GFS artifacts for routine tests. The retained
1.17 GB live run is an ignored/manual offline acceptance fixture, not a normal
unit-test dependency.

### Interval tests

Cover:

- exact one-hour source interval;
- `30-31`, `30-32`, ..., `30-36` accumulation differencing;
- reset to `36-37`, then subsequent differences;
- duration-weighted de-averaging for DSWRF/SHTFL/LHTFL;
- predecessor missing or from another reset/product;
- duplicate/ambiguous messages;
- negative precipitation beyond tolerance;
- tiny quantization negative normalized to zero with provenance;
- valid all-zero precipitation producing daily total/max `0.0`;
- `[09:00,10:00)` used only as baseline and excluded from daily output;
- exact ten-interval flying-window coverage;
- gap, overlap, duplicate, non-hourly maximum, and DST cases.

### LCL tests

Cover analytic/reference cases from the selected Romps implementation:

- saturated parcel gives 0 m;
- warmer/drier parcel gives higher LCL;
- pressure-weighted lowest-100-hPa mixing on uneven levels;
- exact/interpolated pressure boundaries;
- below-terrain levels excluded;
- missing 2 m q/T/pressure;
- incomplete 100 hPa bracket;
- nonphysical humidity/solver result;
- deterministic values and provenance;
- provider cloudbase remains independent and unsupported for GFS;
- PBL-minus-LCL supports positive, zero, and negative values.

### Thermal-strength tests

Cover:

- dimensional/known-value test for density, virtual flux, `B_0`, and `w*`;
- positive sensible/latent forcing;
- latent contribution;
- valid zero forcing gives `B_0 = 0` and `w* = 0`;
- negative signed `B_0` gives `w* = 0`, not missing;
- negative source heat flux is retained;
- missing or unbracketed PBL/T/q/flux affects only thermal-derived fields;
- ten exact-window intervals, duration-weighted daily mean, and maximum;
- no VVEL/GUST/TKE/friction-velocity substitution;
- `w*` remains non-negative and finite.

### Contract/schema tests

Cover:

- new policy schema with layer-specific fields;
- lower layer has no omega keys or missing mask entries;
- upper layer retains omega mean/min;
- hourly/daily feature keys map exactly once to DB columns;
- provenance uniqueness distinguishes mean/min/max;
- missing reason constraints;
- GFS cloudbase null/unsupported persistence;
- valid numeric zero persistence;
- signed gap/buoyancy values and non-negative LCL/`w*` constraints.

### Persistence gate

One integration scenario must:

1. migrate a temporary database with real Drizzle migrations;
2. persist a complete deterministic GFS run graph;
3. assert expected rows and provenance in every weather table;
4. replay the same run and assert all row counts and immutable timestamps are
   unchanged;
5. alter one payload under an existing natural key, assert conflict, and prove
   no row changed;
6. inject an exception after several child inserts and prove rollback leaves no
   run graph or succeeded run;
7. inject a crash after commit/before receipt and prove resume recovers the
   receipt/state without duplicate writes;
8. preserve raw/interim artifacts, replace the database with a newly migrated
   empty file, run resume, and prove the graph is restored;
9. assert a transport spy observed zero source requests throughout resume;
10. assert missing/unsupported fields do not prevent unrelated values from
    persisting.

### Orchestration tests

Cover fresh happy path, preflight failure before collection, incomplete raw
coverage, validation quarantine, stage reuse, outdated derived-stage
supersession, persistence failure/retry, exact terminal no-op, duplicate fresh
acquisition, hash tampering, unsafe paths, and structured exit codes.

## Implementation sequence and suggested commits

Keep commits ticket-prefixed, imperative, independently reviewable, and free of
raw/local data. Before each commit inspect staged/unstaged diffs and ensure the
user-owned S07 plan is not staged.

### Commit 1 — `T-018 resolve GFS interval windows`

- remove GUST from selectors;
- version collector/parser/normalizer boundaries;
- implement accumulation differencing and average de-averaging;
- preserve multi-message provenance;
- add exact reset/tolerance/zero/window tests;
- update source-contract documentation and decision references.

### Commit 2 — `T-018 derive cloudbase and thermal features`

- add SciPy through uv and lock it;
- implement lowest-100-hPa mixed parcel and exact Romps LCL;
- add PBL-minus-LCL;
- implement signed buoyancy flux and positive-part Deardorff `w*`;
- evolve feature policy to layer-specific applicability;
- remove lower omega from active outputs while retaining upper omega;
- bump feature/artifact versions and add focused formula/contract tests.

### Commit 3 — `T-018 align weather persistence schema`

- add hourly/daily derived columns;
- add feature manifest/fingerprint run linkage;
- add provenance missing reason;
- correct daily/layer provenance uniqueness and checks;
- generate/review forward migration(s);
- update schema diagram/database README and migration/parity tests.

### Commit 4 — `T-018 persist weather runs atomically`

- add prepared graph, mapping registry, persistence receipt, and CLI;
- implement natural-key equality/conflict rules;
- implement the one `BEGIN IMMEDIATE` transaction;
- implement exact replay revalidation and rollback tests;
- add temporary real-migration integration harness.

### Commit 5 — `T-018 orchestrate GFS fresh and offline resume`

- add `weather-ingest` fresh/resume;
- add duplicate acquisition preflight;
- add persistence failure state and crash recovery;
- prove resume has no transport calls;
- add end-to-end orchestration tests and command documentation.

### Commit 6 — `T-018 verify and document Slice 8`

- rebuild the retained real run offline through corrected derived stages;
- persist it only after the configured database migration is explicitly
  reviewed/applied;
- record actual counts, quality outcomes, graph fingerprint, and no-op replay;
- run all required repository checks;
- update `docs/tasks.md` only if every S08 gate passes;
- update `docs/handoff.md` with verified results and the next S09 focus.

If implementation naturally requires smaller commits, split within these
boundaries; do not combine unrelated refactors or later S09 work.

## Required validation commands

Run focused tests continuously, then from the repository root run every
relevant available check:

```powershell
uv run --project services/ml pytest
uv run --project services/ml ruff check services/ml
uv run --project services/ml ruff format --check services/ml
npm.cmd run db:check --workspace @paragliding-forecasts/database
npm.cmd test --workspace @paragliding-forecasts/database
npm.cmd run build
npm.cmd run typecheck
npm.cmd run lint
npm.cmd run format:check
npm.cmd test
npm.cmd run test:coverage
npm.cmd run repo:check
git diff --check
```

Also run the fresh temporary-database migration/idempotence integration suite,
offline rebuild/persist/replay fixture, and transport-spy resume tests. Report
any command that cannot run; do not mark S08 complete with missing or failed
required validation.

## Definition of done for S08

S08 is complete only when:

- the corrective interval, GUST, LCL, thermal-strength, cloudbase-state, and
  lower-omega changes are implemented and versioned;
- corrected artifacts can be rebuilt offline from retained source evidence;
- schema migrations are generated, reviewed, tested from a fresh database,
  idempotent, and applied to the configured local database with owner-approved
  timing;
- the Python adapter persists the complete weather graph without DDL;
- one transaction guarantees no partial succeeded run;
- exact replay is a verified database no-op;
- conflict never overwrites;
- valid zero remains numeric and missing/unsupported reasons survive in DB;
- stage commands and end-to-end fresh/resume work as documented;
- resume restores a fresh migrated DB from artifacts with zero network calls;
- contract/schema parity is automatic rather than a copied feature list;
- focused, complete ML, database, root, migration, integration, and formatting
  checks pass;
- final diff contains no unrelated changes or raw/local artifacts;
- task status and handoff reflect only verified completion.

## Explicit non-goals and later work

- Do not implement ERA5 collection in S08; that remains S09. Preserve the
  provider-cloud-base destination and documented target strategy for S09.
- Do not train the cloudbase/XC/overdevelopment models; T022--T024 own them.
- Do not treat ERA5 cloudbase as observation-quality ground truth; it is a
  reanalysis/weak label until calibrated against observations.
- Do not add METAR/ceilometer/IGRA collection here. IGRA/sounding handling is
  T019, and observational cloudbase sourcing needs its own reviewed source
  decision if required.
- Do not add lower omega through a surface-zero assumption or continuity
  derivation.
- Do not add GUST, TKE, friction velocity, cloud ceiling, or new providers as
  substitutes for accepted feature identities.
- Do not persist prediction outputs in the weather-ingestion tables. Ownership
  of the prediction schema remains a later backlog decision.

No owner-level S08 design decision remains open after this plan. Implementation
may discover mechanical details, but any proposed change to the physics,
natural keys, immutable replay policy, transaction boundary, or offline-resume
guarantee requires explicit review and a new/superseding durable decision.
