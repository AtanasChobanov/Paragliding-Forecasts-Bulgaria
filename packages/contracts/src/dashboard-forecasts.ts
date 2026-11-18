import { z } from "zod";

import { availableDataStatusSchema, confidenceSchema, provenanceSchema } from "./data-status.js";
import { forecastDateSchema, validateNestedChances } from "./forecast.js";
import { siteIdSchema, siteSlugSchema } from "./sites.js";

const MAX_SUMMARY_SITES = 7;
const FORECAST_DAY_COUNT = 5;
const TODAY_INDEX = 2;

const forecastSummarySiteSlugsSchema = z
  .string()
  .transform((value) => value.split(","))
  .pipe(
    z
      .array(siteSlugSchema)
      .min(1)
      .max(MAX_SUMMARY_SITES)
      .refine((siteSlugs) => new Set(siteSlugs).size === siteSlugs.length, {
        message: "Expected unique site slugs.",
      }),
  );

export const forecastSummariesQuerySchema = z.strictObject({
  date: forecastDateSchema,
  siteSlugs: forecastSummarySiteSlugsSchema,
});

const forecastSummaryIdentitySchema = z.strictObject({
  siteId: siteIdSchema,
  siteSlug: siteSlugSchema,
  forecastDate: forecastDateSchema,
});

const textSchema = z.string().trim().min(1);

const availableMetricFields = {
  dataStatus: availableDataStatusSchema,
  confidence: confidenceSchema.partial({ note: true }),
  limitationsNote: textSchema.optional(),
};
const missingMetricFields = {
  dataStatus: z.literal("missing"),
  confidence: z.null(),
  missingReason: textSchema,
  confidenceNote: textSchema.optional(),
  limitationsNote: textSchema.optional(),
};

const missingMetricSchema = z.strictObject({ ...missingMetricFields, value: z.null() });
const chanceMetricSchema = z.discriminatedUnion("dataStatus", [
  z.strictObject({ ...availableMetricFields, value: z.number().min(0).max(100) }),
  missingMetricSchema,
]);
const overdevelopmentMetricSchema = z.discriminatedUnion("dataStatus", [
  z.strictObject({
    ...availableMetricFields,
    value: z.enum(["low", "medium", "high"]),
    score: z.number().min(0).max(100).optional(),
  }),
  missingMetricSchema,
]);
const heightFields = { ...availableMetricFields, valueMslM: z.number() };
const dashboardCloudbaseSchema = z.discriminatedUnion("kind", [
  z.strictObject({ ...heightFields, kind: z.literal("estimated") }),
  z.strictObject({ ...heightFields, kind: z.literal("conditional_lcl") }),
  z.strictObject({
    ...availableMetricFields,
    kind: z.enum(["blue", "other_cloud", "indeterminate"]),
  }),
  z.strictObject({ ...missingMetricFields, kind: z.literal("missing") }),
]);
export const dashboardOutputsSchema = z
  .strictObject({
    chance100KmPct: chanceMetricSchema,
    chance200KmPct: chanceMetricSchema,
    chance300KmPct: chanceMetricSchema,
    overdevelopmentRisk: overdevelopmentMetricSchema,
    cloudbase: dashboardCloudbaseSchema,
  })
  .superRefine(validateNestedChances);
export const dashboardMetadataSchema = z.discriminatedUnion("mode", [
  provenanceSchema.extend({ mode: z.literal("mock") }),
  z.strictObject({
    mode: z.literal("sqlite"),
    source: z.literal("NOAA GFS"),
    cycleAtUtc: z.iso.datetime(),
    horizonDays: z.literal([1, 2, 3]),
    xcModelId: textSchema,
    cloudbaseMethodVersion: textSchema,
    overdevelopmentPolicyVersion: textSchema,
    fromPreviousIssue: z.boolean(),
  }),
]);

const availableForecastSummarySchema = forecastSummaryIdentitySchema.extend({
  availability: z.literal("available"),
  generatedAt: z.iso.datetime(),
  metadata: dashboardMetadataSchema,
  outputs: dashboardOutputsSchema,
});

const missingForecastSummarySchema = forecastSummaryIdentitySchema.extend({
  availability: z.literal("missing"),
  missingReason: z.string().trim().min(1),
});

export const forecastSummarySchema = z.discriminatedUnion("availability", [
  availableForecastSummarySchema,
  missingForecastSummarySchema,
]);

export const forecastSummariesResponseSchema = z
  .strictObject({
    forecastDate: forecastDateSchema,
    summaries: z.array(forecastSummarySchema).min(1).max(MAX_SUMMARY_SITES),
  })
  .superRefine((response, context) => {
    const siteIds = new Set<number>();
    const siteSlugs = new Set<string>();
    let previousSiteId = 0;

    response.summaries.forEach((summary, index) => {
      if (summary.forecastDate !== response.forecastDate) {
        context.addIssue({
          code: "custom",
          message: "Expected the summary date to match the response date.",
          path: ["summaries", index, "forecastDate"],
        });
      }

      if (siteIds.has(summary.siteId)) {
        context.addIssue({
          code: "custom",
          message: "Expected one summary per site ID.",
          path: ["summaries", index, "siteId"],
        });
      }

      if (siteSlugs.has(summary.siteSlug)) {
        context.addIssue({
          code: "custom",
          message: "Expected one summary per site slug.",
          path: ["summaries", index, "siteSlug"],
        });
      }

      if (summary.siteId <= previousSiteId) {
        context.addIssue({
          code: "custom",
          message: "Expected summaries to be ordered by ascending site ID.",
          path: ["summaries", index, "siteId"],
        });
      }

      siteIds.add(summary.siteId);
      siteSlugs.add(summary.siteSlug);
      previousSiteId = summary.siteId;
    });
  });

export const forecastDaysQuerySchema = z.strictObject({
  siteSlug: siteSlugSchema,
});

export const forecastDaySchema = z.discriminatedUnion("availability", [
  z.strictObject({
    availability: z.literal("available"),
    forecastDate: forecastDateSchema,
    chance100KmPct: chanceMetricSchema,
  }),
  z.strictObject({
    availability: z.literal("missing"),
    forecastDate: forecastDateSchema,
    chance100KmPct: missingMetricSchema,
    missingReason: textSchema,
  }),
]);

const addUtcDays = (date: string, offsetDays: number): string => {
  const [year, month, day] = date.split("-").map(Number) as [number, number, number];
  const value = new Date(Date.UTC(year, month - 1, day + offsetDays));

  return value.toISOString().slice(0, 10);
};

export const forecastDaysResponseSchema = z
  .strictObject({
    siteId: siteIdSchema,
    siteSlug: siteSlugSchema,
    timeZone: z.literal("Europe/Sofia"),
    todayDate: forecastDateSchema,
    days: z.array(forecastDaySchema).length(FORECAST_DAY_COUNT),
  })
  .superRefine((response, context) => {
    response.days.forEach((day, index) => {
      const expectedDate = addUtcDays(response.todayDate, index - TODAY_INDEX);

      if (day.forecastDate !== expectedDate) {
        context.addIssue({
          code: "custom",
          message: `Expected forecast date ${expectedDate}.`,
          path: ["days", index, "forecastDate"],
        });
      }
    });
  });

export type ForecastSummariesQuery = z.infer<typeof forecastSummariesQuerySchema>;
export type ForecastSummary = z.infer<typeof forecastSummarySchema>;
export type AvailableForecastSummary = z.infer<typeof availableForecastSummarySchema>;
export type DashboardForecastOutputs = z.infer<typeof dashboardOutputsSchema>;
export type DashboardCloudbase = z.infer<typeof dashboardCloudbaseSchema>;
export type ForecastSummariesResponse = z.infer<typeof forecastSummariesResponseSchema>;
export type ForecastDaysQuery = z.infer<typeof forecastDaysQuerySchema>;
export type ForecastDay = z.infer<typeof forecastDaySchema>;
export type ForecastDaysResponse = z.infer<typeof forecastDaysResponseSchema>;
