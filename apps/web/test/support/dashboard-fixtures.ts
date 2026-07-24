import {
  forecastDaysResponseSchema,
  forecastResponseSchema,
  forecastSummariesResponseSchema,
  problemDetailsSchema,
  sitesResponseSchema,
  type Confidence,
  type ForecastDaysResponse,
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

const availableInput = <Value>(value: Value) => ({
  value,
  dataStatus: "mock" as const,
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

export const createSitesResponse = (): SitesResponse =>
  sitesResponseSchema.parse({
    sites: [
      {
        id: 1,
        slug: "sofia-vitosha-kominite",
        name: "Sofia - Vitosha (Kominite)",
        latitude: 42.60222,
        longitude: 23.28927,
      },
      {
        id: 2,
        slug: "zlatitsa",
        name: "Zlatitsa",
        latitude: 42.71506,
        longitude: 24.13749,
      },
      {
        id: 3,
        slug: "sopot",
        name: "Sopot",
        latitude: 42.68776,
        longitude: 24.74996,
      },
      {
        id: 4,
        slug: "nevsha",
        name: "Nevsha",
        latitude: 43.27155,
        longitude: 27.29945,
      },
      {
        id: 5,
        slug: "shumen",
        name: "Shumen",
        latitude: 43.27667,
        longitude: 26.92917,
      },
      {
        id: 6,
        slug: "pastrina",
        name: "Pastrina",
        latitude: 43.42481,
        longitude: 23.30355,
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
        provenance: {
          source: "t-003-t-005-mock-provider",
          version: "mock-v2",
        },
        outputs: createForecastOutputs(),
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
      { forecastDate: "2026-07-16", chance100KmPct: availableMetric(45) },
      { forecastDate: "2026-07-17", chance100KmPct: availableMetric(55) },
      { forecastDate: "2026-07-18", chance100KmPct: availableMetric(65) },
      { forecastDate: "2026-07-19", chance100KmPct: availableMetric(73) },
      { forecastDate: "2026-07-20", chance100KmPct: missingMetric },
    ],
  });

export const createForecastResponse = (): ForecastResponse =>
  forecastResponseSchema.parse({
    siteId: 3,
    siteSlug: "sopot",
    forecastDate: "2026-07-18",
    generatedAt: "2026-07-17T20:00:00.000Z",
    provenance: {
      source: "t-003-t-005-mock-provider",
      version: "mock-v2",
    },
    outputs: createForecastOutputs(),
    forecastInputs: {
      provenance: {
        source: "t-006-t-007-mock-weather-provider",
        version: "mock-weather-v1",
      },
      sourceRunAt: "2026-07-17T20:00:00.000Z",
      surfaceTemperatureC: availableInput(27.4),
      dewPointC: availableInput(14.2),
      boundaryLayerHeightM: availableInput(1_750),
      thermalStrengthMps: availableInput(3.2),
      boundaryLayerWindSpeedKmh: availableInput(18),
      boundaryLayerWindDirectionDeg: availableInput(225),
      windByAltitude: availableInput([{ altitudeMslM: 1_500, directionDeg: 225, speedKmh: 18 }]),
      windShearMpsPerKm: availableInput(2.4),
      relativeHumidityPct: availableInput(52),
      capeJPerKg: availableInput(840),
      cinJPerKg: availableInput(20),
      lapseRateCPerKm: availableInput(6.5),
      lowCloudCoverPct: availableInput(24),
      totalCloudCoverPct: availableInput(38),
      precipitationMm: availableInput(0),
      surfacePressureHpa: availableInput(1_008),
      convergenceSignal: availableInput("weak" as const),
    },
    topDrivers: ["Synthetic thermal strength", "Synthetic boundary-layer depth"],
  });

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
