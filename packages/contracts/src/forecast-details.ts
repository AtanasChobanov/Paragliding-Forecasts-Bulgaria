import { z } from "zod";

import { confidenceLevelSchema, dataStatusSchema } from "./data-status.js";
import { dashboardMetadataSchema, dashboardOutputsSchema } from "./dashboard-forecasts.js";
import { forecastDateSchema } from "./forecast.js";
import { siteIdSchema, siteSlugSchema } from "./sites.js";
import { xcInputInventory } from "./xc-input-inventory.js";

const text = z.string().trim().min(1);
const instant = z.iso.datetime();
export const metricCodes = ["p100", "p200", "p300", "overdevelopment", "cloudbase"] as const;
export const forecastInputRowSchema = z
  .strictObject({
    key: text,
    label: text,
    group: text,
    scope: text,
    unit: text,
    value: z.number().nullable(),
    dataStatus: dataStatusSchema,
    qualityState: text,
    missingReason: text.optional(),
    provenanceId: z.number().int().positive().optional(),
    statistic: text,
    layerBaseAglM: z.number().optional(),
    layerTopAglM: z.number().optional(),
    intervalStartUtc: instant.optional(),
    intervalEndUtc: instant.optional(),
  })
  .superRefine((row, ctx) => {
    if (
      (row.value === null) !== (row.dataStatus === "missing") ||
      (row.value === null && !row.missingReason)
    ) {
      ctx.addIssue({ code: "custom", message: "Input value, status and missing reason disagree." });
    }
    if (
      (row.intervalStartUtc === undefined) !== (row.intervalEndUtc === undefined) ||
      (row.intervalStartUtc && row.intervalEndUtc && row.intervalStartUtc > row.intervalEndUtc)
    ) {
      ctx.addIssue({ code: "custom", message: "Invalid input interval." });
    }
  });

export const forecastDetailInputsSchema = z
  .strictObject({
    windowStartUtc: instant,
    windowEndUtc: instant,
    featureContractVersion: text,
    xcFeatures: z.array(forecastInputRowSchema).length(67),
    hourlyContext: z
      .array(
        z.strictObject({
          validAtUtc: instant,
          odInputs: z.array(forecastInputRowSchema),
          cloudbaseContext: z.array(forecastInputRowSchema),
        }),
      )
      .length(11),
  })
  .superRefine((inputs, ctx) => {
    inputs.xcFeatures.forEach((row, i) => {
      const spec = xcInputInventory[i];
      if (row.key !== spec?.key || row.unit !== spec.unit || row.scope !== spec.scope) {
        ctx.addIssue({
          code: "custom",
          path: ["xcFeatures", i],
          message: "Expected the fixed XC policy inventory in policy order.",
        });
      }
    });
  });

export const forecastDriverSchema = z
  .strictObject({
    kind: z.enum([
      "xc_contribution",
      "pooled_conversion",
      "od_override",
      "od_score_component",
      "cloudbase_reason",
    ]),
    code: text,
    message: text,
    rank: z.number().int().min(1).max(3),
    xcStage: z.enum(["p100", "q200"]).optional(),
    direction: z.enum(["raises", "lowers", "zero"]).optional(),
    contributionLogit: z.number().optional(),
    scorePoints: z.number().min(0).max(100).optional(),
    supportSuccesses: z.number().int().nonnegative().optional(),
    supportTotal: z.number().int().positive().optional(),
    inputs: z.array(
      z.strictObject({
        inputKey: text,
        validAtUtc: instant.optional(),
        intervalEndUtc: instant.optional(),
        provenanceId: z.number().int().positive().optional(),
        field: forecastInputRowSchema.optional(),
        unavailableReason: text.optional(),
      }),
    ),
  })
  .superRefine((driver, ctx) => {
    const xc = driver.kind === "xc_contribution";
    if (
      xc !==
        (driver.xcStage !== undefined &&
          driver.direction !== undefined &&
          driver.contributionLogit !== undefined) ||
      (!xc &&
        (driver.xcStage !== undefined ||
          driver.direction !== undefined ||
          driver.contributionLogit !== undefined))
    ) {
      ctx.addIssue({ code: "custom", message: "Driver contribution fields disagree with kind." });
    }
    if (
      driver.kind === "pooled_conversion" &&
      (driver.supportSuccesses === undefined ||
        driver.supportTotal === undefined ||
        driver.supportSuccesses > driver.supportTotal)
    ) {
      ctx.addIssue({ code: "custom", message: "Pooled conversion requires published support." });
    }
  });

export const forecastExplanationSchema = z
  .strictObject({
    metricCode: z.enum(metricCodes),
    dataStatus: dataStatusSchema,
    confidenceLevel: confidenceLevelSchema.nullable(),
    confidenceNote: text.optional(),
    missingReason: text.optional(),
    limitationsNote: text.optional(),
    drivers: z.array(forecastDriverSchema).max(3),
  })
  .superRefine((group, ctx) => {
    let rank = 0;
    for (const driver of group.drivers) {
      if (
        driver.rank <= rank ||
        (driver.kind === "xc_contribution" &&
          driver.xcStage !==
            (group.metricCode === "p100" ? "p100" : group.metricCode === "p200" ? "q200" : "")) ||
        (driver.kind === "pooled_conversion" && group.metricCode !== "p300") ||
        (driver.kind.startsWith("od_") && group.metricCode !== "overdevelopment") ||
        (driver.kind === "cloudbase_reason" && group.metricCode !== "cloudbase")
      ) {
        ctx.addIssue({
          code: "custom",
          message: "Driver rank or metric association is inconsistent.",
        });
      }
      rank = driver.rank;
    }
  });

export const cloudbaseHourSchema = z
  .strictObject({
    validAtUtc: instant,
    regime: z.enum(["cumulus", "blue", "other_cloud", "indeterminate", "missing"]),
    heightMslM: z.number().nullable(),
    heightModelAglM: z.number().nonnegative().nullable(),
    heightSiteAglM: z.number().nullable(),
    confidenceLevel: confidenceLevelSchema.nullable(),
    reasonCode: text,
    reasonText: text,
    note: text.optional(),
  })
  .superRefine((hour, ctx) => {
    const heights = [hour.heightMslM, hour.heightModelAglM, hour.heightSiteAglM];
    const full = heights.every((value) => value !== null);
    const empty = heights.every((value) => value === null);
    if (
      (hour.regime === "cumulus" && !full) ||
      (hour.regime === "indeterminate" && !full && !empty) ||
      (!["cumulus", "indeterminate"].includes(hour.regime) && !empty) ||
      (hour.regime === "missing" && hour.confidenceLevel !== null) ||
      (hour.regime !== "missing" && hour.confidenceLevel === null)
    ) {
      ctx.addIssue({ code: "custom", message: "Hourly regime, heights and confidence disagree." });
    }
  });

// Date-sensitive Sofia offset, including transition days; no host timezone dependency.
export const sofiaFlyingHours = (date: string): string[] => {
  const format = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Europe/Sofia",
    hour: "2-digit",
    hourCycle: "h23",
  });
  const noon = Date.parse(`${date}T12:00:00Z`);
  const offset = Number(format.format(new Date(noon))) - 12;
  return Array.from({ length: 11 }, (_, i) =>
    new Date(Date.parse(`${date}T00:00:00Z`) + (10 + i - offset) * 3_600_000)
      .toISOString()
      .replace(".000Z", "Z"),
  );
};

export const forecastResponseSchema = z
  .strictObject({
    siteId: siteIdSchema,
    siteSlug: siteSlugSchema,
    forecastDate: forecastDateSchema,
    generatedAt: instant,
    metadata: dashboardMetadataSchema,
    outputs: dashboardOutputsSchema,
    forecastInputs: forecastDetailInputsSchema,
    explanations: z.array(forecastExplanationSchema).length(5),
    cloudbaseHours: z.array(cloudbaseHourSchema).length(11),
  })
  .superRefine((forecast, ctx) => {
    const hours = sofiaFlyingHours(forecast.forecastDate);
    const sameInstant = (a: string | undefined, b: string | undefined) =>
      a !== undefined && b !== undefined && Date.parse(a) === Date.parse(b);
    if (
      !sameInstant(forecast.forecastInputs.windowStartUtc, hours[0]) ||
      !sameInstant(forecast.forecastInputs.windowEndUtc, hours[10])
    ) {
      ctx.addIssue({
        code: "custom",
        message: "Flying window differs from the Sofia target date.",
      });
    }
    forecast.cloudbaseHours.forEach((hour, i) => {
      if (
        !sameInstant(hour.validAtUtc, hours[i]) ||
        !sameInstant(forecast.forecastInputs.hourlyContext[i]?.validAtUtc, hours[i])
      ) {
        ctx.addIssue({
          code: "custom",
          path: ["cloudbaseHours", i],
          message: "Expected eleven ordered Sofia flying hours.",
        });
      }
    });
    const outputKeys = [
      "chance100KmPct",
      "chance200KmPct",
      "chance300KmPct",
      "overdevelopmentRisk",
      "cloudbase",
    ] as const;
    forecast.explanations.forEach((group, i) => {
      const metric = forecast.outputs[outputKeys[i] ?? "cloudbase"];
      if (
        group.metricCode !== metricCodes[i] ||
        group.dataStatus !== metric.dataStatus ||
        group.confidenceLevel !== (metric.confidence?.level ?? null) ||
        (metric.dataStatus === "missing" && group.missingReason !== metric.missingReason)
      ) {
        ctx.addIssue({
          code: "custom",
          path: ["explanations", i],
          message: "Explanation and metric evidence differ.",
        });
      }
    });
    const estimated = forecast.cloudbaseHours.filter((hour) => hour.regime === "cumulus");
    const conditional = forecast.cloudbaseHours.filter(
      (hour) => hour.regime === "indeterminate" && hour.heightMslM !== null,
    );
    const numeric = estimated.length ? estimated : conditional;
    const cloud = forecast.outputs.cloudbase;
    const expectedKind = estimated.length
      ? "estimated"
      : conditional.length
        ? "conditional_lcl"
        : undefined;
    if (
      expectedKind
        ? cloud.kind !== expectedKind ||
          !("valueMslM" in cloud) ||
          cloud.valueMslM !== Math.max(...numeric.map((hour) => hour.heightMslM ?? -Infinity))
        : ["estimated", "conditional_lcl"].includes(cloud.kind)
    ) {
      ctx.addIssue({
        code: "custom",
        path: ["outputs", "cloudbase"],
        message: "Daily cloudbase does not match its own hourly maximum.",
      });
    }
  });

export type ForecastInputRow = z.infer<typeof forecastInputRowSchema>;
export type ForecastDetailInputs = z.infer<typeof forecastDetailInputsSchema>;
export type ForecastDriver = z.infer<typeof forecastDriverSchema>;
export type ForecastExplanation = z.infer<typeof forecastExplanationSchema>;
export type CloudbaseHour = z.infer<typeof cloudbaseHourSchema>;
export type ForecastResponse = z.infer<typeof forecastResponseSchema>;
