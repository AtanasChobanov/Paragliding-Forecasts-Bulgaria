import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  test: {
    clearMocks: true,
    coverage: {
      exclude: ["src/**/*.d.ts"],
      include: ["src/**/*.{ts,tsx}"],
      provider: "v8",
      reporter: ["text", "html", "lcov"],
      thresholds: {
        branches: 75,
        functions: 80,
        lines: 80,
        statements: 80,
      },
    },
    environment: "jsdom",
    environmentOptions: {
      jsdom: {
        url: "http://localhost:5173/",
      },
    },
    include: ["test/**/*.test.{ts,tsx}"],
    restoreMocks: true,
    setupFiles: ["./test/setup.ts"],
    unstubEnvs: true,
    unstubGlobals: true,
  },
});
