# Web dashboard

## Status

The home dashboard reads published summaries and dates through the Express
API. Its four regions share one viewport with the header at desktop and
compact sizes. The map and native location control use the same API catalog.
The detailed forecast view is accessible in explicit demo mode.

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

The browser client exposes the site catalog, batched daily summaries, and
five-day preview endpoints. Successful JSON is parsed with the shared Zod
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

In SQLite mode the overview action is disabled and comparisons are static
cards. To demonstrate detail navigation, start the combined development
servers from the repository root with `FORECAST_DATA_MODE=mock npm run dev`
on macOS or Linux. In PowerShell set `$env:FORECAST_DATA_MODE = "mock"` before
running `npm.cmd run dev`.

`/forecast?site=<slug>&date=YYYY-MM-DD` keeps selection in the same canonical
URL parameters as the dashboard. Its native site/date selectors auto-fetch on
change; there are no date-navigation arrows or confirmation control. `All sites`
returns to the dashboard with the same selection.

The desktop route is a fixed-height, no-page-scroll grid: outputs and a
selected-site Leaflet view occupy the first row, mock forecast inputs and
top-driver strings the second, then a static five-output `Unchanged`
previous-run placeholder. It deliberately has no previous-run API field. On
narrow screens the route stacks and scrolls normally. All seven confirmed-site map pins remain clickable; the detail viewport begins focused on the selected site and adds a north-up compass.

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
  responsive layout and selected Leaflet labels. The mock smoke covers the
  detailed forecast, its outputs, inputs and drivers, and the return to `All sites`.

Playwright runs headlessly by default. `test:browser:headed` shows Chromium and
`test:browser:ui` offers interactive debugging. Failure-only traces and
screenshots are written to ignored test-artifact folders; no visual baselines or
pixel comparisons are maintained. OSM tiles are deliberately blocked in this
suite, so core local forecast behaviour does not depend on the public tile
service. Manual review still owns real tile rendering, pan/zoom, label
collisions, focus appearance, desktop/narrow visual fidelity, and browser
console review.
