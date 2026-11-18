import { mockForecastDetail } from "../../../api/src/modules/forecasts/mock-forecast-detail.js";
import {
  forecastDaysResponseSchema,
  forecastResponseSchema,
  forecastSummariesResponseSchema,
  problemDetailsSchema,
  sitesResponseSchema,
  type Confidence,
  type ForecastDaysResponse,
  type DashboardForecastOutputs,
  type ForecastResponse,
  type ForecastOutputs,
  type ForecastSummariesResponse,
  type ProblemDetails,
  type SitesResponse,
} from "@paragliding-forecasts/contracts";

const mockConfidence = {
  level: "low",
  note: "Synthetic demonstration value.",
} as const satisfies Confidence;

const availableMetric = <Value>(value: Value) => ({
  value,
  dataStatus: "mock" as const,
  confidence: mockConfidence,
});

export const missingMetric = {
  value: null,
  dataStatus: "missing" as const,
  confidence: null,
  missingReason: "No forecast run is available for this site and date.",
};

export const createForecastOutputs = (): ForecastOutputs => ({
  cloudbaseMslM: availableMetric(2_400),
  chance100KmPct: availableMetric(65),
  chance200KmPct: availableMetric(35),
  chance300KmPct: availableMetric(12),
  overdevelopmentRisk: availableMetric("medium" as const),
});

export const createDashboardOutputs = (): DashboardForecastOutputs => {
  const { cloudbaseMslM, ...outputs } = createForecastOutputs();
  return {
    ...outputs,
    cloudbase:
      cloudbaseMslM.dataStatus === "missing"
        ? {
            kind: "missing",
            dataStatus: "missing",
            confidence: null,
            missingReason: cloudbaseMslM.missingReason,
          }
        : {
            kind: "estimated",
            dataStatus: cloudbaseMslM.dataStatus,
            confidence: cloudbaseMslM.confidence,
            valueMslM: cloudbaseMslM.value,
          },
  };
};

export const createSitesResponse = (): SitesResponse =>
  sitesResponseSchema.parse({
    sites: [
      {
        id: 1,
        slug: "sofia-vitosha-kominite",
        name: "Sofia - Vitosha (Kominite)",
        latitude: 42.6013,
        longitude: 23.2844,
      },
      {
        id: 2,
        slug: "zlatitsa",
        name: "Zlatitsa",
        latitude: 42.7302,
        longitude: 24.0923,
      },
      {
        id: 3,
        slug: "sopot",
        name: "Sopot",
        latitude: 42.68733,
        longitude: 24.749962,
      },
      {
        id: 4,
        slug: "nevsha",
        name: "Nevsha",
        latitude: 43.2622,
        longitude: 27.2846,
      },
      {
        id: 5,
        slug: "shumen",
        name: "Shumen",
        latitude: 43.2575,
        longitude: 26.9258,
      },
      {
        id: 6,
        slug: "pastrina",
        name: "Pastrina",
        latitude: 43.4282,
        longitude: 23.3032,
      },
      {
        id: 7,
        slug: "dobrich-region",
        name: "Dobrich region",
        latitude: 43.56667,
        longitude: 27.83333,
      },
    ],
  });

export const createForecastSummariesResponse = (): ForecastSummariesResponse =>
  forecastSummariesResponseSchema.parse({
    forecastDate: "2026-07-18",
    summaries: [
      {
        availability: "missing",
        siteId: 2,
        siteSlug: "zlatitsa",
        forecastDate: "2026-07-18",
        missingReason: "No forecast exists for Zlatitsa on 2026-07-18.",
      },
      {
        availability: "available",
        siteId: 3,
        siteSlug: "sopot",
        forecastDate: "2026-07-18",
        generatedAt: "2026-07-17T20:00:00.000Z",
        metadata: {
          mode: "mock",
          source: "t-003-t-005-mock-provider",
          version: "mock-v2",
        },
        outputs: createDashboardOutputs(),
      },
    ],
  });

export const createForecastDaysResponse = (): ForecastDaysResponse =>
  forecastDaysResponseSchema.parse({
    siteId: 3,
    siteSlug: "sopot",
    timeZone: "Europe/Sofia",
    todayDate: "2026-07-18",
    days: [
      {
        availability: "available",
        forecastDate: "2026-07-16",
        chance100KmPct: availableMetric(45),
      },
      {
        availability: "available",
        forecastDate: "2026-07-17",
        chance100KmPct: availableMetric(55),
      },
      {
        availability: "available",
        forecastDate: "2026-07-18",
        chance100KmPct: availableMetric(65),
      },
      {
        availability: "available",
        forecastDate: "2026-07-19",
        chance100KmPct: availableMetric(73),
      },
      {
        availability: "missing",
        forecastDate: "2026-07-20",
        chance100KmPct: missingMetric,
        missingReason: missingMetric.missingReason,
      },
    ],
  });

export const createForecastResponse = (): ForecastResponse => {
  const summary = createForecastSummariesResponse().summaries[1];
  if (summary?.availability !== "available") throw new Error("Expected fixture forecast");
  return forecastResponseSchema.parse(
    mockForecastDetail(summary, ["Synthetic thermal strength", "Synthetic boundary-layer depth"]),
  );
};

export const createValidationProblem = (): ProblemDetails =>
  problemDetailsSchema.parse({
    type: "urn:paragliding-forecasts:problem:validation-error",
    title: "Invalid request",
    status: 400,
    detail: "The request query is invalid.",
    code: "VALIDATION_ERROR",
    requestId: "request-validation-error",
    issues: [{ path: "siteSlug", message: "Expected a known site slug." }],
  });

export const createInternalServerProblem = (): ProblemDetails =>
  problemDetailsSchema.parse({
    type: "urn:paragliding-forecasts:problem:internal-server-error",
    title: "Internal server error",
    status: 500,
    detail: "An unexpected error occurred.",
    code: "INTERNAL_SERVER_ERROR",
    requestId: "request-internal-error",
  });
