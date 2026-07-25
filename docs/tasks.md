## Epics

| Epic ID | Epic | Description | Priority |
|----|----|----|----|
| E-001 | Local UI / Dashboard | Build the locally hosted user interface for site/date selection, forecast cards, and forecast input visibility. | Highest |
| E-002 | Flight Data Collection | Collect and normalize historical 100 km+, 200 km+, and 300 km+ flights for the Bulgarian target regions. | High |
| E-003 | Historical Forecast Data | Find and ingest historical forecast, reanalysis, weather, and sounding data for matching historical flight dates. | High |
| E-004 | Prediction Model | Create transparent baseline and progressively stronger models for XC distance probability, cloudbase, and overdevelopment. | High |
| E-005 | Alerts | Warn users at least 1 day before a forecast day crosses configured XC opportunity thresholds. | Medium |
| E-006 | Testing and Validation | Add automated tests, data quality checks, model backtests, browser smoke tests, and review evidence per Takt. | High |
| E-007 | Documentation / Handover | Maintain setup, run, data refresh, known limitations, and handover documentation. | Medium |


## Tasks

| ID | Type | Summary | Epic | Takt | Status | Priority | Owner | Start Date | Due Date | Labels | Description | Est. Hours (Junior) | Est. Cost @ €15/h |
|----|----|----|----|----|----|----|----|----|----|----|----|----|----|
| T-001 | Task | Create project repository and README skeleton | Documentation / Handover | Takt 1 | Done | Highest |  | 46218.0 | 46219.0 | setup,repo,readme | Create the initial repository structure, README, setup notes, and clear run commands for local development. | 6.0 | 90.0 |
| T-002 | Task | Create local server skeleton | Local UI / Dashboard | Takt 1 | Done | Highest |  | 46218.0 | 46221.0 | local-server,backend,setup | Set up a local backend or frontend dev server that starts with a documented command. | 12.0 | 180.0 |
| T-003 | Task | Create initial dashboard route | Local UI / Dashboard | Takt 1 | Review | Highest |  | 46220.0 | 46224.0 | ui,dashboard | Build the first screen for the forecast dashboard rather than a landing page. | 10.0 | 150.0 |
| T-004 | Task | Add site selector for initial Bulgarian locations | Local UI / Dashboard | Takt 1 | Review | Highest |  | 46223.0 | 46226.0 | ui,locations | Include Sofia - Vitosha (Kominite), Zlatitsa, Sopot, Nevsha, Shumen, Pastrina, and Dobrich region. | 6.0 | 90.0 |
| T-005 | Task | Add forecast date selector | Local UI / Dashboard | Takt 1 | Review | High |  | 46225.0 | 46227.0 | ui,date-selector | Allow the user to select the forecast date or review upcoming forecast days. | 4.0 | 60.0 |
| T-006 | Task | Create detailed site/date forecast view | Local UI / Dashboard | Takt 1 | Review | Highest |  | 46226.0 | 46230.0 | ui,forecast-details | Build the page opened from the dashboard's detailed-forecast action and show the full cloudbase, 100+ km, 200+ km, 300+ km, overdevelopment, provenance, and driver information for one site/date. | 10.0 | 150.0 |
| T-007 | Task | Label mock, baseline, real, and missing data in the UI | Local UI / Dashboard | Takt 1 | Review | High |  | 46228.0 | 46231.0 | ui,data-status | Make it clear when displayed values are mock, manually loaded, baseline, real, or unavailable. | 4.0 | 60.0 |
| T-008 | Task | Create Takt 1 browser smoke test | Testing and Validation | Takt 1 | Review | High |  | 46230.0 | 46231.0 | testing,ui-smoke | Add a simple check that the local dashboard loads and displays the required forecast cards. | 6.0 | 90.0 |
| T-009 | Task | Confirm launch coordinates and region radii | Flight Data Collection | Takt 1 | To Do | High |  | 46218.0 | 46231.0 | locations,data-quality | Confirm exact coordinates, aliases, and catchment radius for every target location, especially Pastrina and Dobrich region. | 8.0 | 120.0 |
| T-010 | Task | Research XCContest access and data fields | Flight Data Collection | Takt 2 | To Do | High |  | 46232.0 | 46234.0 | xccontest,research | Identify available fields, source URLs, limitations, attribution needs, and rate-limit considerations for XCContest data. | 8.0 | 120.0 |
| T-011 | Task | Research SkyNomad forum access and data fields | Flight Data Collection | Takt 2 | To Do | Medium |  | 46232.0 | 46235.0 | skynomad,research | Identify usable SkyNomad forum sources, search strategy, data fields, and manual validation needs. | 6.0 | 90.0 |
| T-012 | Task | Implement flight record schema | Flight Data Collection | Takt 2 | To Do | High |  | 46235.0 | 46238.0 | schema,flights | Create storage for flight_id, date, source_url, launch_area, coordinates, distance_km, duration, track link, and distance band. | 10.0 | 150.0 |
| T-013 | Task | Ingest first validated flight sample | Flight Data Collection | Takt 2 | To Do | High |  | 46238.0 | 46243.0 | data-ingestion,flights | Collect the first manually verified or automated sample of historical flights for priority sites. | 18.0 | 270.0 |
| T-014 | Task | Add duplicate and source traceability checks for flights | Testing and Validation | Takt 2 | To Do | High |  | 46241.0 | 46245.0 | testing,data-quality | Detect duplicate flights and preserve source URLs and quality notes for every record. | 8.0 | 120.0 |
| T-015 | Task | Create parser fixtures for flight sources | Testing and Validation | Takt 2 | To Do | Medium |  | 46242.0 | 46245.0 | testing,fixtures,parsers | Save frozen sample pages or files so parser changes can be tested without relying on live pages. | 6.0 | 90.0 |
| T-016 | Task | Research historical forecast archive options | Historical Forecast Data | Takt 3 | To Do | High |  | 46246.0 | 46249.0 | weather,research | Identify whether exact historical model forecasts are available; define fallback reanalysis source if not. | 14.0 | 210.0 |
| T-017 | Task | Define weather feature set and units | Historical Forecast Data | Takt 3 | To Do | High |  | 46247.0 | 46251.0 | weather,features | Document cloudbase, boundary layer, thermal strength, wind by altitude, humidity, lapse rate, CAPE, CIN, cloud cover, precipitation, and source fields. | 8.0 | 120.0 |
| T-018 | Task | Implement weather feature schema | Historical Forecast Data | Takt 3 | To Do | High |  | 46250.0 | 46254.0 | schema,weather | Create storage for site/date/model run time and normalized atmospheric forecast or reanalysis features. | 12.0 | 180.0 |
| T-019 | Task | Implement sounding data handling approach | Historical Forecast Data | Takt 3 | To Do | Medium |  | 46252.0 | 46256.0 | soundings,parser | Prefer parsing raw sounding data; document how image-only sounding diagrams could be handled later. | 16.0 | 240.0 |
| T-020 | Task | Join sample flight days to weather features | Historical Forecast Data | Takt 3 | To Do | High |  | 46255.0 | 46259.0 | data-join,features | Produce a joined sample dataset connecting historical flights with weather/sounding context. | 18.0 | 270.0 |
| T-021 | Task | Add feature calculation tests | Testing and Validation | Takt 3 | To Do | High |  | 46256.0 | 46259.0 | testing,weather,data-quality | Test calculated weather and sounding features, units, missing values, and date/timezone alignment. | 10.0 | 150.0 |
| T-022 | Task | Create baseline cloudbase prediction | Prediction Model | Takt 4 | To Do | High |  | 46260.0 | 46264.0 | modeling,cloudbase | Implement an initial transparent method for cloudbase or usable thermal top estimation. | 16.0 | 240.0 |
| T-023 | Task | Create baseline XC probability model | Prediction Model | Takt 4 | To Do | High |  | 46261.0 | 46267.0 | modeling,xc-probability | Produce probability bands for 100+ km, 200+ km, and 300+ km potential per site/date. | 24.0 | 360.0 |
| T-024 | Task | Create overdevelopment risk baseline | Prediction Model | Takt 4 | To Do | High |  | 46264.0 | 46269.0 | modeling,overdevelopment | Estimate low/medium/high overdevelopment risk using humidity, instability, clouds, and precipitation features. | 18.0 | 270.0 |
| T-025 | Task | Show model confidence and top drivers in UI | Local UI / Dashboard | Takt 4 | To Do | Medium |  | 46267.0 | 46271.0 | ui,explainability | Display confidence/limitations and top forecast drivers so the UI is not a black box. | 12.0 | 180.0 |
| T-026 | Task | Backtest model against known historical days | Testing and Validation | Takt 4 | To Do | High |  | 46268.0 | 46273.0 | testing,backtesting,model-validation | Create a report for 100+ km, 200+ km, and 300+ km labels, including false positives and false negatives. | 20.0 | 300.0 |
| T-027 | Task | Define alert thresholds and alert message format | Alerts | Takt 5 | To Do | Medium |  | 46274.0 | 46276.0 | alerts,thresholds | Agree thresholds for site/date alerts and create a clear user-facing message format. | 6.0 | 90.0 |
| T-028 | Task | Implement daily watchlist or first alert channel | Alerts | Takt 5 | To Do | High |  | 46276.0 | 46281.0 | alerts,notifications | Build at least one alert mechanism: dashboard watchlist, email, Telegram, or another agreed channel. | 18.0 | 270.0 |
| T-029 | Task | Ensure alerts are generated minimum 1 day before opportunity | Alerts | Takt 5 | To Do | High |  | 46280.0 | 46284.0 | alerts,timing | Verify alerts can be created at least 1 day before the forecast opportunity date. | 8.0 | 120.0 |
| T-030 | Task | Prevent duplicate alerts for the same threshold/day | Alerts | Takt 5 | To Do | Medium |  | 46281.0 | 46285.0 | alerts,deduplication | Avoid repeated duplicate warnings for the same site/date/threshold unless explicitly refreshed. | 6.0 | 90.0 |
| T-031 | Task | Add alert threshold and timing tests | Testing and Validation | Takt 5 | To Do | High |  | 46283.0 | 46287.0 | testing,alerts | Test alert generation timing, threshold crossing, and duplicate prevention. | 10.0 | 150.0 |
| T-032 | Task | Prepare beta validation demo | Documentation / Handover | Takt 5 | To Do | High |  | 46284.0 | 46287.0 | demo,beta | Prepare a demo showing data, model outputs, UI cards, alert/watchlist behavior, and known limitations. | 8.0 | 120.0 |
| T-033 | Task | Write install and run instructions | Documentation / Handover | Takt 6 | To Do | High |  | 46288.0 | 46291.0 | readme,setup | Document clean checkout setup, required commands, configuration, and local server startup. | 8.0 | 120.0 |
| T-034 | Task | Write data refresh instructions | Documentation / Handover | Takt 6 | To Do | High |  | 46290.0 | 46294.0 | documentation,data-refresh | Document how to update flight records, weather data, soundings, and prediction outputs. | 8.0 | 120.0 |
| T-035 | Task | Document known limitations and safety framing | Documentation / Handover | Takt 6 | To Do | High |  | 46293.0 | 46296.0 | documentation,safety,limitations | Explain sparse data, historical forecast limitations, confidence, and that the tool is decision support rather than a safety guarantee. | 6.0 | 90.0 |
| T-036 | Task | Clean up project backlog before handover | Documentation / Handover | Takt 6 | To Do | Medium |  | 46296.0 | 46298.0 | tracker,handover | Close completed tickets, carry forward agreed items, and leave future-location expansion ideas in backlog. | 4.0 | 60.0 |
| T-037 | Task | Final handover demo and retrospective | Documentation / Handover | Takt 6 | To Do | High |  | 46298.0 | 46301.0 | demo,retrospective,handover | Run final review covering features, tests, documentation, risks, and remaining post-August work. | 6.0 | 90.0 |

## Takts

| Takt | Start | End | Delivery Theme | Acceptance Focus |
|----|----|----|----|----|
| Takt 1 | 46218.0 | 46231.0 | Initial local-server UI and app skeleton | Initial UI must be visible by the end of Takt 1: 2026-07-28. |
| Takt 2 | 46232.0 | 46245.0 | Flight data ingestion MVP | First validated dataset from XCContest and/or SkyNomad. |
| Takt 3 | 46246.0 | 46259.0 | Historical weather and sounding ingestion | Joined sample dataset connects flights to weather features. |
| Takt 4 | 46260.0 | 46273.0 | Prediction MVP | Baseline model and visible confidence/top drivers. |
| Takt 5 | 46274.0 | 46287.0 | Alerting and validation beta | Daily watchlist or first alert channel plus backtest report. |
| Takt 6 | 46288.0 | 46301.0 | Hardening, documentation, and handover | Install/run docs, known limitations, and handover demo. |
