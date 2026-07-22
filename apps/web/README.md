# Web dashboard

## Status

The React/Vite workspace is runnable, production-buildable, and backed by a
validated dashboard HTTP/query foundation. The dashboard route coordinates
canonical URL selection and the sites, days, and summaries queries inside a
responsive visual shell with a semantic application header, stable dashboard
panels, reusable content states, self-hosted Inter, and shared theme tokens.
Forecast cards, the interactive map, and the five-day selector are added by the
remaining T-003-T-005 stages.

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
- A browser-testing tool selected when T-008 is implemented

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
|   |   |-- components/DashboardShell.tsx
|   |   |-- dashboard-compatibility-error.ts
|   |   |-- dashboard-query-options.ts
|   |   |-- dashboard-search-params.ts
|   |   `-- dashboard-summary-selection.ts
|   |-- routes/dashboard/
|   |   |-- dashboard-route.module.scss
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

Standalone web `dev`, `build`, `typecheck`, and test commands build the shared
contracts first. The combined root `dev` supervisor builds contracts once and
then starts the raw API and web watchers.

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
URL date is unusable, and handles an empty catalog. Summary requests deduplicate
the selected site plus the configured Other Locations by numeric ID while the
UI keeps its separate Zlatitsa, Sofia - Vitosha, Dobrich region order.

## Testing expectations

- API-client tests for URL encoding, success parsing, Problem Details, network
  failure, cancellation, malformed JSON, invalid response shapes, and safe
  non-JSON HTTP fallbacks.
- Query/provider tests for stable keys, cancellation signals, freshness, and
  retry policy.
- Route tests for URL normalization, deep links, history navigation, dependent
  query enabling, request deduplication/reindexing, partial catalogs, empty
  catalogs, independent failures, and stale-selection prevention.
- Unit tests for forecast-card transformations and data-status mapping as the
  presentation components are added.
- Component tests for loading, missing, and error states as the route and
  presentation components are added.
- Component tests for the stable dashboard shell, panel semantics, and reusable
  loading, error, empty, and informational states.
- T-008 browser smoke test proving the dashboard and required cards render.

V8 coverage counts all maintained `src/**/*.{ts,tsx}` files, including files a
test never imports. The enforced minimums are 80% statements, lines, and
functions and 75% branches.
