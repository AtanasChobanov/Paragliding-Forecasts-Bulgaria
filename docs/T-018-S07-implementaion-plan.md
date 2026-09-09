# T-018/S07 — Versioned source-neutral weather feature builder

## Summary

S07 ще добави offline команда `weather-build-features --run-key <uuid>`, която:

- приема единствено текущ `validated/complete` S06 boundary;
- чете `accepted-samples.json`, `missing-evidence.json` и hash-verified S05 neighbourhood nodes;
- не импортира GFS/ERA5 adapter код и работи само с canonical contracts;
- произвежда immutable hourly и site/day feature snapshots;
- оставя неприети или недостатъчно обезпечени derivations като `null`, `quality_state="missing"` и точен reason code;
- не пише в SQLite — persistence остава S08.

Версии:

- `weather-feature-builder/1`
- `weather-feature-contract/1`
- `weather-feature-policy/1`
- `agl-piecewise-linear/1`
- `neighbourhood-planar-fit/1`
- `sofia-flying-window/1`

Нови Python dependencies не са нужни: `numpy`, `pydantic`, `tzdata` и стандартните `zoneinfo`, `math`, `datetime` са достатъчни.

## Approved session baseline — 2026-09-08

This section supersedes every conflicting earlier draft in this file.

### Persistence is complete; S07 does not redesign it

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
immutable artifact projections computed from those provenance rows. Provider
PBL/cloud-base aggregates remain distinct from derived PBL/LCL.

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
- per AGL layer: lapse mean/max, inversion strength/depth pair, RH and
  specific-humidity means, U/V means, speed mean/max, vector direction, shear
  mean/max, and vertical-velocity mean/min.

p90, medians, threshold hours, morning development rate, earliest-occurrence
timestamps, separate surface/925 divergence columns, and a daily JSON quality
column are deliberately not persisted in v1. They are not silently substituted
by another statistic; add them only through a reviewed future schema/contract
change.

### Vertical input correction

GFS collection, numeric GRIB profile validation, normalization, sampling, and
source validation now require the full 1000/975/950/925/900/875/850/800/750/700
hPa band for `HGT/TMP/RH/UGRD/VGRD/VVEL`, matching the first ERA5 profile
band. The old 925/850/700-only requirement is superseded. S05 already carries
all selected pressure grains through to profile rows, so no separate sampling
table or adapter path is needed. A level below reviewed site terrain or model
terrain remains an explicit exclusion and cannot bracket interpolation.

### Formulas, guards, and deliberately unsupported derivations

Use only the formulas specified later in this plan: component wind
`sqrt(u²+v²)`, meteorological direction
`(atan2(-u,-v)·180/π+360) mod 360`, piecewise-linear vertical interpolation,
endpoint lapse/shear, trapezoidal layer humidity, and full-rank planar
least-squares neighbourhood gradient/divergence. No vertical extrapolation,
wind-angle averaging, node-weight renormalization, interval de-accumulation,
or fabricated numeric completion is allowed.

Derived PBL remains unsupported: provider PBL is already a provider-specific
fact, not a substitute for an accepted project bulk-Richardson or
potential-temperature-threshold method. Mixed-layer LCL remains unsupported
until the parcel-mixing depth, parcel thermodynamics, constants, and vertical
integration policy are accepted. Surface buoyancy flux and Deardorff `w*`
remain unsupported for GFS until validated sensible/latent flux, density,
virtual potential temperature, positive buoyancy flux, and positive mixing
depth are available. Never substitute omega/VVEL, gust, or TKE for `w*`.

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
3. Acceptance of a project-derived PBL, mixed-layer LCL, buoyancy flux, or
   `w*` requires a separately reviewed physical-method decision and source
   input audit. Until then the result is `missing/unsupported`, never a
   fallback estimate.

## Historical draft prerequisites and schema work

This pre-session draft is retained for traceability only. The approved
2026-09-08 baseline above controls where it conflicts: the migrations are
already applied, S07 writes no replacement schema, and its actual target is
weather_daily_feature_snapshots plus its input and layer relations. In
particular, do not implement the obsolete table/column names, a second
database migration, JSON quality columns, p90/median/threshold aggregates, or
any other persistence/statistic proposal below that conflicts with the
approved baseline. The remaining derivation detail is useful only where it is
consistent with that baseline.

Преди builder-а да се счита за надежден:

- Поправяне на остарелите S06 nullable names:
  - `cloud_base_height_agl_m` → `provider_cloud_base_agl_m`;
  - `convective_inhibition_j_per_kg` → `convective_inhibition_magnitude_j_per_kg`.
- Validation policy loader да проверява всички field codes спрямо packaged T-017 catalogue, за да не се допуска отново silent drift.
- `FeatureSnapshot` v1 да остане readable за старите synthetic fixtures, но реалният S07 да въведе batch contract v2 с:
  - уникален `feature_key`;
  - canonical `field_code`, unit и optional variant/layer/statistic;
  - value, quality, missing reason и derivation provenance;
  - ordered missing mask и quality summary.
- Да се запише DEC-039 за:
  - фиксираните AGL слоеве;
  - flying-window policy;
  - planar neighbourhood method;
  - S07 DB extension.

Нужна е нова reviewed Drizzle migration, без промяна на приложените migrations:

- `weather_feature_snapshots`:
  - existing lapse/shear columns стават долния surface–1500 m слой;
  - добавят се upper 1500–3000 m lapse/shear;
  - lower/upper layer mean RH и layer boundaries;
  - отделни surface и 925 hPa divergence колони;
  - canonical missing-mask и quality-summary metadata.
- Нова wide таблица `weather_day_feature_snapshots` за site/local-date/window/contract identity и фиксираните day aggregates.
- `weather_field_provenance` получава day-snapshot owner FK, partial unique index и обновен exactly-one-owner check.
- Физическата схема в diagram-а, database tests и DEC-033 table-count assertions се обновяват. S07 само подготвя schema contract; реалните DB inserts остават S08.

## Canonical inputs and hourly formulas

### Direct and already accepted transformations

| Snapshot input | GFS native input | ERA5 input за S09 | S07 treatment |
| --- | --- | --- | --- |
| 2 m temperature | `TMP:2 m` | `2m_temperature` | Direct Kelvin |
| 2 m dew point | `DPT:2 m` | `2m_dewpoint_temperature` | Direct Kelvin |
| 2 m RH | `RH:2 m` | Само при accepted direct/normalized mapping | Не се извежда от T/Td в S07 |
| Surface/MSL pressure | `PRES`, `PRMSL` | `surface_pressure`, `mean_sea_level_pressure` | Direct Pa; двете identities остават отделни |
| 10 m U/V | `UGRD`, `VGRD` | `10m_u/v_component_of_wind` | Direct m/s |
| Wind speed | accepted U/V | accepted U/V | `sqrt(u² + v²)` |
| Wind direction | accepted U/V | accepted U/V | `(atan2(-u,-v)·180/π + 360) mod 360`; при calm wind остава missing |
| Provider PBL | `HPBL` | `boundary_layer_height` | Direct provider AGL; никога derived PBL |
| Provider cloud base | GFS S03 не го събира | `cloud_base_height` | GFS missing; ERA5 direct само след S09 validation |
| Cloud cover | `TCDC/LCDC/MCDC/HCDC` | total/low/mid/high cloud cover | Percent; variants се пазят |
| Column water | `PWAT` | `total_column_water_vapour` | Direct/normalized kg/m² |
| CAPE | surface и 180–0 mb AGL | provider parcel variant | Direct J/kg с variant |
| CIN | signed native CIN | provider CIN | `abs(native_cin)` само за доказана non-positive convention |
| Precipitation | `APCP` | `total_precipitation` | Запазен validated interval; без деление на произволен брой часове |
| Shortwave radiation | `DSWRF` interval average | validated ERA5 radiation statistic | W/m² само след доказана interval/statistic normalization |
| Profiles | `HGT/TMP/RH/UGRD/VGRD/VVEL` at 1000/975/950/925/900/875/850/800/750/700 hPa | same accepted ERA5 band | Pressure, MSL height, T/RH/U/V/ω се запазват canonical |

За profile height:

`z_agl = geopotential_height_msl_m - reviewed_site_elevation_msl_m`

Ниво под site или model terrain остава excluded, както е прието в S05.

### Vertical interpolation and layers

Policy слоевете са:

- lower: surface–1500 m AGL;
- upper: 1500–3000 m AGL.

„Surface“ означава реалния canonical anchor, без фиктивна екстраполация до 0 m:

- 2 m за temperature/RH;
- 10 m за U/V;
- pressure-level anchors над него.

За boundary `z` между две валидни нива:

`f(z) = f1 + (f2 - f1) · (z - z1) / (z2 - z1)`

Няма extrapolation. Всеки band изисква bracketing coverage на двата края и всички вътрешни очаквани profile values да са валидни. Иначе целият feature е missing.

Hourly derived fields:

| Feature | Formula |
| --- | --- |
| Lower lapse | `(T_surface - T_1500) · 1000 / (1500 - z_surface)` K/km |
| Upper lapse | `(T_1500 - T_3000) · 1000 / 1500` K/km |
| Lower shear | `sqrt((u1500-u10)² + (v1500-v10)²) · 1000 / (1500-10)` m/s/km |
| Upper shear | `sqrt((u3000-u1500)² + (v3000-v1500)²) · 1000 / 1500` m/s/km |
| Layer mean RH | `∫ RH(z) dz / (z_top-z_base)`, evaluated over the piecewise-linear profile with the composite trapezoidal rule |

Положителен lapse означава cooling with height; inversion дава отрицателна стойност. Това е изрично versioned sign convention. Основното физично определение е температурната разлика върху височинната разлика, както е описано от [NOAA/NWS](https://www.weather.gov/source/zhu/ZHU_Training_Page/definitions/dry_wet_bulb_definition/dry_wet_bulb.html). Интеграцията използва вече наличния [`numpy.trapezoid`](https://numpy.org/doc/2.1/reference/generated/numpy.trapezoid.html).

### Neighbourhood metrics

Използват се само S05 50 km nodes:

- MSL pressure за pressure gradient;
- surface U/V за surface divergence;
- 925 hPa U/V за isobaric low-level divergence.

Node coordinates се превръщат в signed local east/north offsets спрямо site чрез spherical distance and bearing. След това чрез unweighted full-rank least-squares plane:

- `p(x,y) = aₚ + bₚx + cₚy`
- `u(x,y) = aᵤ + bᵤx + cᵤy`
- `v(x,y) = aᵥ + bᵥx + cᵥy`

Резултати:

- pressure gradient: `sqrt(bₚ² + cₚ²) · 1000` Pa/km, когато x/y са metres;
- surface divergence: `bᵤ + cᵥ` s⁻¹;
- 925 hPa divergence: същата формула върху 925 hPa U/V.

Отрицателна divergence означава convergence. Това следва стандартното `∂u/∂x + ∂v/∂y` определение на [AMS](https://glossary.ametsoc.org/wiki/divergence/). Plane coefficients се намират с [`numpy.linalg.lstsq`](https://numpy.org/doc/stable/reference/generated/numpy.linalg.lstsq.html).

Метриката е missing при:

- поне един missing footprint node;
- duplicate node identity;
- недостатъчен matrix rank;
- non-finite coefficient;
- footprint или sampling fingerprint mismatch.

### Explicitly unsupported v1 derivations

Следните DB/catalogue slots присъстват в missing mask, но не се изчисляват в S07 v1:

- `derived_boundary_layer_height_agl_m`: T-017 има само candidate bulk-Richardson/θ-threshold методи. Provider PBL остава отделно; дори ERA5 използва собствен provider bulk-Richardson definition, документиран от [ECMWF](https://codes.ecmwf.int/grib/param-db/159).
- `mixed_layer_lcl_agl_m/msl_m`: lowest-100-hPa parcel mixing method, constants и vertical integration още не са приети. Известните Bolton/exact-LCL формули са реални, но не разрешават сами project mixed-layer policy; виж [Bolton 1980](https://journals.ametsoc.org/doi/10.1175/1520-0493%281980%29108%3C1046%3ATCOEPT%3E2.0.CO%3B2).
- `surface_buoyancy_flux_kinematic_k_m_s`: GFS S03 няма sensible/latent flux, а density/virtual-potential-temperature method не е приет.
- `convective_velocity_scale_m_s`: остава missing, докато няма accepted positive buoyancy flux, positive PBL depth и virtual-potential-temperature input.

Бъдещият accepted method трябва да използва:

`B₀ = H/(ρcp) + 0.61·θᵥ·LE/(ρLv)`

`w* = cbrt((g/θᵥ) · B₀ · zᵢ)`

Това е Deardorff convective velocity scale; [AMS](https://glossary.ametsoc.org/wiki/deardorff-velocity/) потвърждава нужните mixed-layer depth и kinematic virtual-potential-temperature flux. S07 не замества `w*` с vertical velocity или `sqrt(TKE)`.

Unsupported се представя чрез `quality_state="unsupported"` и
`missing_reason="unsupported_derivation_method"`. S07 contract v2 трябва
изрично да добави тази state; persisted provenance вече я допуска.

## Flying-window/day policy

The historical aggregate list in this section is superseded by “Accepted daily
policy and exact persisted aggregates” above. Retain only its formula and
coverage explanations; persist exactly the approved daily columns and
statistics, not p90 values, occurrence timestamps, or additional divergence
variants.

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

Day statistics:

- T2: mean и max;
- dew point: mean и min;
- RH2 и двата layer-RH features: mean и min;
- U/V: arithmetic vector mean; speed/direction се извеждат от mean U/V, никога от средно на angles;
- 10 m speed и lower/upper shear: max и p90;
- lower/upper lapse: mean и max;
- provider PBL: max и earliest occurrence time;
- provider cloud base: min и earliest occurrence time;
- convective velocity: max и median, но v1 остава missing;
- CAPE variants: max;
- canonical positive CIN magnitude variants: max, тоест най-силна inhibition;
- TCWV: mean и max;
- total/low/mid/high cloud cover: max и p90;
- pressure gradient: max;
- surface и 925 hPa divergence: minimum, тоест strongest convergence;
- precipitation: сума само на unique, contiguous, non-overlapping intervals, които покриват точно `[10:00,20:00]`;
- shortwave radiation: duration-weighted mean и max за същия exact interval coverage.

p90 използва sorted linear interpolation при index `(n-1)·0.9`. Timestamp ties използват най-ранния local час. Threshold-hours и morning development rate остават unsupported, защото thresholds/method още не са приети.

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
  - positive lapse, inversion и duplicate heights;
  - vector shear с direction-only и speed-only changes;
  - trapezoidal RH mean;
  - strict missing/no extrapolation.
- Аналитични neighbourhood planes да възстановяват точно известен pressure gradient и surface/925 divergence; тестове за negative convergence, missing nodes и rank deficiency.
- Provider/derived separation:
  - provider PBL/cloud base не попълват derived PBL/LCL;
  - GFS flux/w*/LCL/PBL-derived slots са missing с точния reason;
  - vertical velocity/TKE никога не попълват thermal strength.
- Day tests:
  - 10:00 и 20:00 са включени, 09:00/21:00 са изключени;
  - summer/winter UTC conversion и DST-aware local date;
  - точно 11 hourly values;
  - incomplete hour, interval gap/overlap и duplicate hour;
  - deterministic p90, median и earliest tie time.
- Source-neutral synthetic tests с GFS-shaped и ERA5-shaped accepted artifacts, без import на source adapters.
- Stage/CLI tests за quarantine blocking, offline behavior, hash tampering, replay и supersession.
- Database tests за новата migration, layer checks, day identity, provenance exactly-one-owner и idempotent migrate.
- Финална валидация:
  - focused feature/database tests;
  - всички ML tests;
  - Ruff format/check;
  - database tests и `db:check`;
  - root build/typecheck/lint/test/repo:check;
  - `git diff --check`.

Acceptance изисква никаква fabricated numeric стойност: всеки непокрит layer, непълен ден, невалиден neighbourhood fit или неприет derivation остава null с machine-readable missing reason и участва в missing mask/quality summary.
