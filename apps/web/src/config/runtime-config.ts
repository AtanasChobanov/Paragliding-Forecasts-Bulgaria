import { z } from "zod";

const apiBaseUrlSchema = z
  .string()
  .trim()
  .min(1)
  .transform((value, context) => {
    let url: URL;

    try {
      url = new URL(value);
    } catch {
      context.addIssue({
        code: "custom",
        message: "Expected an absolute URL.",
      });
      return z.NEVER;
    }

    if (url.protocol !== "http:" && url.protocol !== "https:") {
      context.addIssue({
        code: "custom",
        message: "Expected an HTTP(S) URL.",
      });
      return z.NEVER;
    }

    return url.href.replace(/\/$/u, "");
  });

const runtimeEnvironmentSchema = z.object({
  VITE_API_BASE_URL: apiBaseUrlSchema,
});

export interface RuntimeConfig {
  readonly apiBaseUrl: string;
}

export const parseRuntimeConfig = (environment: unknown): RuntimeConfig => {
  const result = runtimeEnvironmentSchema.safeParse(environment);

  if (!result.success) {
    throw new Error("VITE_API_BASE_URL must be an absolute HTTP(S) URL.");
  }

  return { apiBaseUrl: result.data.VITE_API_BASE_URL };
};

export const loadRuntimeConfig = (): RuntimeConfig => parseRuntimeConfig(import.meta.env);
