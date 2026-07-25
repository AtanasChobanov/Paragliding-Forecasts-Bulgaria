import { defineConfig, devices } from "@playwright/test";
import { fileURLToPath } from "node:url";

const repositoryRoot = fileURLToPath(new URL("../../", import.meta.url));
const apiOrigin = "http://127.0.0.1:3000";
const webOrigin = "http://localhost:5173";

export default defineConfig({
  expect: {
    timeout: 10_000,
  },
  forbidOnly: process.env.CI !== undefined,
  fullyParallel: false,
  outputDir: "test-results",
  projects: [
    {
      name: "chromium",
      use: devices["Desktop Chrome"],
    },
  ],
  reporter: "list",
  retries: 0,
  testDir: "test/browser",
  timeout: 30_000,
  use: {
    baseURL: webOrigin,
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  webServer: [
    {
      command: "npm run start:api",
      cwd: repositoryRoot,
      name: "API",
      reuseExistingServer: false,
      stderr: "pipe",
      stdout: "pipe",
      timeout: 120_000,
      url: `${apiOrigin}/health`,
    },
    {
      command: "npm run dev:raw --workspace @paragliding-forecasts/web",
      cwd: repositoryRoot,
      name: "Web",
      reuseExistingServer: false,
      stderr: "pipe",
      stdout: "pipe",
      timeout: 120_000,
      url: webOrigin,
    },
  ],
});
