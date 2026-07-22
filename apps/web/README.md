# Web dashboard

## Status

The React/Vite workspace is runnable and production-buildable. It currently
renders only the truthful application heading; the real dashboard route, API
queries, and visual components are added by the remaining T-003-T-005 stages.

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
|   |-- config/runtime-config.ts
|   |-- App.tsx
|   |-- main.tsx
|   `-- vite-env.d.ts
|-- package.json
|-- tsconfig.json
|-- tsconfig.node.json
`-- vite.config.ts
```

Prefer feature-oriented folders once the UI grows; avoid a single global
`components` folder containing unrelated domain behavior.

## Commands

Run from the repository root:

```powershell
npm.cmd run dev:web
npm.cmd run build --workspace @paragliding-forecasts/web
npm.cmd run typecheck --workspace @paragliding-forecasts/web
```

Use `npm.cmd run dev` to supervise the API and web servers together. Vite uses
`strictPort: true`, so an occupied configured port fails instead of silently
moving the dashboard to another origin. Stage 2 adds the first real web test
scripts together with meaningful API-client/provider tests.

## Configuration

Browser-exposed variables must use Vite's `VITE_` prefix. Never place secrets
in web environment variables because they are bundled into client code.

Current variables:

- `VITE_API_BASE_URL` - absolute HTTP(S) base URL of the local Express API;
  validated before React renders and normalized without a trailing slash
- `WEB_PORT` - Vite development port, default `5173`; changing it requires the
  exact matching `CORS_ORIGIN`

## Testing expectations

- Unit tests for forecast-card transformations and data-status mapping.
- Component tests for loading, missing, and error states.
- T-008 browser smoke test proving the dashboard and required cards render.

There is intentionally no passing placeholder web test script. Stage 2 adds the
test command and coverage gate with the first behavior it can verify.
