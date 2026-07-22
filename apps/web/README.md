# Web dashboard

## Status

Directory scaffold only. The React application and its first dashboard route
belong to **T-003**. T-001 intentionally contains no landing page or fake dev
server.

## Responsibilities

- Render the daily forecast dashboard.
- Provide the site and forecast-date selectors.
- Display cloudbase, 100+/200+/300+ chances, and overdevelopment risk.
- Label every value as mock, manual, baseline, real, or unavailable.
- Handle loading, empty, and API error states accessibly.

The web app must not calculate model probabilities or read databases directly.
It consumes versioned HTTP contracts from `@paragliding-forecasts/contracts`.

## Planned stack

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

## Planned layout

```text
apps/web/
|-- src/
|   |-- components/
|   |-- features/forecast/
|   |-- routes/
|   |-- services/
|   `-- main.tsx
|-- public/
|-- package.json
`-- tsconfig.json
```

Prefer feature-oriented folders once the UI grows; avoid a single global
`components` folder containing unrelated domain behavior.

## Commands after T-003

Run from the repository root:

```powershell
npm.cmd run dev:web
npm.cmd run build --workspace @paragliding-forecasts/web
npm.cmd run test --workspace @paragliding-forecasts/web
```

Until T-003 adds the Vite entry point and package scripts, these commands are
documentation targets, not working application commands.

## Configuration

Browser-exposed variables must use Vite's `VITE_` prefix. Never place secrets
in web environment variables because they are bundled into client code.

Initial variable:

- `VITE_API_BASE_URL` - base URL of the local Express API

## Testing expectations

- Unit tests for forecast-card transformations and data-status mapping.
- Component tests for loading, missing, and error states.
- T-008 browser smoke test proving the dashboard and required cards render.
