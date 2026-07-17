import { z } from "zod";

export const availableDataStatusSchema = z.enum(["mock", "manual", "baseline", "real"]);
export const dataStatusSchema = z.enum(["mock", "manual", "baseline", "real", "missing"]);
export const confidenceLevelSchema = z.enum(["low", "medium", "high"]);

export const confidenceSchema = z.strictObject({
  level: confidenceLevelSchema,
  note: z.string().trim().min(1),
});

export const provenanceSchema = z.strictObject({
  source: z.string().trim().min(1),
  version: z.string().trim().min(1),
});

export const createForecastMetricSchema = <ValueSchema extends z.ZodType>(
  valueSchema: ValueSchema,
) =>
  z.discriminatedUnion("dataStatus", [
    z.strictObject({
      value: valueSchema,
      dataStatus: availableDataStatusSchema,
      confidence: confidenceSchema,
    }),
    z.strictObject({
      value: z.null(),
      dataStatus: z.literal("missing"),
      confidence: z.null(),
      missingReason: z.string().trim().min(1),
    }),
  ]);

export type DataStatus = z.infer<typeof dataStatusSchema>;
export type Confidence = z.infer<typeof confidenceSchema>;
export type Provenance = z.infer<typeof provenanceSchema>;
