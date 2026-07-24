import { z } from "zod";

import {
  availableDataStatusSchema,
  createForecastMetricSchema,
  provenanceSchema,
} from "./data-status.js";
import { siteIdSchema, siteSlugSchema } from "./sites.js";

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
  siteSlug: siteSlugSchema,
  date: forecastDateSchema,
});

export const cloudbaseMslMMetricSchema = createForecastMetricSchema(z.number().nonnegative());
export const chancePctMetricSchema = createForecastMetricSchema(z.number().min(0).max(100));
export const overdevelopmentRiskMetricSchema = createForecastMetricSchema(
  z.enum(["low", "medium", "high"]),
);

export const createForecastInputMetricSchema = <ValueSchema extends z.ZodType>(
  valueSchema: ValueSchema,
) =>
  z.discriminatedUnion("dataStatus", [
    z.strictObject({
      value: valueSchema,
      dataStatus: availableDataStatusSchema,
    }),
    z.strictObject({
      value: z.null(),
      dataStatus: z.literal("missing"),
      missingReason: z.string().trim().min(1),
    }),
  ]);

const percentageForecastInputSchema = createForecastInputMetricSchema(z.number().min(0).max(100));
const nonnegativeForecastInputSchema = createForecastInputMetricSchema(z.number().nonnegative());
const directionDegreesForecastInputSchema = createForecastInputMetricSchema(
  z.number().min(0).max(360),
);

export const windAtAltitudeSchema = z.strictObject({
  altitudeMslM: z.number().nonnegative(),
  directionDeg: z.number().min(0).max(360),
  speedKmh: z.number().nonnegative(),
});

export const convergenceSignalSchema = z.enum(["absent", "weak", "moderate", "strong"]);

export const forecastInputsSchema = z.strictObject({
  provenance: provenanceSchema,
  sourceRunAt: z.iso.datetime(),
  surfaceTemperatureC: createForecastInputMetricSchema(z.number().min(-80).max(70)),
  dewPointC: createForecastInputMetricSchema(z.number().min(-100).max(70)),
  boundaryLayerHeightM: nonnegativeForecastInputSchema,
  thermalStrengthMps: createForecastInputMetricSchema(z.number().min(-10).max(20)),
  boundaryLayerWindSpeedKmh: nonnegativeForecastInputSchema,
  boundaryLayerWindDirectionDeg: directionDegreesForecastInputSchema,
  windByAltitude: createForecastInputMetricSchema(z.array(windAtAltitudeSchema).min(1).max(6)),
  windShearMpsPerKm: nonnegativeForecastInputSchema,
  relativeHumidityPct: percentageForecastInputSchema,
  capeJPerKg: nonnegativeForecastInputSchema,
  cinJPerKg: nonnegativeForecastInputSchema,
  lapseRateCPerKm: createForecastInputMetricSchema(z.number().min(-20).max(20)),
  lowCloudCoverPct: percentageForecastInputSchema,
  totalCloudCoverPct: percentageForecastInputSchema,
  precipitationMm: nonnegativeForecastInputSchema,
  surfacePressureHpa: createForecastInputMetricSchema(z.number().min(800).max(1100)),
  convergenceSignal: createForecastInputMetricSchema(convergenceSignalSchema),
});

export const forecastOutputsSchema = z
  .strictObject({
    cloudbaseMslM: cloudbaseMslMMetricSchema,
    chance100KmPct: chancePctMetricSchema,
    chance200KmPct: chancePctMetricSchema,
    chance300KmPct: chancePctMetricSchema,
    overdevelopmentRisk: overdevelopmentRiskMetricSchema,
  })
  .superRefine((outputs, context) => {
    const chance100 = outputs.chance100KmPct;
    const chance200 = outputs.chance200KmPct;
    const chance300 = outputs.chance300KmPct;

    if (
      chance100.dataStatus !== "missing" &&
      chance200.dataStatus !== "missing" &&
      chance100.value < chance200.value
    ) {
      context.addIssue({
        code: "custom",
        message: "The 100+ km chance cannot be lower than the 200+ km chance.",
        path: ["chance100KmPct", "value"],
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
        path: ["chance200KmPct", "value"],
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
        path: ["chance100KmPct", "value"],
      });
    }
  });

export const forecastResponseSchema = z.strictObject({
  siteId: siteIdSchema,
  siteSlug: siteSlugSchema,
  forecastDate: forecastDateSchema,
  generatedAt: z.iso.datetime(),
  provenance: provenanceSchema,
  outputs: forecastOutputsSchema,
  forecastInputs: forecastInputsSchema,
  topDrivers: z.array(z.string().trim().min(1)).min(1),
});

export type ForecastDate = z.infer<typeof forecastDateSchema>;
export type ForecastQuery = z.infer<typeof forecastQuerySchema>;
export type ForecastOutputs = z.infer<typeof forecastOutputsSchema>;
export type ForecastInputs = z.infer<typeof forecastInputsSchema>;
export type ForecastResponse = z.infer<typeof forecastResponseSchema>;
