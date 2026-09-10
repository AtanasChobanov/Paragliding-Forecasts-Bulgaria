# T-018/S07 — Versioned source-neutral weather feature builder

## Summary

S07 ще добави offline команда `weather-build-features --run-key <uuid>`, която:

- приема единствено текущ `validated/complete` S06 boundary;
- чете `accepted-samples.json`, `missing-evidence.json` и hash-verified S05 neighbourhood nodes;
- не импортира GFS/ERA5 adapter код и работи само с canonical contracts;
- произвежда immutable hourly и site/day feature snapshots;
- оставя неприети derivations като `null`, `quality_state="unsupported"`, а
  недостатъчно обезпечените accepted features като `null`,
  `quality_state="missing"`, винаги с точен machine-readable reason code;
- не пише в SQLite — persistence остава S08.

Версии:

- `weather-feature-builder/1`
- `weather-feature-contract/2`
- `weather-feature-policy/1`
- `component-wind/1`
- `agl-piecewise-linear/1`
- `agl-layer-trapezoid/1`
- `endpoint-environmental-lapse/1`

- `endpoint-bulk-vector-shear/1`
- `neighbourhood-planar-fit/1`
- `surface-parcel-day-reduction/1`
- `exact-interval-day-reduction/1`
- `sofia-flying-window/1`

Нови Python dependencies не са нужни: `numpy`, `pydantic`, `tzdata` и стандартните `zoneinfo`, `math`, `datetime` са достатъчни.

## Reviewed implementation baseline — 2026-09-09

This section supersedes every conflicting earlier draft in this file.

### Persistence shape and required pre-S08 cleanup

The local SQLite database has applied:

- `20260908181331_refactor_daily_weather_persistence`;
- `20260908202837_correct_daily_cin_aggregate`; and
- `20260908202923_restore_daily_feature_snapshot_strict`.

The persistent model is now:

```text
weather_source → weather_product_run → weather_product_valid_time
                              ↓
                     weather_ingestion_run(target_local_date)
                              ↓
weather_point_sample (one site/footprint/valid instant)
       ↓ profile / convection / interval facts
       ↘
        weather_daily_feature_snapshot (one site + local day + contract)
                    ↕ exact contributing hourly point samples
                    ↓ repeatable daily AGL profile-layer features
```

`weather_ingestion_runs` has `product_run_id`, not `source_id`; source is
the non-repeated fact on `weather_product_runs`. `weather_point_samples`
links both the ingestion run and its exact `weather_product_valid_time`.
The daily snapshot's local day is deliberately derived from the ingestion run,
not duplicated. Snapshot input membership is relational, not an SHA field:
the same immutable hourly sample can safely serve a rebuilt feature-contract
version. There is no `weather_grid_point_measurements` table: interpolation
finishes before point facts are persisted.

`weather_field_provenance` is the only source of field-level quality,
`missing`, `unsupported`, and native/derivation evidence. A daily wide row
does not duplicate a JSON missing mask or quality summary; S07 emits both as
immutable artifact projections computed from those provenance rows.

The reviewed active feature contract excludes the unaccepted project-derived
PBL, mixed-layer LCL, kinematic buoyancy flux, and Deardorff convective
velocity-scale candidates. Before S08 persistence, create one forward-only
reviewed migration that removes the five unused daily columns
`mixed_layer_lcl_agl_mean_m`, `mixed_layer_lcl_agl_max_m`,
`surface_buoyancy_flux_kinematic_mean_k_m_s`,
`convective_velocity_scale_mean_m_s`, and
`convective_velocity_scale_max_m_s`. There is no derived-PBL daily column to
remove. Remove these candidate fields from the active machine-readable
catalogue while retaining their historical rationale in decisions/reporting.
Provider PBL and provider cloud base remain direct provider facts.

The absence of daily convection and interval child tables is deliberate only
where the feature contract defines one unambiguous fixed daily reduction.
Interval facts remain hourly children and feed the typed precipitation,
radiation, and flux columns after exact-window coverage checks. Their exact
source rows remain recoverable through `weather_daily_feature_snapshot_inputs`.
Profile layers remain a daily child table because the layer bounds are a
repeatable output dimension.

Hourly storage can contain both surface and 180--0 mb AGL CAPE/CIN variants,
while the daily table has one CAPE and one CIN column. The reviewed v2 daily
contract selects the provider **surface-parcel** CAPE and its matching
surface-parcel CIN only. This is the closest available GFS parcel identity to
surface-triggered soaring convection and, unlike the 180--0 mb AGL product,
does not require the project to reinterpret what the provider's layer means.
The other variant remains hourly evidence and is never combined with the
surface values. A future decision may add separate named daily variants; it
must not change the meaning of these columns in place.

S05 retains both surface/10 m U/V and 925 hPa U/V nodes, while the daily schema
has one `neighbourhood_low_level_divergence_*` feature. The reviewed v2 daily
contract assigns that feature to **surface/10 m U/V**. It is available over
mountain sites where 925 hPa may be below terrain and is the more direct
low-level convergence signal for launch-area soaring. The 925 hPa nodes remain
immutable evidence for a future separately named isobaric-divergence feature;
the two identities are never averaged or silently substituted.

### Explicit inversion-metric removal — 2026-09-09

`inversion_strength_max_k` and `inversion_depth_at_max_m` are not active S07
features. They are not required by the project brief and must not be emitted,
calculated, catalogued, or supplied to ML. Before S08 persistence, create and
apply one reviewed forward-only migration that removes both columns and their
pair constraint from `weather_daily_feature_profile_layers`; never edit an
applied migration. Existing lapse-rate and humidity profile features retain the
required stability evidence.
### Accepted daily policy and exact persisted aggregates

`sofia-flying-window/1` is fixed to IANA `Europe/Sofia`, local
10:00--20:00 inclusive: exactly eleven expected hourly valid instants. Convert
with `ZoneInfo`; never assume a fixed UTC offset. One collection/ingestion
run is one selected provider product cycle and one target local date. Do not
split a local day into child runs and do not build a cross-run assembler.

Each feature is independently strict: its aggregate is missing if any required
hour or required interval coverage is absent. Other complete features remain
available. Persisted daily fields use only these statistics:

- 2 m temperature: mean/min/max; dew point: mean; RH: mean/max; surface and
  MSL pressure: mean;
- 10 m U/V: arithmetic means; speed: mean/max; direction derived from mean
  U/V, never from an arithmetic mean of angles;
- provider PBL: mean/max; provider cloud base: mean/min/max; TCWV: mean;
  cloud fields: the exact mean/max columns present in the schema;
- precipitation: exact-window total plus maximum validated hourly amount;
  shortwave: duration-weighted mean/max; sensible/latent flux: means;
- CAPE: maximum; canonical positive CIN magnitude: maximum; no negative-CIN
  minimum is stored;
- neighbourhood pressure gradient: mean/max; divergence: mean/min, where the
  minimum is strongest convergence;
- per AGL layer: lapse mean/max, RH and
  specific-humidity means, U/V means, speed mean/max, vector direction, shear
  mean/max, and vertical-velocity mean/min.

p90, medians, threshold hours, morning development rate, earliest-occurrence
timestamps, separate surface/925 divergence columns, and a daily JSON quality
column are deliberately not persisted in v1. They are not silently substituted
by another statistic; add them only through a reviewed future schema/contract
change.

### 2026-09-09 GFS inventory correction — blocking prerequisite

The committed ten-level assertion is not live-valid for the object selected by
the collector. The planner reads only
`gfs.tCCz.pgrb2.0p25.fFFF`. NOAA's current official f003 inventory contains
`HGT/TMP/RH/UGRD/VGRD/VVEL` at 1000/975/950/925/900/850/800/750/700 hPa, but
not at 875 hPa. The 875 hPa records are in the separate
`pgrb2b.0p25` product. Therefore the current required `875 mb` selector fails
closed during inventory planning before collection; synthetic inventories do
not prove live availability. Evidence:

- [official GFS 0.25-degree pgrb2 f003 inventory](https://www.nco.ncep.noaa.gov/pmb/products/gfs/gfs.t00z.pgrb2.0p25.f003.shtml);
- [official GFS 0.25-degree pgrb2b f003 inventory](https://www.nco.ncep.noaa.gov/pmb/products/gfs/gfs.t00z.pgrb2b.0p25.f003.shtml).

The 700 hPa ceiling is also not sufficient to promise a 3000 m AGL upper-layer
boundary at the highest reviewed sites: pressure surfaces are MSL, while the
target boundary is site elevation plus 3000 m. No fixed pressure maps to a
fixed height, so the retained band must be demonstrated to bracket 3000 m AGL
over all reviewed site elevations and representative GFS conditions.

Before S07 implementation is accepted, supersede the affected part of DEC-040
with one reviewed source contract:

1. Reviewed target: remain on the single common `pgrb2.0p25` object, remove
   875 hPa, and use
   `1000/975/950/925/900/850/800/750/700/650/600/550/500 hPa`. Then prove with
   real inventories and parsed geopotential heights that every site can bracket
   1500 and 3000 m AGL whenever physically covered. The 500 hPa top is a
   conservative bracketing level, not a new pressure-band daily feature.
2. Alternative: extend raw planning/manifests/parser identity to combine
   `pgrb2` and `pgrb2b` within each valid instant if 875 hPa has a demonstrated
   feature value worth the extra object/provenance complexity. This still needs
   higher levels for elevated-site 3000 m AGL coverage.

The same DEC-040 supersession must narrow its statement that arithmetic-mean
U/V precede both daily speed and direction. Mean U/V precede **direction**;
`wind_speed_*_mean_m_s` is the arithmetic/time-and-height mean of scalar
`hypot(u,v)`, while the separately stored U/V preserve the resultant vector.
Using `hypot(mean(u),mean(v))` as mean speed would systematically cancel
directional variability and duplicate information already recoverable from the
stored component means.

Whichever option is accepted must update one shared pressure-band definition
used consistently by collector selectors, numeric GRIB profiles, normalizer,
spatial fixtures, source validation policy, and tests. S05's generic
`pressure_pa` profile contract already carries arbitrary positive pressure
levels, so no new sampling table or source-specific S07 path is required. A
level below reviewed site or model terrain remains an explicit exclusion and
cannot bracket interpolation.

The daily layer schema also contains `specific_humidity_mean_kg_per_kg`, but
the current GFS selector/profile does not collect `SPFH`. NOAA publishes SPFH
both at 2 m AGL and on every reviewed pressure level in the common product.
Add both forms through collector/parser/normalizer/sampler/validator. The 2 m
value is the required lower-layer anchor; pressure-level SPFH alone cannot
represent the full lower AGL layer without forbidden downward extrapolation.
Add a typed `specific_humidity_2m_kg_per_kg` hourly point field through the same
forward schema cleanup migration and preserve its provenance. Do not derive it
from T/RH/pressure for GFS while a direct provider field exists. ERA5 has no
direct near-surface RH/q archive field, so its future S09 normalizer uses the
separately versioned official ECMWF derivation specified below.

The retained direct sensible/latent daily means also require GFS `SHTFL` and
`LHTFL` interval-average selectors, numeric profile entries, canonical interval
rows, and a pinned upward-positive sign check. These are direct surface-flux
features, not the removed kinematic buoyancy-flux derivation. If current-product
interval/sign identity is not proved, only those two daily fields remain
missing; no fallback is calculated.

The current accepted GFS mapping has no provider cloud-base field. The common
GFS inventory's `cloud ceiling` HGT must not be relabelled as cloud base: the
product identity and physical meaning differ. Therefore the three daily
provider-cloud-base aggregates are explicit source-unavailable/missing for GFS
unless a future source review accepts a real cloud-base parameter and its
MSL-to-AGL normalization. ERA5's separately identified nullable cloud-base
field may populate them after normal validation.

Pressure levels are coordinates/grains, not new canonical weather fields.
Do not add one catalogue field per pressure level. The T-017 catalogue keeps
generic field identities such as `air_temperature_k`,
`relative_humidity_percent`, `specific_humidity_kg_per_kg`, wind components,
vertical velocity, and geopotential height; `pressure_pa` carries the level.
The source-specific required band belongs in the versioned GFS profile and
validation policy. The catalogue itself does need `unsupported` added to its
quality-state vocabulary so the S07 contract can satisfy the gate consistently
with the already-applied database constraint.

### Formula scope and excluded candidates

Use only the formulas locked in “Scientific formula contract” below. No
vertical extrapolation, arithmetic averaging of wind angles, node-weight
renormalization, unproved interval de-accumulation, cross-parcel CAPE/CIN
reduction, or fabricated numeric completion is allowed.

Project-derived PBL, mixed-layer LCL, kinematic buoyancy flux, and Deardorff
`w*` are intentionally outside the active v2 feature key set and outside this
formula analysis. They produce no daily columns and no placeholder feature
keys. Provider PBL/cloud base, direct sensible/latent heat flux, and pressure
vertical velocity remain distinct retained quantities. Omega/VVEL, gust, and
TKE are never relabelled as thermal strength.

### Open implementation choices, not accepted physics

1. The collection CLI still accepts repeatable `--valid-at` values. Before
   operational S07 use it needs a `--local-date`/flying-window mode that
   derives the eleven UTC instants and records the policy. This is orchestration
   work, not feature-builder work.
2. The current default collection cap is 128 MiB. It is intentionally retained
   as a fail-closed safety default until one real multi-level 11-hour inventory
   measures the required ranges. The daily command must use one explicit,
   reviewed larger cap; do not guess a new global default or parallelise
   requests merely to evade the cap.
3. Reintroducing any excluded candidate requires a future feature-contract
   version, an accepted physical method and input audit, and a forward schema
   migration. It must not repurpose an existing retained field.

## Remaining pre-builder contract work

Before the builder is considered reliable:

- correct the stale S06 nullable names:
  - `cloud_base_height_agl_m` → `provider_cloud_base_agl_m`;
  - `convective_inhibition_j_per_kg` →
    `convective_inhibition_magnitude_j_per_kg`;
- make the validation-policy loader validate every field code against the
  packaged T-017 catalogue;
- add `unsupported` to the catalogue and atmospheric feature provenance
  vocabulary, with null-value invariants equivalent to other missing states;
- apply the reviewed GFS band, 2 m/pressure-level SPFH, and surface-flux input
  changes above and supersede the incorrect DEC-040 band assertion;
- create the forward schema/catalogue cleanup described above before S08;
- record surface-parcel CAPE/CIN and surface/10 m divergence as the reviewed v2
  identities when DEC-040 is superseded;
- keep `FeatureSnapshot` v1 readable for old synthetic fixtures, while the
  real S07 batch contract v2 provides a unique `feature_key`, canonical
  field/unit plus optional variant/layer/statistic, value, quality, missing
  reason, derivation provenance, ordered missing mask, and quality summary.

S07 still performs no SQLite writes. The forward cleanup migration is a
pre-S08 contract correction: it removes unused outputs and adds the direct 2 m
specific-humidity input without changing the daily/input/layer ownership model.

## Scientific formula contract

This section is the implementation specification for every retained v2 daily
snapshot metric. It supersedes formula fragments elsewhere in this file.

### Common notation, coverage, and missingness

Let `H = {h0, ..., h10}` be the eleven distinct instantaneous valid times at
10:00--20:00 Europe/Sofia inclusive and `N = 11`. For a complete instantaneous
series:

- `mean_H(x) = (1/N) · Σ_h x_h`;
- `min_H(x) = min_h(x_h)`;
- `max_H(x) = max_h(x_h)`.

All inputs and intermediate results must be finite. A statistic is calculated
only from its exact required inputs: never skip a missing hour, replace it with
zero, carry a value forward, or use another run/source/parcel/height. Physical
zero is valid. Missing evidence is null plus a reason; invalid source evidence
is quarantined upstream. `unsupported` remains a valid quality state for a
configured source/feature mapping with no accepted method, even though the
four removed candidate feature families are absent from the active key set.

The instantaneous sample mean is deliberately an arithmetic mean because the
eleven samples are equally spaced by one hour. Interval quantities use duration
weights instead and cover the ten-hour half-open interval `[10:00, 20:00)`.

### Canonical input and source-normalization contract

| Retained input                | Canonical treatment before S07                                                                      |
| ----------------------------- | --------------------------------------------------------------------------------------------------- |
| 2 m temperature/dew point     | Direct Kelvin. Celsius sources add 273.15 upstream.                                                 |
| 2 m RH                        | Direct/accepted normalized percent in `[0,100]`; S07 does not derive it from T/Td.                  |
| Surface and MSL pressure      | Direct Pa and separate level identities.                                                            |
| 10 m and profile U/V          | Direct m/s, or accepted conversion from native speed/direction.                                     |
| 2 m/profile specific humidity | Direct kg/kg. GFS supplies `SPFH` at 2 m and pressure levels.                                       |
| Provider PBL/cloud base       | Direct provider-defined AGL metres; never replaced by a project derivation.                         |
| Cloud cover                   | Canonical instantaneous percent in `[0,100]`, retaining total/low/mid/high identity.                |
| TCWV                          | Direct/normalized kg/m².                                                                            |
| CAPE/CIN                      | Provider surface-parcel J/kg only for daily v2; retain all other parcel variants hourly.            |
| Precipitation                 | Canonical amount in mm for an explicit, validated accumulation interval.                            |
| Shortwave                     | Downward-positive interval-average W/m² after source normalization.                                 |
| Sensible/latent flux          | Upward-positive interval-average W/m² after source-specific sign/statistic normalization.           |
| Profile coordinates           | Pressure Pa, geopotential height MSL m, derived site-AGL m, and T/RH/q/U/V/omega at the same level. |

GFS supplies 2 m RH and SPFH directly. For ERA5 only, accept
`ecmwf-near-surface-humidity/1` as a source-normalization method using direct
`T2`, `Td2`, and surface pressure `p`:

- `e_s(X) = 611.21·exp[17.502·(X-273.16)/(X-32.19)]` Pa, saturation over water;
- actual vapour pressure `e = e_s(Td2)`;
- `RH2 = 100·e_s(Td2)/e_s(T2)` percent;
- `epsilon = R_d/R_v` and
  `q2 = epsilon·e / [p-(1-epsilon)·e]` kg/kg.

Use the IFS-versioned `R_d`/`R_v` constants, not an independently rounded
project constant. Require finite positive T/Td/p, `0 <= RH2 <= 100`, `p > e`,
and `0 <= q2 < 1`; do not clip invalid results. ECMWF explicitly documents
near-surface RH/q derivation from T2/Td2/surface pressure and the saturation
specific-humidity equation in its
[ERA5 near-surface humidity guidance](https://confluence.ecmwf.int/pages/viewpage.action?pageId=155343959)
and [IFS physical-process equations 7.4--7.5](https://confluence.ecmwf.int/download/attachments/19661682/IFS_CY38R1_Part4.pdf?api=v2&download=true&modificationDate=1443006083445&version=1).
This runs at the source-normalization boundary; S07 consumes only canonical
RH2/q2 and remains provider-neutral. Update the catalogue kinds/provenance
methods accordingly before S09 implementation.

For GFS cloud fields, the source selector must retain the point/`fcst` message,
not the same-parameter interval-average message that can coexist in an
inventory. A source interval average is not interchangeable with an
instantaneous hourly point field.

GFS wind components are native. If a later accepted source supplies
meteorological speed `s` and direction-from-north `theta` instead, convert with
`u = -s·sin(theta)` and `v = -s·cos(theta)`, with `theta` in radians. Conversely:

- `speed(u,v) = hypot(u,v) = sqrt(u²+v²)`;
- `direction(u,v) = (degrees(atan2(-u,-v)) + 360) mod 360`.

This is the meteorological direction **from** which the wind blows, consistent
with [ECMWF's U/V conversion guidance](https://confluence.ecmwf.int/pages/viewpage.action?pageId=242074496).
Direction alone is null when `hypot(u,v) <= 1e-6 m/s`; this is a numerical
undefined-direction tolerance, not a claim that the atmosphere is physically
calm. U, V and speed remain valid.

GFS HGT is already geopotential height. For a source such as ERA5 that supplies
geopotential `Phi` in m²/s², normalize upstream with
`z_msl = Phi / g0`, `g0 = 9.80665 m/s²`, as documented by
[ECMWF](https://confluence.ecmwf.int/pages/viewpage.action?pageId=226496389).
Then:

`z_site_agl = z_msl - reviewed_site_elevation_msl`.

Exclude a pressure level if it is below either reviewed site terrain or model
terrain. Geopotential and geometric metres are not silently mixed; the accepted
canonical vertical coordinate remains geopotential-height metres relative to
the reviewed orthometric site height, with that approximation versioned.

### Exact daily formulas for point and provider fields

| Persisted daily field(s)         | Exact formula over `H`                                            |
| -------------------------------- | ----------------------------------------------------------------- |
| 2 m temperature mean/min/max     | `mean_H(T2)`, `min_H(T2)`, `max_H(T2)`                            |
| 2 m dew-point mean               | `mean_H(Td2)`                                                     |
| 2 m RH mean/max                  | `mean_H(RH2)`, `max_H(RH2)`                                       |
| Surface-pressure mean            | `mean_H(Psfc)`                                                    |
| MSL-pressure mean                | `mean_H(Pmsl)`                                                    |
| 10 m U/V means                   | `Ubar = mean_H(u10)`, `Vbar = mean_H(v10)`                        |
| 10 m speed mean/max              | `mean_H(hypot(u10,v10))`, `max_H(hypot(u10,v10))`                 |
| 10 m mean direction              | `direction(Ubar,Vbar)`, never an angle mean                       |
| Provider PBL mean/max            | `mean_H(provider_pbl)`, `max_H(provider_pbl)`                     |
| Provider cloud-base mean/min/max | `mean_H(provider_cb)`, `min_H(provider_cb)`, `max_H(provider_cb)` |
| TCWV mean                        | `mean_H(tcwv)`                                                    |
| Total cloud mean/max             | `mean_H(tcc)`, `max_H(tcc)`                                       |
| Low cloud mean/max               | `mean_H(lcc)`, `max_H(lcc)`                                       |
| Mid cloud mean                   | `mean_H(mcc)`                                                     |
| High cloud mean                  | `mean_H(hcc)`                                                     |
| Surface CAPE max                 | `max_H(surface_parcel_cape)`                                      |
| Surface CIN-magnitude max        | `max_H(surface_parcel_cin_magnitude)`                             |

The daily speed mean is the mean scalar speed, while direction is from the
resultant mean vector. `hypot(mean(u),mean(v))` is a different statistic and is
not stored as speed mean. A missing provider cloud-base value is not converted
to zero, PBL height, or a clear-sky numeric sentinel. CAPE zero is valid. CIN
is normalized upstream as `abs(native_CIN)` only when the native convention is
proved signed non-positive; otherwise it remains missing/invalid with native
value and sign convention in provenance. NOAA distinguishes surface-based and
mean-layer CAPE as different parcel definitions in its
[CAPE glossary](https://forecast.weather.gov/glossary.php?word=CApe); v2 never
mixes them.

### Interval quantities: precipitation, radiation, and heat flux

Let validated canonical interval rows be `I_j = [a_j,b_j)` with duration
`dt_j = seconds(b_j-a_j)`. For each field/component, intervals must be unique,
contiguous, non-overlapping and together cover exactly `[10:00,20:00)`. No row
may extend outside the window. S07 does not de-accumulate cumulative products;
source-specific normalization must first emit canonical non-overlapping
amounts or interval averages with proved step/reset semantics.

The current GFS APCP selector permits tied shortest matches. Upstream selection
must resolve them by full numeric GRIB identity and canonical interval identity,
or fail closed as ambiguous. Two rows for the same field/component/interval are
duplicates and must never both contribute to a sum.

- Precipitation total: `P_total = Σ_j P_j`, where each `P_j` is an amount in mm.
- Maximum hourly precipitation: `P_hourly_max = max_j(P_j)` **only** when every
  contributing interval has `dt_j = 3600 s`; otherwise this field alone is
  missing with `hourly_amount_not_resolved` even if the exact-window total is
  available.
- Duration-weighted mean flux/radiation:
  `F_mean = Σ_j(F_j·dt_j) / Σ_j dt_j`.
- Shortwave maximum: `max_j(F_j)`. It is explicitly the maximum validated
  interval-average flux, not an unobserved instantaneous peak.
- Sensible/latent daily fields use `F_mean`; negative values are valid because
  the canonical sign is upward-positive and downward exchange may occur.

For accumulated energy `E` in J/m², the upstream interval-average conversion is
`F = (E_end-E_start)/dt` W/m² only when consecutive accumulation endpoints and
reset identity are proved. ERA5 fluxes are downward-positive, so canonical
sensible/latent flux is `-F_native`; ERA5 hourly energy accumulations divide by
3600 s. ECMWF documents both the accumulation conversion and flux convention
in its [ERA5 data documentation](https://confluence.ecmwf.int/pages/viewpage.action?pageId=192907214)
and [IFS physical-process documentation](https://www.ecmwf.int/sites/default/files/2023-06/Part-IV-Physical-Processes.pdf).
GFS `DSWRF`, `SHTFL`, and `LHTFL` are published as interval averages in W/m² in
the [official pgrb2 inventory](https://www.nco.ncep.noaa.gov/pmb/products/gfs/gfs.t00z.pgrb2.0p25.f003.shtml).
The [NCEP GRIB convention](https://www.cpc.ncep.noaa.gov/products/wesley/cdrom/table.ids.html)
treats upward heat flux as positive, but the GFS normalization must still pin
and test the current GRIB parameter/statistic/sign metadata before using
identity normalization.

### Vertical interpolation and layer means

The daily output layers remain `0--1500 m AGL` and `1500--3000 m AGL`, while
the source evidence remains on pressure levels. Linear interpolation in
geopotential height is selected because the targets are fixed height layers:

`f(z) = f1 + (f2-f1)·(z-z1)/(z2-z1)`, for `z1 <= z <= z2`.

Log-pressure interpolation is not used: it is suitable when pressure is the
target coordinate, whereas this contract has measured/normalized heights for
both bracketing levels. Linear-in-height is an explicit approximation supported
by the dense retained lower-tropospheric levels. There is no extrapolation.
Duplicate heights, missing required internal values, or an unbracketed boundary
make only the affected feature missing.

For a feature `f` with ordered knots `(z0,f0),...,(zm,fm)` including exact
interpolated boundaries `A` and `B`, its piecewise-linear height mean is exactly
the composite trapezoid:

`M_h(f;A,B) = [Σ_{k=0}^{m-1} 0.5·(f_k+f_{k+1})·(z_{k+1}-z_k)] / (B-A)`.

Use these real lower anchors rather than pretending there is a measurement at
0 m: T/RH/q use 2 m, and U/V use 10 m. Therefore the lower effective domains
are `[2,1500]` for T/RH/q and `[10,1500]` for wind. The stored layer identity
remains `0--1500 m AGL` and provenance records the feature-specific surface
anchor. The upper domain is exactly `[1500,3000]` for all profile fields.

The lower specific-humidity mean requires direct 2 m SPFH. The lower omega
mean/min cannot be calculated from pressure-level VVEL because there is no
accepted near-surface height/omega anchor. Both lower omega fields are therefore
null with `missing_reason="lower_boundary_not_bracketed"` in v2. Do not average
only the available upper part and label it `0--1500 m`. Upper-layer omega is
valid when 1500 and 3000 m are bracketed.

### Lapse, wind, shear, humidity, and omega formulas

For hour `h` and an effective layer `[A,B]`:

- Environmental lapse, positive for cooling with height:
  `Gamma_h = 1000·(T(A)-T(B))/(B-A)` K/km. Lower uses `A=2`, `B=1500`;
  upper uses `A=1500`, `B=3000`. Daily columns are `mean_H(Gamma)` and
  `max_H(Gamma)`. This is the standard environmental temperature change per
  height; NOAA describes the same two-endpoint definition in its
  [lapse-rate guidance](https://www.weather.gov/source/zhu/ZHU_Training_Page/definitions/dry_wet_bulb_definition/dry_wet_bulb.html).
- RH and q hourly layer means are `M_h(RH;A,B)` and `M_h(q;A,B)`; persisted
  means are `mean_H(M_h)`. Do not average pressure levels equally because their
  height spacing is unequal.
- Hourly component means are `U_h=M_h(u;A,B)` and `V_h=M_h(v;A,B)`.
  Persisted U/V are `mean_H(U_h)` and `mean_H(V_h)`.
- At every boundary/internal knot derive `s_k=hypot(u_k,v_k)`. Hourly scalar
  speed mean is `S_h=M_h(s;A,B)`. Persisted speed mean is `mean_H(S_h)` and
  speed max is the maximum resolved knot/boundary speed across all hours. Mean
  direction is derived from the persisted mean U/V. This stores both scalar
  wind exposure and vector-resultant direction without averaging angles.
- Bulk vector shear is
  `Shear_h = 1000·hypot(u(B)-u(A),v(B)-v(A))/(B-A)` m/s/km. Lower uses the
  10 m wind anchor; upper uses 1500/3000 m. Persisted values are
  `mean_H(Shear_h)` and `max_H(Shear_h)`. This is endpoint bulk shear, not the
  mean of local scalar shears; AMS defines vertical wind shear as variation of
  the wind vector with height in its
  [wind-shear glossary](https://glossary.ametsoc.org/wiki/wind-shear/).
- Upper-layer hourly omega mean is `Omega_h=M_h(omega;1500,3000)`.
  Persisted mean is `mean_H(Omega_h)` and persisted minimum is the minimum
  resolved boundary/internal-knot omega across all hours. Since
  `omega=Dp/Dt`, a more negative value represents stronger resolved ascent;
  see the [AMS omega definition](https://glossary.ametsoc.org/wiki/omega-equation/).
  It remains synoptic/model vertical-motion evidence, never thermal updraft
  speed.

### Neighbourhood pressure gradient and low-level divergence

Use the exact S05 inclusive 50 km node footprint and its mean Earth radius
`R=6371.0088 km`. For node latitude/longitude `(phi,lambda)` and site
`(phi0,lambda0)` in radians, normalize `DeltaLambda` to `[-pi,pi]` and compute:

- `a = sin²((phi-phi0)/2) + cos(phi0)·cos(phi)·sin²(DeltaLambda/2)`;
- `d = 2R·asin(sqrt(clamp(a,0,1)))`;
- `beta = atan2(sin(DeltaLambda)·cos(phi), cos(phi0)·sin(phi) - sin(phi0)·cos(phi)·cos(DeltaLambda))`;
- local offsets in km: `x=d·sin(beta)` east and `y=d·cos(beta)` north.

At every hour, form `A_i=[1,x_i,y_i]` and solve unweighted least squares with
`numpy.linalg.lstsq(A, values, rcond=None)`. Require its reported rank to equal
3; do not solve the normal equations explicitly:

- `p_i = a_p + b_p x_i + c_p y_i + residual_i` using MSL pressure;
- `u_i = a_u + b_u x_i + c_u y_i + residual_i` using surface/10 m U;
- `v_i = a_v + b_v x_i + c_v y_i + residual_i` using surface/10 m V.

Then:

- `G_h = hypot(b_p,c_p)` Pa/km;
- `D_h = (b_u+c_v)/1000` s^-1 because x/y are km.

Persist `mean_H(G_h)`, `max_H(G_h)`, `mean_H(D_h)`, and `min_H(D_h)`; negative
divergence is convergence. The formula is the standard horizontal
`du/dx + dv/dy` definition documented by the
[AMS Glossary](https://glossary.ametsoc.org/wiki/divergence/). Plane fitting is
a local first-order estimate, not a claim that the field is exactly planar.
Unweighted fitting is selected over distance weighting because S05 already
defines a fixed physical footprint and no validated physical weighting kernel
exists; weighting would introduce an arbitrary source-grid-dependent method.

The affected hourly metric is missing for any missing/duplicate expected node,
wrong field/vertical identity, non-finite value/coefficient, rank below 3, or
footprint/fingerprint mismatch. The 925 hPa U/V evidence is not consumed by
the v2 daily divergence fields.

### Reviewed alternatives and why they are not v2

- Pressure-coordinate/log-pressure interpolation is rejected for the daily
  AGL layers; retain pressure as the raw coordinate and interpolate in height.
- A least-squares temperature slope is rejected for lapse: endpoint change is
  the layer-mean environmental lapse and does not overweight denser pressure
  sampling.
- Magnitude of mean wind is not substituted for mean scalar speed; both answer
  different questions, and direction uses only the resultant vector. This
  requires the targeted DEC-040 wording correction described above; it is not
  an unrecorded semantic change.
- Available-hour aggregation is rejected. Without coverage-count fields it
  silently changes feature meaning and can bias days with missing cloud/CIN
  evidence.
- Surface and 180--0 mb CAPE/CIN, or surface and 925 hPa divergence, are never
  reduced together. They are physically different variants.

## Flying-window/day policy

`sofia-flying-window/1` фиксира:

- timezone: IANA `Europe/Sofia`;
- local window: 10:00–20:00 включително;
- expected instantaneous valid times: точно 11 hourly samples;
- DST conversion чрез `ZoneInfo`, не чрез фиксиран UTC offset; [Python `zoneinfo`](https://docs.python.org/3/library/zoneinfo.html) използва IANA timezone rules;
- един day snapshot може да използва само един source, product/cycle, run, site, local date, point/neighbourhood footprint и feature contract.

GFS денят се събира в един reviewed run. Точният larger
`--maximum-total-mib` се определя след измерване на първи real multi-level
11-hour inventory; builder-ът не обединява run keys и не прикрива cap failure.

Per-feature aggregation е strict: ако някой от 11-те очаквани hourly values липсва, конкретният aggregate е missing. Другите пълни aggregates остават валидни.

Persist exactly the statistics listed in “Accepted daily policy and exact
persisted aggregates” above and defined mathematically in “Scientific formula
contract”. Precipitation, shortwave and surface heat fluxes use only unique,
contiguous, non-overlapping intervals that cover exactly the half-open local
interval `[10:00,20:00)`; they do not consume the preceding 09:00--10:00
interval merely because 10:00 is an instantaneous sample time.
No p90, median, occurrence timestamp, threshold-hour, morning-development, or
additional divergence statistic is emitted in contract v2.

## Implementation structure and artifacts

Основни промени:

- `services/ml/src/paragliding_forecasts_ml/ingestion/weather/features/`
  - `contracts.py` — v2 hourly/day snapshot, feature value, mask и quality contracts;
  - `policy.py` — strict loader за packaged policy;
  - `vertical.py` — interpolation, lapse, shear и RH integration;
  - `neighbourhood.py` — local coordinates, plane fitting, gradient/divergence;
  - `aggregation.py` — flying-window grouping и statistics;
  - `builder.py` — hash-chain verification, source-neutral orchestration и artifact publication.
- `ingestion/weather/resources/weather-feature-policy-v1.json` — ordered feature keys, layers, formulas/method versions, window, aggregations и missing rules.
- `ingestion/weather/feature_cli.py` плюс `pyproject.toml` entry point `weather-build-features`.

Immutable outputs:

- `feature-snapshots.json`
- `day-feature-snapshots.json`
- `feature-quality-report.json`
- `stage-manifest.json`

Fingerprint-ът включва validator manifest, accepted/missing artifacts, exact S05 neighbourhood artifact, policy bytes, feature contract и builder version.

CLI behavior:

- exit `0`: complete feature boundary, дори отделни features да са explicit missing;
- exit `2`: current validation е quarantined; без feature artifacts/event;
- exit `1`: broken hashes/contracts/state или operational error;
- identical replay reuses boundary без нов event;
- policy/version/upstream change публикува immutable `features_built/complete` supersession.

Документацията се обновява в ML README, decisions, tasks и handoff. S07 не стартира S08 persistence или S09 ERA5 collector.

## Test plan and acceptance

- Unit tests с аналитични profiles за:
  - exact boundary interpolation;
  - positive/negative lapse and missing profile inputs;
  - duplicate heights and missing internal levels;
  - vector shear с direction-only и speed-only changes;
  - trapezoidal RH/q/U/V/scalar-speed/omega means on uneven height spacing;
  - scalar speed mean versus resultant-vector direction and numerical-zero
    direction handling;
  - lower feature-specific 2 m/10 m anchors and explicit missing lower omega;
  - strict missing/no extrapolation.
- Analytic neighbourhood planes recover known MSL-pressure gradient and
  surface/10 m divergence after the documented spherical local-coordinate
  transform; test negative convergence, units-per-km conversion, antimeridian
  normalization, missing/duplicate nodes and rank deficiency. Assert that
  925 hPa nodes never feed the v2 daily divergence fields.
- Provider/derived separation:
  - provider PBL/cloud base remain direct provider identities;
  - removed PBL/LCL/buoyancy/convective-velocity candidates are absent from
    active feature keys and daily output contracts;
  - vertical velocity/TKE никога не попълват thermal strength.
- GFS source-contract tests:
  - a frozen official `pgrb2.0p25` inventory proves every accepted
    parameter/level selector and rejects unavailable 875 hPa;
  - a bounded live inventory check is recorded before accepting the corrected
    band, without downloading full GRIB files;
  - parsed geopotential heights prove 1500/3000 m AGL bracketing for every
    reviewed site or produce explicit per-feature missingness;
  - 2 m SPFH and every accepted pressure-level SPFH cross collector, parser,
    normalizer, spatial sampling, and source validation without being silently
    dropped;
  - `SHTFL`/`LHTFL` interval/statistic/sign metadata are pinned before their
    canonical upward-positive values are accepted.
  - point cloud selectors choose instantaneous forecast messages and reject or
    ignore same-parameter interval-average messages deterministically.
  - cloud-ceiling HGT never populates `provider_cloud_base_agl_m`; absent GFS
    cloud base produces explicit per-field missing provenance.
- Day tests:
  - 10:00 и 20:00 са включени, 09:00/21:00 са изключени;
  - summer/winter UTC conversion и DST-aware local date;
  - точно 11 hourly values;
  - incomplete hour, interval gap/overlap и duplicate hour;
  - exact `[10:00,20:00)` interval coverage, duration weighting, and exclusion
    of the 09:00--10:00 interval;
  - precipitation total may be valid while hourly maximum is independently
    missing for non-hourly source intervals;
  - exact persisted mean/min/max/total statistics only;
  - daily CAPE/CIN use only the matching surface parcel and daily divergence
    uses only surface/10 m U/V.
- Source-neutral synthetic tests с GFS-shaped и ERA5-shaped accepted artifacts, без import на source adapters.
- Stage/CLI tests за quarantine blocking, offline behavior, hash tampering, replay и supersession.
- Contract/schema parity tests for the forward-cleaned daily snapshot, hourly
  2 m specific-humidity input, input join, layer, and provenance shapes. S07
  emits artifacts only and performs no SQLite writes.
- Финална валидация:
  - focused feature/database tests;
  - всички ML tests;
  - Ruff format/check;
  - database tests и `db:check`;
  - root build/typecheck/lint/test/repo:check;
  - `git diff --check`.

Acceptance изисква никаква fabricated numeric стойност: всеки непокрит layer,
непълен ден, невалиден neighbourhood fit или неприет derivation/reduction
остава null с `missing` или `unsupported` според причината, има
machine-readable reason и участва в missing mask/quality summary.
