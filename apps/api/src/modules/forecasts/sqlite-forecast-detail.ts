import { readExplanations } from "./sqlite-forecast-explanations.js";
import { requirePublishedValue } from "./require-published-value.js";
import {
  cloudbaseHourSchema,
  forecastResponseSchema,
  type AvailableForecastSummary,
} from "@paragliding-forecasts/contracts";
import type { DatabaseSync } from "node:sqlite";
import { z } from "zod";

import { cloudbaseReasonText } from "./cloudbase-reasons.js";
import { SqliteForecastInputs, type SqlRow } from "./sqlite-forecast-inputs.js";

const string = (value: unknown) => z.string().parse(value);

export const readSqliteForecastDetail = (
  database: DatabaseSync,
  chosen: SqlRow,
  summary: AvailableForecastSummary,
) => {
  const predictionId = z.number().parse(chosen.predictionId);
  const weather = new SqliteForecastInputs(
    database,
    z.number().parse(chosen.snapshotId),
    summary.forecastDate,
  );
  const hours = database
    .prepare(
      "SELECT * FROM prediction_cloudbase_hours WHERE prediction_id = ? ORDER BY valid_at_utc",
    )
    .all(predictionId)
    .map((row) =>
      cloudbaseHourSchema.parse({
        validAtUtc: row.valid_at_utc,
        regime: row.regime,
        heightMslM: row.estimated_cloudbase_msl_m,
        heightModelAglM: row.estimated_cloudbase_model_agl_m,
        heightSiteAglM: row.estimated_cloudbase_site_agl_m,
        confidenceLevel: row.confidence_level,
        reasonCode: row.reason_code,
        reasonText: cloudbaseReasonText(string(row.reason_code)),
        ...(row.note === null ? {} : { note: row.note }),
      }),
    );
  for (const [regime, column] of [
    ["cumulus", "cloudbaseMaxAtUtc"],
    ["indeterminate", "conditionalLclMaxAtUtc"],
  ] as const) {
    const candidates = hours.filter((hour) => hour.regime === regime && hour.heightMslM !== null);
    const maximum = candidates.reduce<(typeof candidates)[number] | undefined>(
      (best, hour) =>
        !best || requirePublishedValue(hour.heightMslM) > requirePublishedValue(best.heightMslM)
          ? hour
          : best,
      undefined,
    );
    if ((maximum?.validAtUtc ?? null) !== chosen[column])
      throw new Error("Published cloudbase maximum differs from its own hourly maximum.");
  }
  const forecast = {
    siteId: summary.siteId,
    siteSlug: summary.siteSlug,
    forecastDate: summary.forecastDate,
    generatedAt: summary.generatedAt,
    metadata: summary.metadata,
    outputs: summary.outputs,
  };
  return forecastResponseSchema.parse({
    ...forecast,
    forecastInputs: weather.inputs,
    cloudbaseHours: hours,
    explanations: readExplanations(database, predictionId, summary, weather),
  });
};
