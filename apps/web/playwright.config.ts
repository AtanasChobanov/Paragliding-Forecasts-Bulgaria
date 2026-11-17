import { defineConfig, devices } from "@playwright/test";
import { fileURLToPath } from "node:url";

const repositoryRoot = fileURLToPath(new URL("../../", import.meta.url));

const fixtures = [
  { mode: "mock", apiPort: 3300, webPort: 5373, testMatch: "dashboard.smoke.spec.ts" },
  { mode: "sqlite", apiPort: 3301, webPort: 5374, testMatch: "dashboard.sqlite.spec.ts" },
].map(({ mode, apiPort, webPort, testMatch }) => ({
  mode,
  apiPort: String(apiPort),
  webPort: String(webPort),
  apiOrigin: `http://127.0.0.1:${String(apiPort)}`,
  webOrigin: `http://localhost:${String(webPort)}`,
  testMatch,
}));

export default defineConfig({
  expect: {
    timeout: 10_000,
  },
  forbidOnly: process.env.CI !== undefined,
  fullyParallel: false,
  outputDir: "test-results",
  projects: fixtures.map(({ mode, testMatch, webOrigin }) => ({
    name: `chromium-${mode}`,
    testMatch,
    use: { ...devices["Desktop Chrome"], baseURL: webOrigin },
  })),
  reporter: "list",
  retries: 0,
  testDir: "test/browser",
  timeout: 30_000,
  use: {
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  webServer: fixtures.flatMap(({ mode, apiOrigin, apiPort, webOrigin, webPort }) => [
    {
      command: "node --import tsx apps/api/test/support/dashboard-browser-server.ts",
      cwd: repositoryRoot,
      env: {
        API_HOST: "127.0.0.1",
        API_PORT: apiPort,
        CORS_ORIGIN: webOrigin,
        FORECAST_DATA_MODE: mode,
        NODE_ENV: "test",
      },
      gracefulShutdown: { signal: "SIGTERM", timeout: 5_000 },
      name: `API fixture (${mode})`,
      reuseExistingServer: false,
      stderr: "pipe",
      stdout: "pipe",
      timeout: 60_000,
      url: `${apiOrigin}/health`,
    },
    {
      command: "node node_modules/vite/bin/vite.js --mode test --config apps/web/vite.config.ts",
      cwd: repositoryRoot,
      env: { VITE_API_BASE_URL: apiOrigin, WEB_PORT: webPort },
      name: `Web fixture (${mode})`,
      reuseExistingServer: false,
      stderr: "pipe",
      stdout: "pipe",
      timeout: 60_000,
      url: webOrigin,
    },
  ]),
});
