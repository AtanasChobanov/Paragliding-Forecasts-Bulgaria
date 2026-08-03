# Web dashboard

## Status

The React/Vite workspace is runnable, production-buildable, and backed by a
validated dashboard HTTP/query foundation. The dashboard route coordinates
canonical URL selection and the sites, days, and summaries queries inside a
responsive visual shell with a semantic application header, stable dashboard
panels, reusable content states, self-hosted Inter, and shared theme tokens. The
selected overview now renders validated summary data with explicit status,
confidence, provenance, units, and missing-data semantics. The fixed-order
Other Locations cards retain status, units, and missing-data semantics in a
more compact comparison treatment. The Leaflet site selector now renders all
API coordinates with permanent labels and a synchronized native control. The
five-day selector is rendered from exactly the five API slots. Scoped
failure/retry presentation, request IDs, compatibility errors, live
announcements, focus behavior, reduced motion, and narrow-layout wrapping are
implemented and covered by automated tests. The wide desktop layout now uses
the available viewport height as one fixed dashboard canvas: all four regions
remain visible together and the page itself does not scroll. The header spans
the full viewport independently, while the dashboard body uses a fluid `90vw`
width with fractional columns and viewport-relative rows rather than a fixed
maximum width. Compact widths retain document scrolling because the panels
stack vertically. T-003-T-005 remain in progress until the deliberately
deferred manual browser/visual review is completed.

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
contracts once and then starts the raw API and web watchers.

## API and query behavior

The browser client exposes the site catalog, batched daily summaries, and
five-day preview endpoints. Successful JSON is parsed with the shared Zod
response schemas. Failures remain distinguishable as network errors, validated
HTTP Problem Details, or incompatible successful responses. TanStack Query
forwards cancellation, treats the site catalog as static, uses five-minute
forecast freshness, disables focus refetch, and retries only the first network
or HTTP 5xx failure.

## URL selection behavior

The canonical dashboard URL is `/?site=<site-slug>&date=YYYY-MM-DD`. React
Router search parameters are the only selected-site/date state. Missing,
repeated, unknown, or out-of-strip values are normalized with history replace;
deliberate site and date changes create history entries. Back, Forward, refresh,
and pasted deep links reconstruct the same query selection.

The route explicitly selects the minimum numeric site ID as the catalog
default, waits for the selected site's API-defined Sofia `todayDate` when the
URL date is unusable, and handles an empty catalog. Other Locations are the
next three catalog entries in ascending numeric ID order. Summary requests
deduplicate those comparison entries with the currently selected site.

## Forecast presentation behavior

The selected overview renders 100+/200+/300+ kilometre chances, cloudbase in
metres MSL, and overdevelopment risk. Date-only values are formatted as UTC
calendar labels to avoid a browser-timezone day shift; generation instants are
shown in `Europe/Sofia`. Status labels preserve `mock`, `manual`, `baseline`,
`real`, and `missing` distinctions, while mixed metrics retain per-metric status
and confidence context.

Other Locations remain static comparison cards for the three catalog entries
immediately after the minimum-ID default, ordered by numeric ID. The selected
location is not filtered out when it is one of those cards. Missing summary
items and missing metrics show their reasons without substituting zero. Below
each chance bar, cloudbase and overdevelopment risk use a compact icon-and-value
row without a metric divider, followed by the compact confidence meter. The
full-width detailed-forecast control now links to the selected site/date, and
every Other Locations card is a full-card link to that same route for its site
and the active dashboard date.

## Detailed forecast view

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

Each card exposes its ISO date as the control name and an explicit accessible
description for the 100+ kilometre chance, data status, and confidence. Missing
metrics remain in their original position, stay selectable, and show the API
reason as unavailable rather than zero. The responsive grid changes from five
columns to two and then one without adding horizontal page overflow.

## Error and accessibility behavior

Sites, summaries, days, and tiles own independent states. A sites failure keeps
the stable four-panel shell; a days failure leaves the selected summary usable;
a summaries failure leaves the selector/map and date strip usable; a tile
failure does not become an API error. Retry controls are rendered only for
retryable network and HTTP 5xx failures. HTTP Problem Details request IDs are
shown for support, while malformed or mismatched successful payloads are named
as dashboard/API compatibility errors and are never rendered as trusted data.

The page uses one `h1`, semantic labelled sections, scoped `aria-busy`, one
polite selection announcement, native select/buttons, visible focus rings,
approximately 44-pixel controls, explicit units/status text, and reduced-motion
handling. The date cards expose API today separately from URL selection. One
shared summaries failure creates one alert and one restrained comparison-region
explanation rather than duplicate alert spam.

## Validation and testing

The repository-level `build`, `typecheck`, `lint`, `format:check`, `test`,
`test:coverage`, and `repo:check` commands include this workspace. Web coverage
enforces at least 80% statements, lines, and functions plus 75% branches across
all maintained `src/**/*.{ts,tsx}` files, including files a test never imports.
`test:browser` is intentionally separate because it needs a Playwright Chromium
binary and starts the real local API and Vite processes on ports `3000` and
`5173`; both ports must be free. The browser-test configuration pins its API
host/port, web port, CORS origin, API base URL, mock data mode, and test runtime
environment explicitly, so local `.env` overrides cannot redirect the managed
test processes away from those readiness-checked origins.

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
- Playwright Chromium smoke tests that load the real dashboard, assert all five
  required forecast outputs and mock status, then navigate to the detailed
  forecast and assert its five outputs, inputs, drivers, and `All sites` return.

Playwright runs headlessly by default. `test:browser:headed` shows Chromium and
`test:browser:ui` offers interactive debugging. Failure-only traces and
screenshots are written to ignored test-artifact folders; no visual baselines or
pixel comparisons are maintained. OSM tiles are deliberately blocked in this
suite, so core local forecast behaviour does not depend on the public tile
service. Manual review still owns real tile rendering, pan/zoom, label
collisions, focus appearance, desktop/narrow visual fidelity, and browser
console review.
