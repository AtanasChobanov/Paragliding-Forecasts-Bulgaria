import { existsSync } from "node:fs";
import { resolve } from "node:path";
import { loadEnvFile } from "node:process";
import { fileURLToPath } from "node:url";

import { migrate } from "drizzle-orm/node-sqlite/migrator";

import { openDatabase } from "./connection.js";

const rootEnvPath = fileURLToPath(new URL("../../../.env", import.meta.url));
const migrationsFolder = fileURLToPath(new URL("../drizzle", import.meta.url));

export const loadRootEnvironmentIfNeeded = (
  databaseUrl: string | undefined,
  environmentDatabaseUrl = process.env.DATABASE_URL,
  rootEnvironmentFileExists = existsSync(rootEnvPath),
  loadEnvironmentFile: (path: string) => void = loadEnvFile,
): void => {
  if (
    databaseUrl === undefined &&
    environmentDatabaseUrl === undefined &&
    rootEnvironmentFileExists
  ) {
    loadEnvironmentFile(rootEnvPath);
  }
};

export const runMigrations = (databaseUrl?: string): void => {
  loadRootEnvironmentIfNeeded(databaseUrl);

  const connection = openDatabase(databaseUrl);

  try {
    migrate(connection.db, { migrationsFolder });
  } finally {
    connection.close();
  }
};

export const isMigrationEntrypoint = (scriptPath = process.argv[1]): boolean =>
  scriptPath !== undefined && resolve(scriptPath) === fileURLToPath(import.meta.url);

/* v8 ignore next -- executed by the npm script; the exported predicate is unit-tested. */
if (isMigrationEntrypoint()) {
  runMigrations();
}
