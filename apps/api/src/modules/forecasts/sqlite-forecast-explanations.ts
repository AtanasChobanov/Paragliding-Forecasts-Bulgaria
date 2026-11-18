import {
  forecastDriverSchema,
  metricCodes,
  type AvailableForecastSummary,
  type ForecastExplanation,
} from "@paragliding-forecasts/contracts";
import type { DatabaseSync } from "node:sqlite";
import { z } from "zod";
import { requirePublishedValue } from "./require-published-value.js";
import type { SqliteForecastInputs } from "./sqlite-forecast-inputs.js";
const string = (value: unknown) => z.string().parse(value);

export const readExplanations = (
  database: DatabaseSync,
  predictionId: number,
  summary: AvailableForecastSummary,
  weather: SqliteForecastInputs,
): ForecastExplanation[] => {
  const drivers = database
    .prepare("SELECT * FROM prediction_drivers WHERE prediction_id = ? ORDER BY metric_code, rank")
    .all(predictionId);
  const inputs = database
    .prepare(
      `SELECT i.* FROM prediction_driver_inputs i
    JOIN prediction_drivers d ON d.id = i.prediction_driver_id
    WHERE d.prediction_id = ? ORDER BY i.prediction_driver_id, i.input_ordinal`,
    )
    .all(predictionId);
  const outputKeys = [
    "chance100KmPct",
    "chance200KmPct",
    "chance300KmPct",
    "overdevelopmentRisk",
    "cloudbase",
  ] as const;
  return metricCodes.map((metricCode, i) => {
    const metric = summary.outputs[requirePublishedValue(outputKeys[i])];
    const rows = drivers
      .filter((driver) => driver.metric_code === metricCode)
      .map((row) => {
        const inputRows = inputs.filter((input) => input.prediction_driver_id === row.id);
        const mappedInputs = inputRows.map((input) => {
          const key = string(input.input_key);
          const locator = {
            inputKey: key,
            ...(input.valid_at_utc === null ? {} : { validAtUtc: string(input.valid_at_utc) }),
            ...(input.interval_end_utc === null
              ? {}
              : { intervalEndUtc: string(input.interval_end_utc) }),
          };
          if (input.weather_field_provenance_id === null) {
            return {
              ...locator,
              unavailableReason:
                key === "profile"
                  ? "Exact input is retained in the ML artifact. The full T-022 model column includes levels below the launch and is not retained in SQL."
                  : "Exact input is retained in the ML artifact",
            };
          }
          const provenanceId = z.number().parse(input.weather_field_provenance_id);
          if (!weather.provenance.some((p) => p.id === provenanceId))
            throw new Error("Driver provenance is outside the selected snapshot input graph.");
          const fields = weather.resolved.filter(
            (field) => field.provenanceId === provenanceId && field.key === key,
          );
          const field = fields[0];
          if (!field || fields.some((other) => JSON.stringify(other) !== JSON.stringify(field)))
            throw new Error("Driver provenance does not resolve to its exact named input.");
          const context = weather.inputs.hourlyContext.find((hour) =>
            [...hour.odInputs, ...hour.cloudbaseContext].some(
              (f) => f.provenanceId === provenanceId,
            ),
          );
          if (
            input.valid_at_utc !== null &&
            (field.intervalStartUtc
              ? field.intervalStartUtc !== input.valid_at_utc ||
                field.intervalEndUtc !== input.interval_end_utc
              : context?.validAtUtc !== input.valid_at_utc || input.interval_end_utc !== null)
          )
            throw new Error("Driver time differs from its exact input owner.");
          return { ...locator, provenanceId, field };
        });
        return forecastDriverSchema.parse({
          kind: row.kind,
          code: row.code,
          message: row.message,
          rank: row.rank,
          ...(row.xc_stage === null ? {} : { xcStage: row.xc_stage }),
          ...(row.direction === null ? {} : { direction: row.direction }),
          ...(row.contribution_logit === null ? {} : { contributionLogit: row.contribution_logit }),
          ...(row.score_points === null ? {} : { scorePoints: row.score_points }),
          ...(row.support_successes === null ? {} : { supportSuccesses: row.support_successes }),
          ...(row.support_total === null ? {} : { supportTotal: row.support_total }),
          inputs: mappedInputs,
        });
      });
    return {
      metricCode,
      dataStatus: metric.dataStatus,
      confidenceLevel: metric.confidence?.level ?? null,
      ...(metric.dataStatus === "missing"
        ? {
            missingReason: metric.missingReason,
            ...(metric.confidenceNote ? { confidenceNote: metric.confidenceNote } : {}),
          }
        : metric.confidence.note
          ? { confidenceNote: metric.confidence.note }
          : {}),
      ...(metric.limitationsNote ? { limitationsNote: metric.limitationsNote } : {}),
      drivers: rows,
    };
  });
};
