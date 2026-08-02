import { existsSync } from "node:fs";
import { loadEnvFile } from "node:process";
import { fileURLToPath } from "node:url";

import { migrate } from "drizzle-orm/node-sqlite/migrator";

import { openDatabase } from "./connection.js";

const rootEnvPath = fileURLToPath(new URL("../../../.env", import.meta.url));
const migrationsFolder = fileURLToPath(new URL("../drizzle", import.meta.url));

if (existsSync(rootEnvPath)) {
  loadEnvFile(rootEnvPath);
}

const connection = openDatabase();

try {
  migrate(connection.db, { migrationsFolder });
} finally {
  connection.close();
}
