import { z } from "zod";

import { createForecastMetricSchema, provenanceSchema } from "./data-status.js";
import { siteIdSchema } from "./sites.js";

const ISO_DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

const isCalendarDate = (value: string): boolean => {
  const [yearText, monthText, dayText] = value.split("-");

  if (yearText === undefined || monthText === undefined || dayText === undefined) {
    return false;
  }

  const year = Number(yearText);
  const month = Number(monthText);
  const day = Number(dayText);
  const parsed = new Date(Date.UTC(year, month - 1, day));

  return (
    parsed.getUTCFullYear() === year &&
    parsed.getUTCMonth() === month - 1 &&
    parsed.getUTCDate() === day
  );
};

export const forecastDateSchema = z
  .string()
  .regex(ISO_DATE_PATTERN, "Expected a date in YYYY-MM-DD format.")
  .refine(isCalendarDate, "Expected a real calendar date.");

export const forecastQuerySchema = z.strictObject({
  siteId: siteIdSchema,
  date: forecastDateSchema,
});

const cloudbaseMslMMetricSchema = createForecastMetricSchema(z.number().nonnegative());
const chancePctMetricSchema = createForecastMetricSchema(z.number().min(0).max(100));
const overdevelopmentRiskMetricSchema = createForecastMetricSchema(
  z.enum(["low", "medium", "high"]),
);

export const forecastResponseSchema = z
  .strictObject({
    siteId: siteIdSchema,
    forecastDate: forecastDateSchema,
    generatedAt: z.iso.datetime(),
    provenance: provenanceSchema,
    outputs: z.strictObject({
      cloudbaseMslM: cloudbaseMslMMetricSchema,
      chance100KmPct: chancePctMetricSchema,
      chance200KmPct: chancePctMetricSchema,
      chance300KmPct: chancePctMetricSchema,
      overdevelopmentRisk: overdevelopmentRiskMetricSchema,
    }),
    topDrivers: z.array(z.string().trim().min(1)),
    qualityNotes: z.array(z.string().trim().min(1)).min(1),
  })
  .superRefine((forecast, context) => {
    const chance100 = forecast.outputs.chance100KmPct;
    const chance200 = forecast.outputs.chance200KmPct;
    const chance300 = forecast.outputs.chance300KmPct;

    if (
      chance100.dataStatus !== "missing" &&
      chance200.dataStatus !== "missing" &&
      chance100.value < chance200.value
    ) {
      context.addIssue({
        code: "custom",
        message: "The 100+ km chance cannot be lower than the 200+ km chance.",
        path: ["outputs", "chance100KmPct", "value"],
      });
    }

    if (
      chance200.dataStatus !== "missing" &&
      chance300.dataStatus !== "missing" &&
      chance200.value < chance300.value
    ) {
      context.addIssue({
        code: "custom",
        message: "The 200+ km chance cannot be lower than the 300+ km chance.",
        path: ["outputs", "chance200KmPct", "value"],
      });
    }

    if (
      chance200.dataStatus === "missing" &&
      chance100.dataStatus !== "missing" &&
      chance300.dataStatus !== "missing" &&
      chance100.value < chance300.value
    ) {
      context.addIssue({
        code: "custom",
        message: "The 100+ km chance cannot be lower than the 300+ km chance.",
        path: ["outputs", "chance100KmPct", "value"],
      });
    }
  });

export type ForecastDate = z.infer<typeof forecastDateSchema>;
export type ForecastQuery = z.infer<typeof forecastQuerySchema>;
export type ForecastResponse = z.infer<typeof forecastResponseSchema>;
