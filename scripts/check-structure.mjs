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
  "apps/api/src/modules/forecasts/forecast.routes.ts",
  "apps/api/src/modules/health/health.routes.ts",
  "apps/api/src/modules/sites/site.routes.ts",
  "apps/api/src/observability/logger.ts",
  "apps/api/src/server.ts",
  "apps/api/test/smoke/server.test.ts",
  "apps/api/tsconfig.build.json",
  "apps/web/README.md",
  "apps/web/package.json",
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
]);

const requiredScripts = new Map([
  [
    "package.json",
    [
      "build",
      "dev:api",
      "format:check",
      "prelint",
      "lint",
      "repo:check",
      "start:api",
      "test",
      "test:coverage",
      "typecheck",
    ],
  ],
  ["apps/api/package.json", ["build", "dev", "start", "test", "test:coverage", "typecheck"]],
  ["packages/contracts/package.json", ["build", "test", "test:coverage", "typecheck"]],
]);

const requiredDependencies = new Map([
  [
    "apps/api/package.json",
    ["@paragliding-forecasts/contracts", "cors", "express", "pino", "pino-http", "zod"],
  ],
  ["packages/contracts/package.json", ["zod"]],
]);

const requiredDevDependencies = new Map([["package.json", ["@vitest/coverage-v8"]]]);

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

console.log("Repository structure and API workspace check passed.");
