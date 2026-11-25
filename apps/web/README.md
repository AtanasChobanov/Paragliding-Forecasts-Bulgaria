# Web dashboard

## Status

The home dashboard reads published summaries and dates through the Express
API. Its four regions share one viewport with the header at desktop and
compact sizes. The map and native location control use the same API catalog.
The detailed forecast view reads the selected SQLite publication and also
supports explicit synthetic demo mode.

## Responsibilities

- Render the daily forecast dashboard.
- Provide the site and forecast-date selectors.
- Display cloudbase, 100+/200+/300+ chances, and overdevelopment risk.
- Label every value as mock, manual, baseline, real, or unavailable.
- Handle loading, empty, and API error states accessibly.

The web app must not calculate model probabilities or read databases directly.
It consumes versioned HTTP contracts from `@paragliding-forecasts/contracts`.

## Accepted stack

- React
- Vite
- TypeScript in strict mode
- React Router with `site` and `date` URL search parameters
- TanStack Query for API/server state
- native `fetch` validated with `@paragliding-forecasts/contracts`
- SCSS Modules, CSS custom-property theme tokens, and self-hosted Inter
- Leaflet through React Leaflet with OpenStreetMap raster tiles for the local
  MVP
- Vitest, React Testing Library, and MSW for unit/component/API-client tests
- Playwright Test with Chromium for real-browser smoke coverage

## Current layout

```text
apps/web/
|-- index.html
|-- src/
|   |-- app/
|   |   |-- AppProviders.tsx
|   |   |-- app-routes.tsx
|   |   `-- query-client.ts
|   |-- config/runtime-config.ts
|   |-- components/
|   |   |-- app-header/
|   |   |-- content-state/
|   |   `-- dashboard-panel/
|   |-- features/dashboard/
|   |   |-- components/        # Overview, comparisons, map, and date strip
|   |   |-- dashboard-compatibility-error.ts
|   |   |-- dashboard-error-presentation.ts
|   |   |-- dashboard-query-options.ts
|   |   |-- dashboard-search-params.ts
|   |   |-- dashboard-summary-selection.ts
|   |   |-- forecast-presentation.ts
|   |   `-- map-provider.ts
|   |-- routes/dashboard/
|   |   `-- dashboard-route.tsx
|   |-- services/api/
|   |   |-- api-client.ts
|   |   |-- api-errors.ts
|   |   `-- dashboard-api.ts
|   |-- styles/
|   |   |-- _mixins.scss
|   |   |-- _tokens.scss
|   |   `-- globals.scss
|   |-- App.module.scss
|   |-- App.tsx
|   |-- main.tsx
|   `-- vite-env.d.ts
|-- test/
|   |-- component/
|   |-- integration/
|   |-- support/
|   `-- unit/
|-- package.json
|-- tsconfig.json
|-- tsconfig.node.json
|-- vite.config.ts
`-- vitest.config.ts
```

Prefer feature-oriented folders once the UI grows; avoid a single global
`components` folder containing unrelated domain behavior.

## Commands

Run from the repository root:

```powershell
npm.cmd run dev:web
npm.cmd run build --workspace @paragliding-forecasts/web
npm.cmd run typecheck --workspace @paragliding-forecasts/web
npm.cmd run test --workspace @paragliding-forecasts/web
npm.cmd run test:coverage --workspace @paragliding-forecasts/web
npm.cmd run test:browser:install
npm.cmd run test:browser
npm.cmd run test:browser:headed
npm.cmd run test:browser:ui
```

Use `npm.cmd run dev` to supervise the API and web servers together. Vite uses
`strictPort: true`, so an occupied configured port fails instead of silently
moving the dashboard to another origin. The test scripts run meaningful
API-client, query, provider, and runtime-configuration tests.

## Configuration

Browser-exposed variables must use Vite's `VITE_` prefix. Never place secrets
in web environment variables because they are bundled into client code.

Current variables:

- `VITE_API_BASE_URL` - absolute HTTP(S) base URL of the local Express API;
  validated before React renders and normalized without a trailing slash
- `WEB_PORT` - Vite development port, default `5173`; changing it requires the
  exact matching `CORS_ORIGIN`

Standalone web `dev`, `build`, `typecheck`, Vitest, and browser-test commands
build the shared contracts first. The combined root `dev` supervisor builds
contracts and database workspaces before starting the API and web watchers.

## API and query behavior

The browser client exposes the site catalog, batched daily summaries,
five-day preview and single-site/date detail endpoints. Successful JSON is parsed with the shared Zod
response schemas. Failures remain distinguishable as network errors, validated
HTTP Problem Details, or incompatible successful responses. TanStack Query
forwards cancellation and retries one network or HTTP 5xx failure. Dashboard
requests use the validated sites, days and summary results cached for the
page session. Reload the page to pick up new publications or the next Sofia
calendar day. Focus, reconnect and remount do not trigger background refresh.

## URL selection behavior

The canonical dashboard URL is `/?site=<site-slug>&date=YYYY-MM-DD`. The route
chooses the minimum catalog ID for an unknown site and waits for the selected
site's days response. A requested date stays selected when its publication is
available. Otherwise the route chooses Today, then the nearest available
future day, then the nearest available past day. It replaces the URL after
validation. Deliberate site/date changes create history entries. With no
published dates, the URL contains just the site and the map remains usable.

Other Locations are the next three catalog entries after the minimum ID.
A single summary request deduplicates those comparison sites and the selected
site for the selected date.

## Forecast presentation behavior

Dashboard percentages display up to two decimals, with `<0.01%` for tiny
positive values and `0%` for a stored zero. Cloudbase and conditional LCL
display whole metres MSL. Blue, Other cloud, Uncertain and Unavailable are
separate states. The compact confidence meters refer to the 100+ km chance.
A missing P100 leaves the other metrics visible and omits the chance bar.

Hover over, focus or press the information button to inspect a card's issue
metadata and each metric's status, confidence and limitations. Press to keep
the panel open. Escape or an outside press dismisses it. SQLite shows the GFS
cycle in UTC and the publication time in Sofia. Demo panels identify the
mock provider and version.

## Detailed forecast view

`/forecast?site=<slug>&date=YYYY-MM-DD` opens from the overview or an available
comparison card in both SQLite and mock mode. `All sites` returns with the
same site/date. Native selectors fetch on change. A valid direct date stays
selected, even outside the five-day preview, and is added to the selector.
An unpublished exact date stays visible with an empty state. Only entirely
unpublished preview dates are disabled; missing P100 does not disable a day.
Missing/invalid dates choose available Today, then nearest future, then nearest
past. An empty preview does not request an arbitrary date.

The toolbar and content fit one viewport, including at compact sizes and
125% text in the tested viewports. From 70rem, the main row and chart use
70:30 of the remaining height. The main row has 1.08:0.92 columns: summary
left, inputs and explanations stacked right. Compact layouts allocate
28:20:24:28 to summary, inputs, explanations and chart. The detail route has no
map, tile requests or previous-run placeholder.

The detail summary stacks three compact 100+/200+/300+ km probability rows,
each with its percentage, progress bar, status, own confidence and information.
Cloudbase and OD risk share two equal columns below those rows. Cloudbase shows
metres MSL for the selected daily maximum. Its information contains the matching signed site/model AGL values; no AGL row appears in the card.
Probability confidence levels follow their meter immediately; the weather cards
retain their Confidence prefix. Publication metadata uses the GFS cycle and
the actual publication time in Sofia. Detail information uses compact pages;
hover/focus opens it, press pins it, and Escape/outside press closes it.
The summary's common information uses the home dashboard's labeled metadata
layout, without per-metric evidence. Height-reference and cloud-formation
explanations live in the information button beside the Hourly cloudbase time range;
the cloudbase result information retains its matching site/model AGL readings. Each
output metric shows its explanation and limitations together, with readable descriptions of published flags and no
duplicate status/confidence prefix or pagination. Hourly chart information retains
its existing pagination. Home information is unchanged.

Inputs default to `XC inputs / Surface temperature`. All 67 policy fields are
reachable through group selectors and measured pagination (one through six
rows). OD/cloudbase modes use a synchronized hour selector. Input information
uses one labeled metadata view without repeating the row name or displayed value.
Exact canonical values appear only when they add precision or use a different unit.
Quality, statistics, source records, true intervals and layer bounds remain available.
Canonical values,
quality, provenance and true intervals remain available in row information.
Display conversions include K to °C, Pa to hPa, kg/kg to g/kg and K/km to
°C/km; small magnitudes use three-significant-digit scientific notation.
Unavailable inputs preserve their reasons, including outside-OD slots at 20:00.

Detail selectors share the location/date controls' primary border, leading icon
and chevron. A shared `Pagination` component serves inputs, drivers, information
popovers and chart tooltips: arrow buttons flank the current page and total
(`1 of 3`), with disabled arrows at the boundaries (`1 of 1` for a single page).
The measured lists recalculate page totals when available space changes.

Explanations have five metric tabs, with the equivalent native select on
compact layouts. Published rank/order and up to three drivers remain intact,
with measured pagination. XC signs mean model direction relative to the
training reference, not causal effects or percentage points. P200 describes
`P(200+ | 100+)`; P300 shows stored pooled support. OD overrides use a warning
symbol and score components show risk points. Cloudbase reasons use neutral
information or uncertainty symbols. Full driver text and ordered exact inputs
remain accessible in structured information: short drivers combine their calculation
and up to three inputs in one view; longer evidence separates the calculation
from inputs grouped by topic. Metadata fields are not split into individual pages.
Long groups can use the viewport and scroll; popup position updates between pages.
Missing SQL equivalents point to the
retained ML artifact, including the full T-022 model column.

The responsive SVG chart uses Recharts (`ComposedChart`, `ResponsiveContainer`,
axes, lines and areas), loaded on demand for the detail plot. Recharts and its
`react-is` peer are web workspace dependencies; keep `react-is` aligned with React.
The root npm override is scoped to Recharts' peer so npm cannot resolve it to
the older `react-is` used by test tooling. Update that override with React.
It uses eleven actual Sofia hours and linear segments.
Solid primary lines/circles denote estimated cloudbase; dashed warning
lines/diamonds denote conditional LCL. Each contiguous numeric segment gets
its own fading gradient. Blue, other cloud, uncertain and missing hours use
separate text/markers in a regime band. Lines never bridge gaps or changes of
numeric type. Isolated numeric hours retain a marker. The daily maximum
outline follows estimated-first selection. No numeric hours produces an
explicit explanation rather than a zero-height curve or a thermal-top claim.

Hover/focus/press an hour for a paginated tooltip with all three height
references, confidence, reason/code, note and matching cloudbase context.
Left/Right and Home/End select hours; Enter/press pins the tooltip for its
page controls. The selected hour synchronizes with OD/cloudbase inputs.
Tooltips use a portal to stay inside the viewport.
Hour ticks use `HH:mm`. The first tooltip page emphasizes MSL, followed by
secondary site/model AGL readings, the shared confidence indicator and an optional
daily-maximum badge. Reasons, hour/regime and exact inputs remain on subsequent
pages. There is no close button: pointer leave dismisses an unpinned tooltip;
Escape or an outside press dismisses a pinned tooltip.
The themed regime band uses Recharts' plot/scale hooks. The adjacent native DOM
hour controls retain all eleven selectable slots, even without numeric heights.
They own keyboard focus, so Recharts' parallel accessibility layer is disabled
to avoid duplicate navigation. The tooltip keeps the shared React pagination.
Line/area animations are disabled to preserve the published values during selection.

Catalog, days and detail have independent errors and explicit Retry controls.
Detail requests are keyed by slug/date and checked for correlation. Changing
site/date clears old evidence and resets panel selections; returning to a
cached date reuses it. No polling or automatic refetch occurs on focus,
reconnect or cached remount. Reload the page for new publications.

## Map behavior and network dependency

The site selector lazy-loads Leaflet and React Leaflet, fits all API coordinates,
and retains normal pointer pan plus visible zoom controls. Scroll-wheel zoom and
map keyboard navigation are disabled so the map cannot trap page scrolling or
keyboard focus. The synchronized native `Location` selector is the complete
keyboard control; map pins are pointer shortcuts using the same URL update
callback. The selected pin differs by size, border, and colour, and viewport
movement respects `prefers-reduced-motion`.

The basemap uses OpenStreetMap Standard raster tiles from
`https://tile.openstreetmap.org/{z}/{x}/{y}.png`. This creates a runtime internet
dependency and is best effort, not an offline or production-SLA tile service.
The URL, linked attribution, maximum zoom, and policy URL are kept in one
provider descriptor. The app does not prefetch or offer offline downloads. If
tiles fail, site labels, the native selector, selected forecast, and an explicit
degraded-map message remain available. Site coordinates were confirmed in T-009.

## Forecast date behavior

The date strip renders exactly the ordered five slots supplied by the selected
site's days response. It has no arrows, pagination, browser-clock expansion, or
historical navigation. `todayDate` from the API owns the visible `Today` state;
`aria-pressed` independently identifies the URL-selected date. Labels are
formatted from numeric date-only parts in UTC so local timezone conversion
cannot move a Sofia calendar date. The strip deliberately omits a separate year
heading and weekday row; non-today cards show only day and month.

Each card exposes its ISO date and an accessible description for P100.
Availability refers to the whole publication. Slots without a publication
stay visible as disabled buttons. A published slot with missing P100 can be
selected to read the remaining metrics.

## Error and accessibility behavior

A sites failure keeps the four-panel shell. Days must load before the home
route requests a summary. A summaries failure leaves the map, location selector
and date strip usable. Compatibility errors identify invalid service
responses and network and HTTP 5xx errors offer Retry where applicable.
The page uses semantic sections, native controls, visible focus rings,
accessible date descriptions and a polite selection announcement.

## Validation and testing

The repository-level `build`, `typecheck`, `lint`, `format:check`, `test`,
`test:coverage`, and `repo:check` commands include this workspace. Web coverage
enforces at least 80% statements, lines, and functions plus 75% branches across
all maintained `src/**/*.{ts,tsx}` files, including files a test never imports.
`test:browser` needs Playwright Chromium and starts fixture API processes on
`3300` and `3301`, with Vite on `5373` and `5374`. The fixtures use explicit
environment values and a fixed Sofia date. The SQLite fixture migrates and
seeds a disposable database. Tests intercept tile requests.

Automated coverage includes:

- API-client tests for URL encoding, success parsing, Problem Details, network
  failure, cancellation, malformed JSON, invalid response shapes, and safe
  non-JSON HTTP fallbacks.
- Query/provider tests for stable keys, cancellation signals, freshness, and
  retry policy.
- Route tests for URL normalization, deep links, history navigation, dependent
  query enabling, request deduplication/reindexing, partial catalogs, empty
  catalogs, independent failures, and stale-selection prevention.
- Unit tests for forecast/date formatting, data-status and confidence summaries,
  and mixed/missing metric behavior.
- Component tests for loading, missing, and error states as the route and
  presentation components are added.
- Component tests for the stable dashboard shell, panel semantics, and reusable
  loading, error, empty, and informational states.
- Component/unit tests for native location selection, fitted map bounds, OSM
  provider metadata, permanent site labels, pin selection, reduced motion, and
  tile-failure degradation.
- Integration tests for sites/days/summaries retry recovery, request IDs,
  compatibility failures, independent-region preservation, stale-selection
  prevention, keyboard date activation, and polite selection announcements.
- Playwright Chromium tests for SQLite outputs, missing slots, issue metadata,
  responsive layout and selected Leaflet labels. Both runtime modes cover detail navigation. SQLite detail tests also cover
  the eight viewport/text settings, mixed regimes, keyboard/touch, hourly
  synchronization, independent Retry and manual refresh behavior.

Playwright runs headlessly by default. `test:browser:headed` shows Chromium and
`test:browser:ui` offers interactive debugging. Failure traces and detail verification
screenshots are written to ignored test-artifact folders; no visual baselines or
pixel comparisons are maintained. OSM tiles are deliberately blocked in this
suite, so core local forecast behaviour does not depend on the public tile
service. Manual review still owns real tile rendering, pan/zoom, label
collisions, focus appearance, desktop/narrow visual fidelity, and browser
console review.
