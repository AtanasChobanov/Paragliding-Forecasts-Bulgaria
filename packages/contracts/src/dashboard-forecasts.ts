import { z } from "zod";

import { provenanceSchema } from "./data-status.js";
import { chancePctMetricSchema, forecastDateSchema, forecastOutputsSchema } from "./forecast.js";
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

const availableForecastSummarySchema = forecastSummaryIdentitySchema.extend({
  availability: z.literal("available"),
  generatedAt: z.iso.datetime(),
  provenance: provenanceSchema,
  outputs: forecastOutputsSchema,
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

export const forecastDaySchema = z.strictObject({
  forecastDate: forecastDateSchema,
  chance100KmPct: chancePctMetricSchema,
});

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
export type ForecastSummariesResponse = z.infer<typeof forecastSummariesResponseSchema>;
export type ForecastDaysQuery = z.infer<typeof forecastDaysQuerySchema>;
export type ForecastDay = z.infer<typeof forecastDaySchema>;
export type ForecastDaysResponse = z.infer<typeof forecastDaysResponseSchema>;
