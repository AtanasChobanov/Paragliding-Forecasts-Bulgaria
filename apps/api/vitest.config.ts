import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    coverage: {
      include: ["src/**/*.ts"],
      provider: "v8",
      reporter: ["text", "html", "lcov"],
      thresholds: {
        branches: 75,
        functions: 70,
        lines: 70,
        statements: 70,
      },
    },
    environment: "node",
    include: ["test/**/*.test.ts"],
  },
});
