import { z } from "zod";

export const healthResponseSchema = z.strictObject({
  status: z.literal("ok"),
  service: z.literal("paragliding-forecasts-api"),
  version: z.string().trim().min(1),
  timestamp: z.iso.datetime(),
});

export type HealthResponse = z.infer<typeof healthResponseSchema>;
