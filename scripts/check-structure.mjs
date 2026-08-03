import { access, readFile } from "node:fs/promises";

const requiredPaths = [
  "AGENTS.md",
  ".env.example",
  ".gitignore",
  "CONTRIBUTING.md",
  "README.md",
  "package-lock.json",
  "apps/api/README.md",
  "apps/api/package.json",
  "apps/api/src/app.ts",
  "apps/api/src/app-metadata.ts",
  "apps/api/src/config/env.ts",
  "apps/api/src/http/middleware/error-handler.ts",
  "apps/api/src/main.ts",
  "apps/api/src/modules/forecasts/forecast-prediction.ts",
  "apps/api/src/modules/forecasts/forecast.routes.ts",
  "apps/api/src/modules/health/health.routes.ts",
  "apps/api/src/modules/sites/site.routes.ts",
  "apps/api/src/observability/logger.ts",
  "apps/api/src/server.ts",
  "apps/api/test/smoke/server.test.ts",
  "apps/api/tsconfig.build.json",
  "apps/web/README.md",
  "apps/web/index.html",
  "apps/web/package.json",
  "apps/web/playwright.config.ts",
  "apps/web/src/App.module.scss",
  "apps/web/src/App.tsx",
  "apps/web/src/app/AppProviders.tsx",
  "apps/web/src/app/app-routes.tsx",
  "apps/web/src/app/query-client.ts",
  "apps/web/src/components/app-header/AppHeader.module.scss",
  "apps/web/src/components/app-header/AppHeader.tsx",
  "apps/web/src/components/content-state/ContentState.module.scss",
  "apps/web/src/components/content-state/ContentState.tsx",
  "apps/web/src/components/dashboard-panel/DashboardPanel.module.scss",
  "apps/web/src/components/dashboard-panel/DashboardPanel.tsx",
  "apps/web/src/config/runtime-config.ts",
  "apps/web/src/features/dashboard/components/DashboardShell.module.scss",
  "apps/web/src/features/dashboard/components/DashboardShell.tsx",
  "apps/web/src/features/dashboard/components/DashboardErrorState.tsx",
  "apps/web/src/features/dashboard/components/AccessibleSiteSelector.module.scss",
  "apps/web/src/features/dashboard/components/AccessibleSiteSelector.tsx",
  "apps/web/src/features/dashboard/components/ConfidenceIndicator.module.scss",
  "apps/web/src/features/dashboard/components/ConfidenceIndicator.tsx",
  "apps/web/src/features/dashboard/components/DataStatusBadge.module.scss",
  "apps/web/src/features/dashboard/components/DataStatusBadge.tsx",
  "apps/web/src/features/dashboard/components/ForecastMetric.module.scss",
  "apps/web/src/features/dashboard/components/ForecastMetric.tsx",
  "apps/web/src/features/dashboard/components/ForecastDateCard.module.scss",
  "apps/web/src/features/dashboard/components/ForecastDateCard.tsx",
  "apps/web/src/features/dashboard/components/ForecastDateStrip.module.scss",
  "apps/web/src/features/dashboard/components/ForecastDateStrip.tsx",
  "apps/web/src/features/dashboard/components/ForecastOverview.module.scss",
  "apps/web/src/features/dashboard/components/ForecastOverview.tsx",
  "apps/web/src/features/dashboard/components/LocationSummaryCard.module.scss",
  "apps/web/src/features/dashboard/components/LocationSummaryCard.tsx",
  "apps/web/src/features/dashboard/components/OtherLocationsSection.module.scss",
  "apps/web/src/features/dashboard/components/OtherLocationsSection.tsx",
  "apps/web/src/features/dashboard/components/SiteMap.module.scss",
  "apps/web/src/features/dashboard/components/SiteMap.tsx",
  "apps/web/src/features/dashboard/components/SiteSelectorSection.module.scss",
  "apps/web/src/features/dashboard/components/SiteSelectorSection.tsx",
  "apps/web/src/features/dashboard/dashboard-compatibility-error.ts",
  "apps/web/src/features/dashboard/dashboard-error-presentation.ts",
  "apps/web/src/features/dashboard/dashboard-query-options.ts",
  "apps/web/src/features/dashboard/dashboard-search-params.ts",
  "apps/web/src/features/dashboard/dashboard-summary-selection.ts",
  "apps/web/src/features/dashboard/forecast-presentation.ts",
  "apps/web/src/features/dashboard/map-provider.ts",
  "apps/web/src/main.tsx",
  "apps/web/src/routes/dashboard/dashboard-route.tsx",
  "apps/web/src/services/api/api-client.ts",
  "apps/web/src/services/api/api-errors.ts",
  "apps/web/src/services/api/dashboard-api.ts",
  "apps/web/src/vite-env.d.ts",
  "apps/web/src/styles/_mixins.scss",
  "apps/web/src/styles/_tokens.scss",
  "apps/web/src/styles/globals.scss",
  "apps/web/test/component/content-state.test.tsx",
  "apps/web/test/component/accessible-site-selector.test.tsx",
  "apps/web/test/component/dashboard-panel.test.tsx",
  "apps/web/test/component/dashboard-shell.test.tsx",
  "apps/web/test/component/forecast-overview.test.tsx",
  "apps/web/test/component/forecast-date-strip.test.tsx",
  "apps/web/test/component/other-locations-section.test.tsx",
  "apps/web/test/component/site-map.test.tsx",
  "apps/web/test/integration/dashboard-api.test.ts",
  "apps/web/test/integration/dashboard-route.test.tsx",
  "apps/web/test/browser/dashboard.smoke.spec.ts",
  "apps/web/test/setup.ts",
  "apps/web/test/support/dashboard-fixtures.ts",
  "apps/web/test/support/render.tsx",
  "apps/web/test/support/server.ts",
  "apps/web/test/unit/config.test.ts",
  "apps/web/test/unit/dashboard-query-options.test.ts",
  "apps/web/test/unit/dashboard-error-presentation.test.ts",
  "apps/web/test/unit/dashboard-route-orchestration.test.ts",
  "apps/web/test/unit/forecast-presentation.test.ts",
  "apps/web/test/unit/map-provider.test.ts",
  "apps/web/test/unit/query-client.test.tsx",
  "apps/web/tsconfig.json",
  "apps/web/tsconfig.node.json",
  "apps/web/vite.config.ts",
  "apps/web/vitest.config.ts",
  "data/README.md",
  "docs/architecture.md",
  "docs/decisions.md",
  "docs/development.md",
  "docs/handoff.md",
  "docs/project-brief.md",
  "docs/tasks.md",
  "packages/contracts/README.md",
  "packages/contracts/package.json",
  "packages/contracts/src/index.ts",
  "packages/contracts/test/contracts.test.ts",
  "packages/contracts/tsconfig.build.json",
  "packages/database/package.json",
  "packages/database/README.md",
  "packages/database/drizzle/20260802104316_create_flight_foundation/migration.sql",
  "packages/database/drizzle/20260802104333_seed_initial_sites_and_xccontest_source/migration.sql",
  "packages/database/drizzle.config.ts",
  "packages/database/src/connection.ts",
  "packages/database/src/index.ts",
  "packages/database/src/migrate.ts",
  "packages/database/src/schema.ts",
  "packages/database/test/connection.test.ts",
  "packages/database/test/migrate.test.ts",
  "packages/database/test/migration-foundation.test.ts",
  "packages/database/test/schema.test.ts",
  "packages/database/tsconfig.build.json",
  "packages/database/tsconfig.json",
  "packages/database/vitest.config.ts",
  "scripts/dev.mjs",
  "services/ml/README.md",
  "services/ml/.python-version",
  "services/ml/pyproject.toml",
  "services/ml/uv.lock",
  "tsconfig.base.json",
];

const expectedWorkspaceNames = new Map([
  ["apps/api/package.json", "@paragliding-forecasts/api"],
  ["apps/web/package.json", "@paragliding-forecasts/web"],
  ["packages/contracts/package.json", "@paragliding-forecasts/contracts"],
  ["packages/database/package.json", "@paragliding-forecasts/database"],
]);

const requiredScripts = new Map([
  [
    "package.json",
    [
      "build",
      "dev",
      "dev:api",
      "dev:web",
      "format:check",
      "predev",
      "prelint",
      "lint",
      "repo:check",
      "start:api",
      "test",
      "test:browser",
      "test:browser:headed",
      "test:browser:install",
      "test:browser:ui",
      "test:coverage",
      "typecheck",
    ],
  ],
  [
    "apps/api/package.json",
    ["build", "dev", "dev:raw", "start", "test", "test:coverage", "typecheck"],
  ],
  [
    "apps/web/package.json",
    [
      "build",
      "contracts:build",
      "dev",
      "dev:raw",
      "prebuild",
      "predev",
      "pretest",
      "pretest:browser",
      "pretest:browser:headed",
      "pretest:browser:ui",
      "pretest:coverage",
      "pretest:watch",
      "pretypecheck",
      "test",
      "test:browser",
      "test:browser:headed",
      "test:browser:install",
      "test:browser:ui",
      "test:coverage",
      "test:watch",
      "typecheck",
      "typecheck:raw",
    ],
  ],
  ["packages/contracts/package.json", ["build", "test", "test:coverage", "typecheck"]],
  [
    "packages/database/package.json",
    ["build", "db:check", "db:generate", "db:migrate", "test", "test:coverage", "typecheck"],
  ],
]);

const requiredDependencies = new Map([
  [
    "apps/api/package.json",
    ["@paragliding-forecasts/contracts", "cors", "express", "pino", "pino-http", "zod"],
  ],
  ["packages/contracts/package.json", ["zod"]],
  ["packages/database/package.json", ["drizzle-orm"]],
  [
    "apps/web/package.json",
    [
      "@paragliding-forecasts/contracts",
      "@fontsource-variable/inter",
      "@tanstack/react-query",
      "leaflet",
      "react",
      "react-dom",
      "react-leaflet",
      "react-router-dom",
      "zod",
    ],
  ],
]);

const requiredDevDependencies = new Map([
  ["package.json", ["@vitest/coverage-v8"]],
  ["packages/database/package.json", ["@types/node", "drizzle-kit", "tsx"]],
  [
    "apps/web/package.json",
    [
      "@testing-library/dom",
      "@playwright/test",
      "@testing-library/jest-dom",
      "@testing-library/react",
      "@testing-library/user-event",
      "@types/node",
      "@types/leaflet",
      "@types/react",
      "@types/react-dom",
      "@vitejs/plugin-react",
      "jsdom",
      "msw",
      "sass-embedded",
      "vite",
    ],
  ],
]);

const missing = [];

for (const path of requiredPaths) {
  try {
    await access(path);
  } catch {
    missing.push(path);
  }
}

if (missing.length > 0) {
  console.error("Repository structure is incomplete. Missing paths:");
  for (const path of missing) {
    console.error(`- ${path}`);
  }
  process.exit(1);
}

for (const [path, expectedName] of expectedWorkspaceNames) {
  const manifest = JSON.parse(await readFile(path, "utf8"));

  if (manifest.name !== expectedName || manifest.private !== true) {
    console.error(`${path} must be private and named ${expectedName}; received ${manifest.name}.`);
    process.exit(1);
  }
}

for (const [path, scripts] of requiredScripts) {
  const manifest = JSON.parse(await readFile(path, "utf8"));

  for (const script of scripts) {
    if (typeof manifest.scripts?.[script] !== "string" || manifest.scripts[script].length === 0) {
      console.error(`${path} is missing a runnable ${script} script.`);
      process.exit(1);
    }
  }
}

for (const [path, dependencies] of requiredDependencies) {
  const manifest = JSON.parse(await readFile(path, "utf8"));

  for (const dependency of dependencies) {
    if (typeof manifest.dependencies?.[dependency] !== "string") {
      console.error(`${path} is missing runtime dependency: ${dependency}`);
      process.exit(1);
    }
  }
}

for (const [path, dependencies] of requiredDevDependencies) {
  const manifest = JSON.parse(await readFile(path, "utf8"));

  for (const dependency of dependencies) {
    if (typeof manifest.devDependencies?.[dependency] !== "string") {
      console.error(`${path} is missing development dependency: ${dependency}`);
      process.exit(1);
    }
  }
}

const rootManifest = JSON.parse(await readFile("package.json", "utf8"));
const workspaces = new Set(rootManifest.workspaces ?? []);

for (const workspace of ["apps/*", "packages/*"]) {
  if (!workspaces.has(workspace)) {
    console.error(`Root package.json is missing workspace: ${workspace}`);
    process.exit(1);
  }
}

if (rootManifest.engines?.node !== ">=24 <25" || rootManifest.engines?.npm !== ">=11 <12") {
  console.error("Root package.json must target Node.js 24.x and npm 11.x.");
  process.exit(1);
}

console.log("Repository structure and runnable workspace check passed.");
