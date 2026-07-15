import { access, readFile } from "node:fs/promises";

const requiredPaths = [
  ".env.example",
  ".gitignore",
  "CONTRIBUTING.md",
  "README.md",
  "apps/api/README.md",
  "apps/api/package.json",
  "apps/web/README.md",
  "apps/web/package.json",
  "data/README.md",
  "docs/architecture.md",
  "docs/development.md",
  "packages/contracts/README.md",
  "packages/contracts/package.json",
  "services/ml/README.md",
  "services/ml/.python-version",
  "services/ml/pyproject.toml",
  "tsconfig.base.json"
];

const expectedWorkspaceNames = new Map([
  ["apps/api/package.json", "@paragliding-forecasts/api"],
  ["apps/web/package.json", "@paragliding-forecasts/web"],
  ["packages/contracts/package.json", "@paragliding-forecasts/contracts"]
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
  console.error("Repository scaffold is incomplete. Missing paths:");
  for (const path of missing) {
    console.error(`- ${path}`);
  }
  process.exit(1);
}

for (const [path, expectedName] of expectedWorkspaceNames) {
  const manifest = JSON.parse(await readFile(path, "utf8"));

  if (manifest.name !== expectedName || manifest.private !== true) {
    console.error(
      `${path} must be private and named ${expectedName}; received ${manifest.name}.`
    );
    process.exit(1);
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

console.log("Repository scaffold check passed.");
