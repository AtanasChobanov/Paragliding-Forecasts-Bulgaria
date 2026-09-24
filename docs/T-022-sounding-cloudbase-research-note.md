# T-022 sounding and cloudbase research note

## Question answered

"Sounding" is a vertical profile and an analysis method, not one specific data
provider. It can mean either:

1. an observed atmospheric profile measured by a radiosonde carried by a
   weather balloon; or
2. a virtual/model sounding assembled from forecast-model values at one
   latitude, longitude, and valid time.

The Project Owner's description fits both. For historical validation we already
have the first kind through NOAA IGRA. For forecasts at all seven locations we
need the second kind from GFS.

## Observed soundings: existing NOAA IGRA boundary

The implemented T-019 pipeline downloads NOAA/NCEI IGRA v2.2 observations for
Sofia station `BUM00015614`. IGRA is a global archive of radiosonde and pilot
balloon observations. NOAA describes more than 2,800 stations, around 800
currently reporting, with station-dependent periods and vertical resolution.

Official inventory on 2026-09-24 lists:

- `BUM00015614`, Sofia Observatory, 42.6500 N / 23.3833 E, 595 m,
  1955-2026;
- `BUM00015730`, Kurdjali, 41.6500 N / 25.3670 E, 331 m,
  1966-1991.

These are the Bulgarian entries in the current IGRA station list. Only Sofia
has current records. Straight-line distances from the Sofia station to the
project coordinates are approximately:

| Project location | Distance from IGRA Sofia | Direct local balloon coverage? |
| --- | ---: | --- |
| Sofia - Vitosha | 10 km | Useful nearby observation |
| Zlatitsa | 59 km | Regional comparison only |
| Pastrina | 87 km | Regional comparison only |
| Sopot | 112 km | Too distant for a local label |
| Shumen | 296 km | No |
| Nevsha | 325 km | No |
| Dobrich region | 375 km | No |

A balloon profile is one observed column that drifts during ascent. It does not
represent every mountain, valley, or distant site at the same time. Therefore
IGRA Sofia cannot supply cloudbase labels or live predictor inputs for all seven
locations.

IGRA also arrives after the atmosphere was observed. Using it as an input to a
historical prediction would leak information that was unavailable at forecast
issue time. Its accepted role remains T-039 validation: compare an archived GFS
profile with the later observed Sofia sounding at the same nominal time and
measure bias or calibration error.

Sources:

- [NOAA/NCEI IGRA product page](https://www.ncei.noaa.gov/products/weather-balloon/integrated-global-radiosonde-archive)
- [Official IGRA station list](https://www.ncei.noaa.gov/pub/data/igra/igra2-station-list.txt)
- [Official IGRA derived-parameter format](https://www.ncei.noaa.gov/pub/data/igra/derived/igra2-derived-format.txt)

## Model soundings: available for all seven locations

A virtual sounding samples GFS temperature, moisture, pressure, height, and wind
through the vertical column above a project coordinate. GFS is global, so the
same calculation can be run for Sofia - Vitosha, Zlatitsa, Sopot, Nevsha,
Shumen, Pastrina, and Dobrich for every retained forecast valid time.

The existing GFS catalogue already includes the main inputs:

- surface pressure, 2 m temperature, dew point/specific humidity;
- pressure-level temperature and relative/specific humidity;
- pressure-level geopotential height;
- pressure-level wind and vertical velocity;
- provider CAPE, CIN, and boundary-layer height.

The current feature pipeline already calculates
`mixed_layer_lcl_agl_m` and `pbl_minus_lcl_m`. This means a transparent first
cloudbase candidate exists in our own data path; no new provider is required
just to begin T-022.

### NOAA READY website/API

NOAA READY is one example of the website the Project Owner mentioned. Its
sounding endpoint accepts GFS/GFS0p25 plus arbitrary global latitude and
longitude, so it can generate a model sounding for all seven locations. The
published API requires registration and an API key, returns text, and currently
limits a user to 250 calls per day. Its documented GFS0p25 product is global,
0.25 degree, 3-hourly, updated four times per day.

READY is not a second independent measurement source. It calculates a sounding
from forecast-model data, including GFS. Adopting it in production would add a
credential, call quota, external availability dependency, text parser, and
possibly different GFS processing while duplicating data we already download.
NOAA also says the READY service is not a 24/7 operation and does not guarantee
data completeness or availability.

Recommendation: use READY only for a bounded manual comparison during T-022,
if useful. Do not make it the production cloudbase source.

Sources:

- [NOAA READY current meteorology](https://www.ready.noaa.gov/READYcmetus.php)
- [NOAA READY Web API guide](https://www.ready.noaa.gov/webapi/READY_Web_API_User_Guide_v0.3.0.pdf)

## What a sounding can calculate

The terms below describe parcel/profile diagnostics rather than learned ML
targets:

- **LCL (lifting condensation level):** the height where a lifted parcel first
  becomes saturated. Mixed-layer LCL is a useful convective cloud-base proxy,
  but it is not an observed cloud ceiling.
- **CCL (convective condensation level):** a condensation level for
  surface-heated convection. It is another cloud-base candidate and requires an
  explicit parcel policy.
- **LFC (level of free convection):** the level above which a parcel can rise
  with positive buoyancy.
- **EL/LNB (equilibrium or neutral-buoyancy level):** an upper bound for a
  parcel's buoyant ascent and a rough convective cloud-top diagnostic. It is not
  automatically the visible cloud top.
- **CAPE:** accumulated positive buoyant energy between LFC and EL. Larger
  values can support deeper convection, but CAPE alone does not predict a safe
  or unsafe day.
- **CIN:** energy that inhibits a parcel from reaching free convection.
- **Inversion/cap:** a stable layer where temperature stops decreasing normally
  or increases with height. Its base, depth, and strength can limit thermals.
- **PBL or mixed-layer top:** a forecast estimate of the actively mixed layer.
  It is a useful usable-thermal-top candidate.

IGRA's own derived files include inversion pressure/height/temperature
difference, mixed-layer top, LCL, LFC, neutral-buoyancy level, Lifted Index,
Showalter Index, K Index, Total Totals, CAPE, and CIN. This confirms that the
owner's suggested diagnostics are standard sounding-derived quantities.

MetPy provides reviewed Python calculations for LCL, CCL, LFC, EL, parcel
profiles, CAPE/CIN, and several instability indices. It is BSD-3-Clause licensed.
T-022 may either reuse the repository's current thermodynamic functions or add
MetPy after reviewing the concrete dependency need and numerical equivalence.

Sources:

- [MetPy sounding calculation example](https://unidata.github.io/MetPy/latest/examples/calculations/Sounding_Calculations.html)
- [MetPy calculation reference](https://unidata.github.io/MetPy/latest/api/generated/metpy.calc.html)
- [MetPy source and BSD-3-Clause license](https://github.com/Unidata/MetPy)

## Recommended T-022 direction

Use a deterministic GFS model-sounding baseline for the MVP, with one
calculation at each site and forecast valid time. Do not train a separate
cloudbase ML model until a trustworthy multi-site target exists.

Recommended output contract:

- `cloud_mode = cumulus | blue | indeterminate`;
- nullable `cloud_base_agl_m` and `cloud_base_msl_m`;
- nullable `usable_thermal_top_agl_m` and `usable_thermal_top_msl_m`;
- `method`, `forecast_reference_time`, `valid_time`, `lead_hours`,
  `confidence`, missing-input reasons, and main drivers.

First baseline logic to evaluate in T-022:

1. calculate a versioned mixed-layer parcel and LCL from the GFS surface and
   pressure profile;
2. compare LCL with provider PBL/mixed-layer top;
3. identify material stable layers/inversions below or near the expected
   thermal top;
4. if the mixed layer can plausibly reach LCL, report a `cumulus` cloud-base
   estimate;
5. if useful buoyant mixing exists but the parcel does not reach saturation,
   report `blue`, keep cloud base null, and still report usable thermal top;
6. if required profile data are missing or contradictory, report
   `indeterminate` rather than inventing a number.

A blue result is not a negative flying-day label. It means thermals may exist
without cumulus markers. XC probability features may use the thermal profile,
PBL, wind, and other evidence independently of whether a numeric cloud base is
present.

For overdevelopment support, add profile diagnostics such as LFC, EL,
CAPE/CIN, deep moisture, saturation depth, inversion/cap strength, and the
duration of forecast precipitation/cloud signals. These become explainable
inputs to the accepted T-024 rule-and-score policy; they do not replace that
policy with one magic sounding threshold.

## Validation plan

1. Run the calculation from existing GFS profiles for all seven sites.
2. For Sofia only, compare GFS LCL, LFC, EL, CAPE/CIN, and detected inversion
   with the nearest-time IGRA observed sounding under T-039.
3. Optionally compare a small set with NOAA READY or another display tool to
   catch interpretation errors.
4. Ask the Project Owner/pilots to review cumulus, blue, capped, and
   overdeveloped case days.
5. Version the parcel choice, vertical interpolation, elevation reference,
   thresholds, and missing-data rules before T-022 is implemented.

The remaining product choices are:

- whether the main card should lead with cloud base, usable thermal top, or
  both;
- the parcel definition: surface, mixed-layer depth, or another reviewed rule;
- the exact `blue` boundary when PBL and LCL are close;
- the inversion strength/depth that materially caps paragliding thermals;
- which intraday hour or maximum within the flying window is displayed;
- whether MSL and AGL are both shown or one is primary.

## Data use and attribution

NOAA U.S. government web information is generally public domain unless marked
otherwise. Treat data openness and software licensing as different questions:
IGRA and GFS data can be used with provenance and NOAA/NCEI acknowledgement,
while the hosted READY API still has registration, quota, and availability
conditions. Keep the IGRA dataset citation and DOI already present in the
repository. Do not imply NOAA endorsement.

If MetPy is added, retain its BSD-3-Clause license notice and pin the version.
No new package is needed for this research note.

Source:

- [NOAA copyright information](https://sos.noaa.gov/copyright/)
