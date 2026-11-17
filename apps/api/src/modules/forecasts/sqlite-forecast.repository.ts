import {
  confidenceLevelSchema,
  forecastDateSchema,
  siteIdSchema,
  siteSlugSchema,
  type AvailableForecastSummary,
  type DashboardCloudbase,
  type ForecastDate,
  type ForecastDay,
  type Site,
  type SiteId,
} from "@paragliding-forecasts/contracts";
import type { DatabaseSync, StatementSync } from "node:sqlite";
import { z } from "zod";

import { toForecastDate } from "./forecast-date.js";
import type { ForecastRepository } from "./forecast.repository.js";

// Filter by the requested site/date set before ranking. Join metric evidence only
// for the winning forecast so missing metrics never fall back independently.
const selectionSql = `
  WITH eligible_runs AS NOT MATERIALIZED (
    SELECT publication.id, publication.weather_ingestion_run_id,
           ingestion.target_local_date AS forecastDate,
           product.reference_at_utc AS cycleAtUtc,
           publication.created_at_utc AS generatedAt,
           publication.xc_model_id AS xcModelId,
           publication.cloudbase_method_version AS cloudbaseMethodVersion,
           publication.overdevelopment_policy_version AS overdevelopmentPolicyVersion
    FROM prediction_runs AS publication
    JOIN weather_ingestion_runs AS ingestion ON ingestion.id = publication.weather_ingestion_run_id
    JOIN weather_product_runs AS product ON product.id = ingestion.product_run_id
    JOIN weather_sources AS source ON source.id = product.source_id
    WHERE source.code = 'noaa_gfs_0p25_aws_grib2'
      AND product.reference_at_utc LIKE '%T06:00:00Z'
      AND ingestion.status = 'succeeded'
      AND ingestion.operational_use_allowed = 1
      AND ingestion.request_purpose = 'operational_forecast'
  ), ranked AS (
    SELECT prediction.*, site.id AS siteId, site.slug AS siteSlug, run.forecastDate,
           run.cycleAtUtc, run.generatedAt, run.xcModelId,
           run.cloudbaseMethodVersion, run.overdevelopmentPolicyVersion,
           ROW_NUMBER() OVER (
             PARTITION BY site.id, run.forecastDate
             ORDER BY run.cycleAtUtc DESC, run.generatedAt DESC, run.id DESC, prediction.id DESC
           ) AS preference
    FROM eligible_runs AS run
    JOIN predictions AS prediction ON prediction.prediction_run_id = run.id
    JOIN weather_daily_feature_snapshots AS snapshot
      ON snapshot.id = prediction.daily_feature_snapshot_id
      AND snapshot.ingestion_run_id = run.weather_ingestion_run_id
    JOIN weather_sampling_footprints AS footprint ON footprint.id = snapshot.point_footprint_id
    JOIN sites AS site ON site.id = footprint.site_id
    WHERE site.is_active = 1 AND site.id IN (SELECT value FROM json_each(?))
      AND run.forecastDate BETWEEN ? AND ?
  )
`;

const metricSql = `json_object(
  'status', metric.data_status, 'confidence', metric.confidence_level,
  'note', metric.confidence_note, 'reason', metric.missing_reason_code,
  'limitations', metric.limitations_note
)`;

const metricDetailsSchema = z.object({
  status: z.enum(["baseline", "missing"]),
  confidence: confidenceLevelSchema.nullable(),
  note: z.string().nullable(),
  reason: z.string().nullable(),
  limitations: z.string().nullable(),
});
type MetricDetails = z.infer<typeof metricDetailsSchema>;

const dayRowSchema = z.object({
  forecastDate: forecastDateSchema,
  p100: z.number().nullable(),
  metric: z.string(),
});

const summaryRowSchema = z.object({
  siteId: siteIdSchema,
  siteSlug: siteSlugSchema,
  forecastDate: forecastDateSchema,
  cycleAtUtc: z.iso.datetime(),
  latestCycleAtUtc: z.iso.datetime(),
  generatedAt: z.iso.datetime(),
  xcModelId: z.string(),
  cloudbaseMethodVersion: z.string(),
  overdevelopmentPolicyVersion: z.string(),
  p100: z.number().nullable(),
  p200: z.number().nullable(),
  p300: z.number().nullable(),
  risk: z.enum(["low", "medium", "high"]).nullable(),
  score: z.number().nullable(),
  cloudbaseState: z.enum([
    "cloudbase_available",
    "potential_base_available",
    "blue",
    "other_cloud",
    "indeterminate",
    "missing",
  ]),
  height: z.number().nullable(),
  hourRegime: z.string().nullable(),
  metrics: z.string(),
});

type SummaryRow = z.infer<typeof summaryRowSchema>;

const summaryMetricsSchema = z.strictObject({
  p100: metricDetailsSchema,
  p200: metricDetailsSchema,
  p300: metricDetailsSchema,
  overdevelopment: metricDetailsSchema,
  cloudbase: metricDetailsSchema,
});

const missingReasons = new Map([
  ["required_inputs_missing", "Required weather inputs are missing."],
  ["insufficient_weather_evidence", "Required forecast evidence is missing in the flying window."],
  ["surface_or_model_terrain_missing", "Surface or model terrain data is missing."],
  ["required_source_input_unavailable", "Required GFS inputs are unavailable."],
  ["model_profile_missing", "The model profile is missing."],
  [
    "insufficient_300_support",
    "There are too few training flights to estimate the 300+ km chance.",
  ],
]);

const availableDetails = ({ status, confidence, note, limitations }: MetricDetails) => {
  if (status !== "baseline" || confidence === null) {
    throw new Error("A published value is missing its baseline metric details.");
  }

  return {
    dataStatus: status,
    confidence: { level: confidence, note: note ?? undefined },
    limitationsNote: limitations ?? undefined,
  };
};

const missingDetails = ({ status, confidence, note, reason, limitations }: MetricDetails) => {
  if (status !== "missing" || confidence !== null || reason === null) {
    throw new Error("A missing published value has inconsistent metric details.");
  }

  return {
    dataStatus: status,
    confidence,
    confidenceNote: note ?? undefined,
    missingReason: missingReasons.get(reason) ?? "No value is available for this metric.",
    limitationsNote: limitations ?? undefined,
  };
};

const chanceMetric = (
  value: number | null,
  details: MetricDetails,
): ForecastDay["chance100KmPct"] =>
  value === null
    ? { ...missingDetails(details), value }
    : { ...availableDetails(details), value: value * 100 };

const cloudbaseMetric = (row: SummaryRow, details: MetricDetails): DashboardCloudbase => {
  const state = row.cloudbaseState;
  switch (state) {
    case "cloudbase_available":
    case "potential_base_available": {
      const estimated = state === "cloudbase_available";
      if (row.height === null || row.hourRegime !== (estimated ? "cumulus" : "indeterminate")) {
        throw new Error(
          "The published cloudbase maximum has no matching hourly height and regime.",
        );
      }
      return {
        ...availableDetails(details),
        kind: estimated ? "estimated" : "conditional_lcl",
        valueMslM: row.height,
      };
    }
    case "missing":
      return { ...missingDetails(details), kind: state };
    default:
      return { ...availableDetails(details), kind: state };
  }
};

const horizonSchema = z.literal([1, 2, 3]);
const forecastHorizon = (issueDate: ForecastDate, target: ForecastDate): number =>
  (Date.parse(target) - Date.parse(issueDate)) / 86_400_000;

const mapSummary = (row: SummaryRow, today: ForecastDate): AvailableForecastSummary => {
  const metrics = summaryMetricsSchema.parse(JSON.parse(row.metrics));
  const issueDate = toForecastDate(new Date(row.cycleAtUtc));
  const latestIssueDate = toForecastDate(new Date(row.latestCycleAtUtc));
  const latestHorizon = forecastHorizon(latestIssueDate, row.forecastDate);

  return {
    availability: "available",
    siteId: row.siteId,
    siteSlug: row.siteSlug,
    forecastDate: row.forecastDate,
    generatedAt: row.generatedAt,
    metadata: {
      mode: "sqlite",
      source: "NOAA GFS",
      cycleAtUtc: row.cycleAtUtc,
      horizonDays: horizonSchema.parse(forecastHorizon(issueDate, row.forecastDate)),
      xcModelId: row.xcModelId,
      cloudbaseMethodVersion: row.cloudbaseMethodVersion,
      overdevelopmentPolicyVersion: row.overdevelopmentPolicyVersion,
      fromPreviousIssue:
        row.forecastDate > today &&
        row.cycleAtUtc < row.latestCycleAtUtc &&
        latestHorizon >= 1 &&
        latestHorizon <= 3,
    },
    outputs: {
      chance100KmPct: chanceMetric(row.p100, metrics.p100),
      chance200KmPct: chanceMetric(row.p200, metrics.p200),
      chance300KmPct: chanceMetric(row.p300, metrics.p300),
      cloudbase: cloudbaseMetric(row, metrics.cloudbase),
      overdevelopmentRisk:
        row.risk === null
          ? { ...missingDetails(metrics.overdevelopment), value: null }
          : {
              ...availableDetails(metrics.overdevelopment),
              value: row.risk,
              score: row.score ?? undefined,
            },
    },
  };
};

export class SqliteForecastRepository implements ForecastRepository {
  readonly #summaries: StatementSync;
  readonly #days: StatementSync;

  constructor(database: DatabaseSync) {
    this.#summaries = database.prepare(`${selectionSql}
      , latest AS (
        SELECT MAX(run.cycleAtUtc) AS cycleAtUtc
        FROM eligible_runs AS run
        WHERE EXISTS (SELECT 1 FROM predictions WHERE prediction_run_id = run.id)
      )
      SELECT chosen.siteId, chosen.siteSlug, chosen.forecastDate, chosen.cycleAtUtc,
             latest.cycleAtUtc AS latestCycleAtUtc, chosen.generatedAt, chosen.xcModelId,
             chosen.cloudbaseMethodVersion, chosen.overdevelopmentPolicyVersion,
             chosen.p_100km AS p100, chosen.p_200km AS p200, chosen.p_300km AS p300,
             chosen.overdevelopment_risk AS risk, chosen.overdevelopment_score AS score,
             chosen.cloudbase_summary_state AS cloudbaseState, hour.regime AS hourRegime,
             hour.estimated_cloudbase_msl_m AS height,
             (SELECT json_group_object(metric.metric_code, ${metricSql})
              FROM prediction_metric_details AS metric WHERE metric.prediction_id = chosen.id) AS metrics
      FROM ranked AS chosen
      CROSS JOIN latest
      LEFT JOIN prediction_cloudbase_hours AS hour
        ON hour.prediction_id = chosen.id AND hour.valid_at_utc =
          CASE chosen.cloudbase_summary_state
            WHEN 'cloudbase_available' THEN chosen.cloudbase_max_at_utc
            WHEN 'potential_base_available' THEN chosen.conditional_lcl_max_at_utc
          END
      WHERE chosen.preference = 1
    `);
    this.#days = database.prepare(`${selectionSql}
      SELECT chosen.forecastDate, chosen.p_100km AS p100, ${metricSql} AS metric
      FROM ranked AS chosen
      LEFT JOIN prediction_metric_details AS metric ON metric.prediction_id = chosen.id
        AND metric.metric_code = 'p100'
      WHERE chosen.preference = 1
    `);
  }

  listSummaries(sites: readonly Site[], date: ForecastDate, todayDate: ForecastDate) {
    const rows = this.#summaries.all(JSON.stringify(sites.map(({ id }) => id)), date, date);
    return Promise.resolve(rows.map((row) => mapSummary(summaryRowSchema.parse(row), todayDate)));
  }

  listDays(siteId: SiteId, fromDate: ForecastDate, throughDate: ForecastDate) {
    const rows = this.#days.all(JSON.stringify([siteId]), fromDate, throughDate);
    return Promise.resolve(
      rows.map((row): Extract<ForecastDay, { availability: "available" }> => {
        const day = dayRowSchema.parse(row);
        return {
          availability: "available",
          forecastDate: day.forecastDate,
          chance100KmPct: chanceMetric(day.p100, metricDetailsSchema.parse(JSON.parse(day.metric))),
        };
      }),
    );
  }
}
