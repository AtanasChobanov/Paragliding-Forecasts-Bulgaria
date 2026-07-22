import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";
import { z } from "zod";

const repositoryRoot = fileURLToPath(new URL("../../", import.meta.url));
const webRoot = fileURLToPath(new URL("./", import.meta.url));
const webPortSchema = z.coerce.number().int().min(1).max(65_535);

const readWebPort = (mode: string): number => {
  const fileEnvironment = loadEnv(mode, repositoryRoot, "WEB_PORT");
  const fileWebPort = Object.hasOwn(fileEnvironment, "WEB_PORT")
    ? fileEnvironment.WEB_PORT
    : undefined;
  const result = webPortSchema.safeParse(process.env.WEB_PORT ?? fileWebPort ?? "5173");

  if (!result.success) {
    throw new Error("WEB_PORT must be an integer from 1 through 65535.");
  }

  return result.data;
};

export default defineConfig(({ mode }) => ({
  envDir: repositoryRoot,
  plugins: [react()],
  root: webRoot,
  server: {
    host: "localhost",
    port: readWebPort(mode),
    strictPort: true,
  },
}));
