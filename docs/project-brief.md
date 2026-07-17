| **Document type** | Initial project brief for developer handover |
|----|----|
| **Prepared** | 30 May 2026 |
| **Target completion** | Usable beta by mid-August 2026; final hardening by end-August 2026 |
| **Delivery model** | Agile execution with 2-week Takts, Scrum review, and retrospective at each Takt end |

<table>
<colgroup>
<col style="width: 100%" />
</colgroup>
<thead>
<tr>
<th><p><strong>Critical milestone: initial UI by mid-June
2026</strong></p>
<p>By 15 June 2026 the project must have a locally hosted user interface
with visible forecast cards and enough working structure to demonstrate
the product direction. It can use mock or manually loaded early data,
but it must run locally and show the intended forecast outputs.</p></th>
</tr>
</thead>
<tbody>
</tbody>
</table>

# 1. Project Objective

Build a local-server forecasting application that identifies promising
paragliding cross-country days in Bulgaria and warns users at least 1
day before the opportunity. The system should learn from historical good
and record flights, especially 100 km+ flights, and compare those days
against the forecast and atmospheric conditions that existed at the
time.

- **Primary outcome:** a working decision-support tool that ranks
  upcoming days for selected Bulgarian locations.

- **Initial geography:** Bulgaria, with the architecture designed so the
  same model and data pipeline can later be extended to other countries
  or sites.

- **Forecast purpose:** identify days with high XC potential, not
  replace pilot judgment, official aviation weather, or safety
  decision-making.

# 2. Product Concept

The application should combine historical flight evidence with
atmospheric forecast features. A strong historical flight day becomes a
labeled example; the matching historical weather, forecast, and sounding
profile becomes the explanatory context. The model then scans new
forecast days for similar patterns and raises a warning when the day
resembles historically successful XC conditions.

<table>
<colgroup>
<col style="width: 100%" />
</colgroup>
<thead>
<tr>
<th><p><strong>Core hypothesis</strong></p>
<p>Exceptional XC days share recognizable signatures: usable cloudbase,
adequate thermal strength, manageable winds, favorable route alignment,
limited overdevelopment, and suitable humidity/stability profiles. The
product should expose those signals clearly rather than acting as a
black box.</p></th>
</tr>
</thead>
<tbody>
</tbody>
</table>

# 3. Initial Geographic Scope

The first version should focus on the following Bulgarian locations and
regions. Exact coordinates, launch aliases, and catchment radius should
be confirmed in the kickoff backlog before automated data collection
begins.

| **Initial location** | **Modeling scope** | **Notes** |
|----|----|----|
| Sofia - Vitosha | Kominite launch / Vitosha area | High-priority Sofia region site; useful for local pilot adoption. |
| Zlatitsa | Sredna Gora / Balkan corridor influence | Important XC trigger area and route starter. |
| Sopot | Central Balkan launch area | Known high-volume Bulgarian XC site; likely richer historical data. |
| Nevsha | Northeast Bulgaria | Flatland and ridge/thermal patterns; useful regional contrast. |
| Shumen | Northeast Bulgaria | Potentially relevant for flatland distance and convergence days. |
| Pastrona | Site/area to confirm during kickoff | Name, coordinates, and radius should be confirmed before ingestion. |
| Dobrich region | Regional forecast area around Dobrich | Flatland XC potential; may need regional rather than single-launch modeling. |

# 4. Data Collection Scope

## 4.1 Flight Records

The project needs a historical dataset of good and record flights for
the target regions. The developer should start with 100 km+ flights and
keep labels for 200 km+ and 300 km+ thresholds so that the model can
later learn different levels of XC potential.

- Preferred sources: XCContest.org and SkyNomad forum; pilot-provided
  IGC tracks or manually confirmed records can be added later.

- Collect date, source URL, launch/region, distance, track link/file
  when available, route type, pilot/source name when permitted, and
  quality notes.

- Respect source terms of use, rate limits, and attribution
  requirements. Use caching and manual validation for the first data
  sample.

- Normalize site names and decide whether each flight belongs to a
  launch, a nearby launch cluster, or a broader region such as Dobrich.

## 4.2 Historical Forecasts and Weather Features

Historical forecast availability is a major technical dependency. The
developer should perform an early spike to identify reliable archives
for the same dates as the historical flights. If exact historical
forecasts are not accessible, reanalysis data can be used as a practical
baseline, while keeping the architecture open for forecast-archive
replacement.

- Candidate data types: archived numerical weather model runs, ERA5 or
  similar reanalysis, surface observations, satellite/radar context
  where available, and sounding data.

- Important features: cloudbase, boundary layer height, thermal
  strength, wind speed/direction by altitude, wind shear, humidity
  profile, lapse rate, CAPE, CIN, cloud cover, precipitation, pressure
  pattern, and convergence indicators.

- Sounding diagrams should be supported conceptually. Prefer parsing
  underlying sounding data where possible; image-only sounding diagram
  reading can be a later enhancement if the raw data is unavailable.

# 5. Forecast Outputs and UI Requirements

The user interface should run from a local server and provide a quick
daily view of XC potential. It must be useful even before the final
model is mature, because early demos will validate the workflow and the
information design.

| **Output** | **Developer requirement** | **Display expectation** |
|----|----|----|
| Cloudbase height | Estimated cloudbase or usable thermal top for each site/date. | Meters MSL and/or AGL, with confidence. |
| 100+ km chance | Probability that the day supports at least one 100 km+ XC flight from/near the region. | Percent and simple signal label. |
| 200+ km chance | Probability of a 200 km+ XC opportunity. | Percent; likely sparse-data aware. |
| 300+ km chance | Probability of exceptional long-distance potential. | Percent; conservative until enough examples exist. |
| Overdevelopment risk | Chance that convection, cloud spread, storms, or precipitation reduce flyability/safety. | Low/medium/high plus main drivers. |
| Lead-time alert | User warning when tomorrow or a later day crosses configured thresholds. | Minimum 1 day before the expected opportunity. |

## Mid-June UI Minimum

- A local server starts with a documented command and opens a working
  web UI.

- The UI includes a site selector covering the initial Bulgarian
  locations and a forecast date selector.

- Dashboard cards exist for cloudbase, 100+/200+/300+ chances, and
  overdevelopment risk.

- A simple table or panel shows the underlying forecast inputs used for
  the displayed result.

- If model values are mock, manual, or early baseline values, the UI
  must label them clearly.

# 6. Suggested Technical Direction

The implementation choices should stay pragmatic. The priority is a
working, inspectable pipeline and UI by mid-June, then a progressively
better model by August.

- **Backend:** Python FastAPI or similar local API server; use clear
  service boundaries for ingestion, feature generation, predictions, and
  alerts.

- **Data stack:** pandas, xarray/netCDF tools where needed, SQLite for
  MVP storage; move to PostgreSQL only if the data volume or querying
  requires it.

- **Modeling:** start with transparent baselines and tree-based models
  such as scikit-learn or LightGBM before considering more complex
  methods.

- **Frontend:** React/Vite, Svelte, or a lightweight server-rendered UI
  are acceptable; choose the option that gives the fastest reliable
  dashboard.

- **Version control:** use a Git repository with readable README, setup
  instructions, and issue references linked to the Jira-like backlog.

- **AI assistance:** the developer is encouraged to use coding AI agents
  such as Codex or Claude Code for scaffolding, scraper prototypes,
  tests, documentation, and refactoring. AI-generated code must still be
  reviewed, tested, and committed deliberately.

# 7. Agile Delivery Plan

Dates below assume kickoff around 1 June 2026. Each Takt is 2 weeks long
and ends with a demo/review, acceptance check, retrospective, and
payment for the accepted delivery. The mid-August target should produce
a usable beta; the final August window is reserved for hardening and
handover.

| **Takt** | **Dates 2026** | **Delivery theme** | **Acceptance focus** |
|----|----|----|:--:|
| Takt 1 | 2 Jun - 15 Jun | Initial local-server UI and app skeleton | Local server starts reliably; site selector and forecast date are visible; first dashboard cards exist for cloudbase, XC chances, and overdevelopment risk; values may be mock or manually loaded but must be clearly marked. |
| Takt 2 | 16 Jun - 29 Jun | Flight data ingestion MVP | First validated dataset from XCContest and/or SkyNomad for priority sites; source URLs, dates, distances, launch region, and 100/200/300 km labels stored. |
| Takt 3 | 30 Jun - 13 Jul | Historical weather and sounding ingestion | Working pipeline for historical forecast or reanalysis features; sounding data handling defined; sample joined dataset connects flights to weather features. |
| Takt 4 | 14 Jul - 27 Jul | Prediction MVP | Baseline model produces cloudbase, XC probability bands, and overdevelopment risk per site/date; UI displays model confidence and top drivers. |
| Takt 5 | 28 Jul - 10 Aug | Alerting and validation beta | At least one alert channel or daily watchlist works; basic backtest/validation report shows how the model performed on known historical days. |
| Takt 6 | 11 Aug - 24 Aug | Hardening, documentation, and handover | Install/run instructions, data refresh instructions, known limitations, and handover demo are complete; end-August buffer remains for fixes. |

# 8. Project Management and Ways of Working

- All work should be tracked in a Jira-like environment with backlog
  items, priorities, acceptance criteria, and delivery screenshots or
  notes.

- Each Takt should begin with a short planning session and end with a
  review/demo plus retrospective.

- Bugs and technical risks discovered during a Takt should be captured
  immediately, not hidden until the retrospective.

- Payments are processed via Revolut after the Takt delivery is
  accepted.


# 9. Definition of Done

- The feature runs locally from documented commands on a clean checkout.

- The UI or API behavior is demonstrated during the Takt review.

- Data fields and assumptions are documented enough for another
  developer to continue the work.

- Acceptance criteria in the Jira-like ticket are met or explicitly
  carried forward by agreement.

- Basic tests, validation scripts, or reproducible checks are included
  for data ingestion and model output where practical.

- Known limitations are documented honestly, especially around sparse
  data, historical forecast availability, and safety interpretation.

# 10. Testing and Validation

Testing should be treated as part of every Takt delivery, not as a final
August activity. The goal is to keep the product trustworthy while the
data pipeline, model, and UI are still evolving.

- **Automated tests:** unit tests for parsers, feature calculations,
  threshold logic, forecast-card transformations, and alert rules.

- **Ingestion validation:** tests using frozen sample pages/files from
  XCContest, SkyNomad, weather archives, and sounding sources so scraper
  or parser changes are detectable.

- **Data quality checks:** duplicate detection, date/timezone
  consistency, coordinate sanity checks, missing-value thresholds,
  distance-band labels, and source traceability.

- **Model validation:** backtesting on historical flight days, with
  separate reporting for 100 km+, 200 km+, and 300 km+ labels; include
  calibration checks and false-positive/false-negative examples.

- **UI testing:** basic browser checks for the local server, site
  selector, date selector, forecast cards, loading/error states, and
  clear labels for mock, baseline, real, and missing data.

- **Alert testing:** tests proving alerts are generated at least 1 day
  before a qualifying forecast day and are not duplicated unnecessarily.

- **Review evidence:** each Takt review should include test output,
  screenshots, or a short validation note linked to the relevant
  Jira-like ticket.

| **Test area** | **Minimum expectation** | **When required** |
|----|----|----|
| Data ingestion | Sample-based parser tests and schema checks for every supported source. | From Takt 2 onward |
| Forecast features | Repeatable checks for calculated weather/sounding features and units. | From Takt 3 onward |
| Model output | Backtest report with metrics, confidence notes, and known limitations. | From Takt 4 onward |
| Local UI | Browser smoke test for the dashboard and visible forecast outputs. | From Takt 1 onward |
| Alerts | Threshold and timing tests for 1-day-minimum warning behavior. | From Takt 5 onward |

# 11. Initial Data Model

The following schema is only a starting point. The developer should
refine it after the first ingestion spike, but the MVP should preserve
source traceability and make it easy to join flight days to weather
features.

| **Dataset/table** | **Representative fields** |
|----|----|
| flight_records | flight_id, date, pilot/source name, source_url, launch_area, start_coordinates, landing_coordinates, distance_km, duration, track_url/file, distance_band |
| weather_features | date, model_run_time, site_id, cloudbase_m, boundary_layer_height_m, thermal_strength, wind_by_altitude, humidity_profile, CAPE, CIN, lapse_rate, precipitation, cloud_cover, source |
| soundings | date_time, station_or_grid_point, raw_sounding_data, parsed_levels, skew_t_image_path_if_used, quality_flag |
| predictions | date, site_id, generated_at, cloudbase_prediction_m, p_100km, p_200km, p_300km, overdevelopment_risk, confidence, top_drivers_json |
| alerts | alert_id, date_for_forecast, site_id, threshold_crossed, message, created_at, delivery_channel, acknowledged |

# 12. Risks and Open Questions

- **Historical forecasts:** exact forecast archives may be hard to
  obtain; reanalysis may be needed as a baseline.

- **Source access:** XCContest and forum scraping must respect
  permissions, rate limits, and attribution requirements.

- **Sparse labels:** 200 km+ and 300 km+ flights may be rare, so
  probability estimates must show confidence and avoid false precision.

- **Location definitions:** coordinates, launch aliases, and catchment
  radius must be agreed early, especially for Pastrona and the Dobrich
  region.

- **Alert channel:** the initial alert mechanism should be agreed before
  Takt 5: email, Telegram, local dashboard watchlist, or another
  channel.

- **Safety framing:** the product must be presented as forecast decision
  support, not a guarantee that a day is safe or flyable.

# 13. Immediate Next Steps

1.  Create the repository, local server skeleton, and first UI dashboard
    route.

2.  Confirm launch coordinates, region radii, and spelling/aliases for
    all target locations.

3.  Open Jira-like epics for UI, flight data ingestion, weather/sounding
    ingestion, modeling, alerting, and documentation.

4.  Run a data-source spike for XCContest, SkyNomad, and historical
    weather archives.

5.  Prepare the mid-June demo around the working local UI, even if the
    first values are early baselines.

# Appendix: Mid-June Demo Checklist

- Can the developer start the app locally in less than 5 minutes from
  the README?

- Can a user select Sofia - Vitosha, Zlatitsa, Sopot, Nevsha, Shumen,
  Pastrona, and Dobrich region?

- Does the page show cloudbase, 100+/200+/300+ chances, and
  overdevelopment risk?

- Does the UI distinguish between real, baseline, mock, and missing
  data?

- Is there at least one screenshot or short demo recording linked in the
  Takt review ticket?

- Are the next data/model tasks already written for Takt 2?
