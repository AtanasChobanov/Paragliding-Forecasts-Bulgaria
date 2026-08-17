# T-017 Weather Feature and Source Spike

Status: **spike complete; source roles, canonical units, nullability, and
derivation boundaries are locked for T-018 implementation review.**

Date: 2026-08-16

The machine-readable companion to this report is
[`T-017-weather-field-catalogue.json`](T-017-weather-field-catalogue.json).
The catalogue is the proposed ingestion vocabulary for T-018. It is not yet a
database schema and must not be treated as an accepted source-provider decision
until the CDS checks below are complete.

## Scope and safety boundary

This spike tests whether the T-016 candidate sources actually provide the
fields needed for a paragliding decision-support model. It does not validate a
forecast as safe for flight and it does not turn a day without a collected XC
flight into a negative training label.

The spike preserves these source kinds separately:

- `forecast`: an as-issued model run with run, availability, valid, retrieval,
  and lead times;
- `reanalysis`: a retrospective reconstruction that was not available as an
  operational forecast at the same valid time;
- `observation`: a station or radiosonde measurement.

No request silently fell back to a different model.

## Representative sample

### Sites

The sample uses five of the seven initial canonical product sites. This is more
useful than adding unrelated points because it tests the terrain and coordinate
choices the first product release will actually use.

| Site | Latitude | Longitude | Reason |
| --- | ---: | ---: | --- |
| Vitosha / Kominite | 42.6013 | 23.2844 | high mountain and complex relief |
| Sopot | 42.68733 | 24.749962 | central Balkan launch and strong XC history |
| Pastrina | 43.4282 | 23.3032 | north-western lower mountain/foothill |
| Nevsha | 43.2622 | 27.2846 | north-east, lower terrain and maritime influence |
| Dobrich region | 43.56667 | 27.83333 | flat north-east/near-coastal plain |

External sites should be added later only for a concrete coverage or orography
question. Shumen and Zlatitsa remain canonical but are not needed to make this
bounded five-site spike representative.

### Days

| Case | Valid day/time | Evidence and interpretation |
| --- | --- | --- |
| Strong XC | 2025-08-02 12:00 UTC | 11 local normalized XC records; maximum 400.86 km and 2,660.71 km total recorded distance. |
| Marginal XC | 2025-08-11 12:00 UTC | one local normalized record, 100.31 km from Sopot. |
| Overcast/precipitation | 2025-05-25 12:00 UTC | no local XC record; independent ERA5-hosted screening across the five sites gave mean 19.3 mm daily precipitation and 98% mean cloud cover. This is a technical weather case, not a labelled non-flying day. |
| ICON exact-run comparison | 2026-08-05 12:00 UTC | 10 local normalized records, maximum 317.3 km. Required because the hosted ICON-EU Single Runs archive begins on 2026-04-02. |

The first three cases came from the ignored T-013 normalized local data under
`data/interim/xccontest/`. The weather screening does not modify those artifacts.

## Exact-run protocol

For each forecast case the intended valid time is 12:00 UTC and the requested
leads are 24, 48, 72, and 120 hours. Each request records the explicit model and
run. Open-Meteo requests use native temporal resolution, metres per second for
wind, and `elevation=nan` to disable statistical elevation downscaling and expose
the model-grid elevation.

The Open-Meteo Single Runs endpoint rejected `start_hour`, so the spike retained
the bounded multi-day response and selected the exact valid timestamp locally.
One IFS request returned HTTP 200 with a plain-text `modelRunUnavailable` error
instead of JSON. Production ingestion must therefore validate content type,
model/run identity, the requested valid timestamp, and non-null completeness;
HTTP status alone is insufficient.

## Results by source

### Open-Meteo ECMWF IFS HRES Single Runs

Tested 12 exact-run requests for the three 2025 cases, each containing all five
sites and 46 requested fields. Eleven responses were valid JSON; the marginal
case's 2025-08-08 12:00 UTC run at lead 72 was unavailable. Valid payloads were
approximately 183-188 KB and took about 3.3-19.9 seconds during this spike.

Confirmed available surface fields include 2 m temperature, relative humidity,
dew point, pressure, cloud fractions, precipitation, radiation, 10/100/200 m
wind, CAPE, CIN, boundary-layer height, and total-column water vapour. Individual
archived runs were not uniformly complete: among 55 site/valid-time samples,
boundary-layer height was null in 10, CAPE in 5, and CIN in 24.

Every requested 925/850/700 hPa temperature, humidity, wind, geopotential-height,
and vertical-velocity value was null with an undefined unit. This matches the
provider documentation: native IFS HRES 9 km pressure-level variables are not
offered by this endpoint. `freezing_level_height` and `lifted_index` were also
undefined and null in this sample.

The raw-grid elevations show why both grid and site height must be retained:

| Site | Returned grid point | Raw model elevation (m) |
| --- | --- | ---: |
| Vitosha | 42.565903, 23.328424 | 1,276 |
| Sopot | 42.7065, 24.726736 | 974 |
| Pastrina | 43.40949, 23.343328 | 182 |
| Nevsha | 43.26889, 27.309416 | 209 |
| Dobrich | 43.550087, 27.8797 | 255 |

For comparison, default elevation downscaling returned 1,433 m at Sopot instead
of the 974 m raw-grid elevation. Downscaled point values and native model values
must not be mixed without explicit provenance.

**Decision from the spike:** hosted IFS HRES cannot be the sole detailed weather
source. It remains a useful high-resolution surface/CAPE/PBL component and
comparator, subject to completeness checks and appropriate commercial terms,
but a separate profile-capable model is mandatory.

### Open-Meteo DWD ICON-EU Single Runs

Four exact runs at leads 24/48/72/120 were tested for the 2026-08-05 comparison
day. All 20 site/lead samples contained surface temperature/humidity/dew point,
pressure, precipitation, cloud fractions, radiation, 10 m wind/gust, CAPE/CIN,
and 925/850/700 hPa temperature, humidity, wind, and geopotential height.

Boundary-layer height and pressure-level vertical velocity were undefined and
all null. Payloads were approximately 150-152 KB and took about 20.7-26.2
seconds. The returned grid elevations were 1,059 m at Vitosha, 1,068 m at Sopot,
240 m at Pastrina, 185 m at Nevsha, and 251 m at Dobrich.

**Decision from the spike:** ICON-EU is the strongest no-credential detailed
profile candidate tested here, but it still needs a derived/profile PBL method
or direct DWD flux/TKE fields. The hosted exact-run history is too recent for
older training seasons. Direct DWD is no-registration and commercially safer,
but its public tree is current-run oriented, so the project would have to subset
and archive runs itself.

### NOAA GFS 0.25 degree archive

The official public AWS archive was accessed without an account. A 2025-08-01
00 UTC lead-24 file index contained 743 messages. Forty selected GRIB2 byte
ranges were downloaded and decoded with ecCodes: about 31.4 MB instead of the
roughly 545 MB full file.

Actual decoded metadata confirmed surface temperature/dew point/humidity,
10 m vector wind and gust, pressure, precipitation, cloud cover, surface and
layer CAPE/CIN, boundary-layer height, plus 925/850/700 hPa geopotential,
temperature, humidity, vector wind, and vertical velocity. Native units include
K, Pa, percent, m/s, geopotential metres, Pa/s, J/kg, and kg/m2. Accumulation
step ranges must be retained and de-accumulated before hourly comparison.

The exact 12 UTC indexes for the strong day were also verified for all required
leads:

| Run | Lead | Index messages | Approximate full GRIB size from last offset |
| --- | ---: | ---: | ---: |
| 2025-08-01 12 UTC | 24 h | 743 | 545 MB |
| 2025-07-31 12 UTC | 48 h | 743 | 545 MB |
| 2025-07-30 12 UTC | 72 h | 743 | 543 MB |
| 2025-07-28 12 UTC | 120 h | 743 | 544 MB |

GFS native CIN is signed negative, while the Open-Meteo output observed in this
spike represents CIN as a positive magnitude. The canonical field therefore
uses an explicit positive-magnitude name and retains native value/sign metadata.
The locally decoded HPBL short name appeared as `unknown` under the temporary
ecCodes definition set even though the NOAA index identifies it as HPBL; a
production decoder must pin and test the GRIB table/version.

**Decision from the spike:** GFS is accepted as the exact, long-history,
no-credential forecast archive comparator. Its coarse grid does not replace a
regional terrain-resolving source.

### NOAA IGRA Sofia radiosondes

Station `BUM00015614` raw and derived ZIP archives downloaded without an account.
Both formats contained profiles for all three 2025 case dates, at 06 and 12 UTC:

| Date | 06 UTC raw/derived levels | 12 UTC raw/derived levels |
| --- | ---: | ---: |
| 2025-05-25 | 148 / 36 | 137 / 52 |
| 2025-08-02 | 132 / 35 | 150 / 44 |
| 2025-08-11 | 155 / 40 | 143 / 38 |

The profile contract must preserve the actual nominal/release time; it must not
assume that every station always reports at 00/12 UTC. IGRA is accepted as an
observational validation source, not a forecast replacement.

### ERA5 through CDS

Four bounded Bulgaria-only GRIB requests completed successfully for all three
case days. The requests covered 11/12/13 UTC, 22 single-level fields, seven
pressure-level fields, and 1000/975/950/925/900/875/850/800/750/700 hPa. Total
payload size was 519,048 bytes; individual requests completed in approximately
37-78 seconds.

The decoded native inventory is:

| Group | Native fields and units |
| --- | --- |
| Surface state | `2t`/`2d` K; `sp`/`msl` Pa; `10u`/`10v` m/s; surface `z` m2/s2 |
| Convection/PBL | `blh` m; `cbh` m; `cape`/`cin` J/kg; `zust` m/s |
| Clouds/water | `tcc`/`lcc`/`mcc`/`hcc` fraction 0-1; `tcwv` kg/m2 |
| Interval fields | `tp` m; `ssrd` J/m2; mean shortwave/sensible/latent fluxes W/m2 |
| Pressure levels | `t` K; `q` kg/kg; `r` percent; `u`/`v` m/s; `w` Pa/s; `z` m2/s2 |

All 630 requested pressure-level messages decoded without a missing grid value.
The surface fields exposed a critical distinction between physical zero and
missing evidence:

- `cin` used the GRIB missing sentinel `9999` in 2,193 of 2,349 Bulgaria-grid
  values (93.36%). At the five sites at 12 UTC, only 1 of 15 CIN samples was
  present.
- `cbh` was missing in 513 of 2,349 grid values (21.84%) and in 3 of 15 site
  samples at 12 UTC.
- `cape` and `blh` were present at all 15 site/time samples. A zero CAPE value is
  valid data and must not be treated as missing.

The decoder must use GRIB missing metadata/bitmap handling and normalize missing
sentinels to `null`; `9999 m` or `9999 J/kg` must never cross the ingestion
boundary as a measurement.

Some ERA5 variables selected as reanalysis are delivered from forecast steps.
For the requested 11/12/13 UTC values, accumulated and mean fields had native
step ranges 4-5, 5-6, and 6-7 hours; `cbh`, `cin`, and `zust` had steps 5, 6,
and 7. Run/base time, valid time, step range, and statistical processing type
are therefore mandatory even for reanalysis ingestion.

Cloud fractions require multiplication by 100 for the canonical percent unit;
precipitation metres require multiplication by 1,000 for millimetres; and
geopotential requires division by standard gravity for geopotential height.
ERA5's downward-positive heat-flux convention means an upward-positive project
flux must negate the native sensible/latent flux after interval normalization.

**Decision from the spike:** ERA5 is accepted as the long-history reanalysis
baseline. It provides the most complete direct foundation for PBL, cloud base,
CAPE, surface fluxes, and atmospheric profiles, but direct CIN and cloud base
remain nullable and must not be imputed silently.

### CERRA through CDS

Authentication, terms acceptance, retrieval, and GRIB decoding are now verified.
The full-domain analysis request returned 12 messages for 2025-05-25 12:00 UTC;
the diagnostic request returned one `2t` message for 2025-08-02 12:00 UTC.
Every message used the 1069 x 1069 Lambert conformal grid (1,142,761 points),
analysis step `0`, and the requested valid time. No decoded message contained a
missing grid value.

The actual native surface inventory is:

| Native field | Decoded name | Native unit | Canonical treatment |
| --- | --- | --- | --- |
| `2t` | 2 metre temperature | K | `air_temperature_k`, direct |
| `2r` | 2 metre relative humidity | `%` | `relative_humidity_percent`, direct |
| `10si` | 10 metre wind speed | `m s**-1` | `wind_speed_m_s`, direct |
| `10wdir` | 10 metre wind direction | `Degree true` | meteorological direction, direct |
| `msl` | mean sea-level pressure | Pa | sea-level `air_pressure_pa`, direct |
| `sp` | surface pressure | Pa | surface `air_pressure_pa`, direct |
| `tcc`/`lcc`/`mcc`/`hcc` | cloud cover by layer | `%` | `cloud_cover_percent`, already 0-100 |
| `orog` | orography | m | `grid_elevation_m`, direct model terrain |
| `tciwv` | total-column integrated water vapour | `kg m**-2` | column-water field, direct |

Unlike sources that expose `u`/`v`, this CERRA surface analysis exposes speed
and meteorological direction. Canonical components must therefore be derived as
`u = -speed * sin(direction)` and `v = -speed * cos(direction)` with direction
converted to radians. The native speed/direction must remain in provenance.

The actual retrieval and processing evidence is:

| Request | Payload | Queue wait | CDS processing | Local download |
| --- | ---: | ---: | ---: | ---: |
| 12-field analysis `cd6ecce3-43f2-42dc-b6f7-9bb54ae01577` | 27,438,924 bytes | about 2 h 07 m 49 s | 9.32 s | 5.35 s |
| diagnostic `2t` `022c32df-a870-4049-abd2-b5dcf6b4a385` | 2,286,577 bytes | about 2 h 02 m 52 s | 10.35 s | 2.92 s |

The long delay was provider queue time, not data generation or transfer time.
The single-field payload is still about 2.29 MB and the 12-field payload about
27.44 MB because the main CDS form exposes no geographic area subset.

Nearest-grid terrain confirms that source/model elevation must be retained:

| Site | CERRA grid point | CERRA orography (m) |
| --- | --- | ---: |
| Vitosha / Kominite | 42.58110, 23.29965 | 1,513.86 |
| Sopot | 42.69753, 24.76780 | 1,320.23 |
| Pastrina | 43.42846, 23.33456 | 237.86 |
| Nevsha | 43.25258, 27.30442 | 177.36 |
| Dobrich region | 43.55610, 27.83649 | 244.86 |

The 2025-05-25 samples were physically consistent with the selected
overcast/precipitation case: total cloud cover was 100% at four sites and
76.47% near Dobrich. This is supporting technical evidence, not a safety or
non-flying label.

The catalogue declares additional pressure-level and forecast products, but
this bounded retrieval decoded only single-level analysis data. Direct CERRA
PBL height, cloud-base height, CAPE, and CIN are not exposed by the reviewed
single/pressure dataset forms. They must remain missing or be derived from
other validated inputs; CERRA TKE must not be renamed to thermal strength.

**Decision from the spike:** CERRA is accepted as an offline terrain-resolution
reanalysis comparator. Its verified surface fields and model orography are
useful evidence, but it is not the primary source for PBL/cloud-base/CAPE/CIN
and its full-domain payload/queue cost makes it unsuitable for per-site live
requests. ERA5 remains the long-history reanalysis baseline.

## Proposed canonical feature contract

The detailed field list and source mappings are in the JSON catalogue. These
rules are required regardless of storage design:

- Keep native name, native value/unit, source/model/run, grid point/elevation,
  valid/retrieval/availability time, lead, interval/step, and derivation version.
- Use temperature K internally, pressure Pa, speed m/s, height m, radiation
  W/m2, CAPE/CIN J/kg, precipitation mm per explicit interval, and cloud/RH as
  percent 0-100. API/UI adapters may display degrees Celsius and hPa.
- Preserve the source's native wind representation. Derive speed/direction from
  native `u`/`v`, or derive `u = -speed*sin(direction)` and
  `v = -speed*cos(direction)` when CERRA supplies meteorological speed/direction.
  Derive fixed AGL bands only after pressure-level geopotential is converted to
  AGL and levels below terrain are excluded.
- Represent CIN as `convective_inhibition_magnitude_j_per_kg`, always non-negative,
  while preserving the source sign convention.
- Keep provider PBL height and derived PBL height separate, with an explicit
  method. A profile fallback may use a versioned bulk-Richardson or potential-
  temperature-threshold method; it is not interchangeable with provider PBL.
- Keep provider cloud base separate from a derived mixed-layer LCL. A proposed
  `project_mixed_layer_lcl_v1` can mix temperature and humidity through the
  lowest approximately 100 hPa, calculate LCL thermodynamically, and return both
  MSL and AGL heights. LCL is not automatically an observed cloud ceiling.
- Do not retain one ambiguous `thermalStrengthMps` field. A physical convective
  velocity scale requires boundary-layer depth and surface buoyancy flux:
  `w* = ((g/theta_v) * buoyancy_flux * zi)^(1/3)`. It is only valid where the
  required flux and PBL inputs exist. Model vertical velocity, maximum updraft,
  and `sqrt(TKE)` are different features and must not be aliased to it.
- Derive lapse rate, inversion strength/depth, wind shear, and humidity layers
  from profiles with versioned AGL layer definitions. Single-point fields cannot
  produce pressure gradients or convergence; those require a retained grid or
  neighbourhood and a versioned spatial calculation.
- Convert accumulated precipitation and radiation using source step/reset
  metadata before comparison. Never infer an hourly value by dividing an
  accumulation without validating its interval.

## Final source lock after the full spike

| Role | Current result |
| --- | --- |
| Exact long-history forecast comparator | **GFS accepted**; coarse-resolution limitation retained. |
| Detailed recent/regional profile forecast | **ICON-EU preferred** over hosted IFS HRES; production path still needs commercial/licence and self-archive decision. |
| High-resolution surface/PBL forecast component | **IFS HRES retained conditionally**, not as sole source. |
| Long-history reanalysis baseline | **ERA5 accepted**; direct CIN/cloud base remain nullable. |
| Terrain-resolution reanalysis comparison | **CERRA accepted** for offline comparison; verified surface analysis only, not primary PBL/CAPE/CIN evidence. |
| Observed upper-air validation | **IGRA accepted**, with actual observation-time availability retained. |

T-017 is ready for `Review`. T-018 may implement the locked catalogue while
preserving nullable fields, derivation versions, source roles, and the documented
production-licence limitations.

## Local artifacts and reproducibility

All raw artifacts are ignored by Git and remain on disk D: inside the project:

- `data/raw/weather-spike/gfs-20250801T00-f024/` - selected GFS GRIB2 messages;
- `data/raw/weather-spike/open-meteo-ifs-hres/` - 12 exact IFS responses,
  including the retained unavailable-run response;
- `data/raw/weather-spike/open-meteo-icon-eu/` - four exact ICON-EU responses;
- `data/raw/weather-spike/igra-sofia/` - IGRA raw and derived station archives.
- `data/raw/weather-spike/cds/` - CDS request/result metadata plus decoded ERA5 and CERRA GRIB summaries.

The GFS values were decoded with a temporary uv/ecCodes environment; no Python
dependency or secret was added to the repository. The permanent, reviewable
output of this research phase is this report and its JSON catalogue. T-018/T-019
should turn accepted mappings into tested ingestion code rather than depend on
an ad-hoc research decoder.

## Primary documentation consulted

- Open-Meteo Single Runs API: <https://open-meteo.com/en/docs/single-runs-api>
- Open-Meteo ECMWF API: <https://open-meteo.com/en/docs/ecmwf-api>
- Open-Meteo model updates and terms: <https://open-meteo.com/en/docs/model-updates>
  and <https://open-meteo.com/en/terms>
- NOAA GFS public archive: <https://registry.opendata.aws/noaa-gfs-bdp-pds/>
- NOAA IGRA: <https://www.ncei.noaa.gov/products/weather-balloon/integrated-global-radiosonde-archive>
- Copernicus CDS API setup: <https://cds.climate.copernicus.eu/how-to-api>
- DWD ICON-EU open data: <https://opendata.dwd.de/weather/nwp/icon-eu/grib/>

