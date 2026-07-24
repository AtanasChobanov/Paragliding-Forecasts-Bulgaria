import { HttpResponse, delay, http } from "msw";
import { describe, expect, it } from "vitest";

import { createApiClient } from "../../src/services/api/api-client.js";
import {
  ApiHttpError,
  ApiNetworkError,
  ApiResponseError,
} from "../../src/services/api/api-errors.js";
import { createDashboardApi } from "../../src/services/api/dashboard-api.js";
import {
  createForecastDaysResponse,
  createForecastResponse,
  createForecastSummariesResponse,
  createInternalServerProblem,
  createSitesResponse,
  createValidationProblem,
} from "../support/dashboard-fixtures.js";
import { server } from "../support/server.js";

const API_BASE_URL = "https://forecast-api.example.test/local";
const SITES_URL = `${API_BASE_URL}/api/v1/sites`;
const SUMMARIES_URL = `${API_BASE_URL}/api/v1/forecasts/summaries`;
const DAYS_URL = `${API_BASE_URL}/api/v1/forecasts/days`;
const FORECAST_URL = `${API_BASE_URL}/api/v1/forecasts`;

const createTestApi = () => createDashboardApi(createApiClient({ baseUrl: API_BASE_URL }));
const createSignal = () => new AbortController().signal;

const captureError = async (request: Promise<unknown>): Promise<unknown> => {
  try {
    await request;
  } catch (error) {
    return error;
  }

  throw new Error("Expected the API request to reject.");
};

describe("dashboard API client", () => {
  it("parses the site catalog with the shared response schema", async () => {
    const expected = createSitesResponse();
    server.use(http.get(SITES_URL, () => HttpResponse.json(expected)));

    await expect(createTestApi().listSites(createSignal())).resolves.toEqual(expected);
  });

  it("encodes summaries as one date and one comma-separated siteSlugs parameter", async () => {
    const expected = createForecastSummariesResponse();
    let receivedUrl: URL | undefined;
    server.use(
      http.get(SUMMARIES_URL, ({ request }) => {
        receivedUrl = new URL(request.url);
        return HttpResponse.json(expected);
      }),
    );

    await expect(
      createTestApi().getForecastSummaries({
        date: "2026-07-18",
        siteSlugs: ["zlatitsa", "sopot"],
        signal: createSignal(),
      }),
    ).resolves.toEqual(expected);

    expect(receivedUrl?.searchParams.getAll("date")).toEqual(["2026-07-18"]);
    expect(receivedUrl?.searchParams.getAll("siteSlugs")).toEqual(["zlatitsa,sopot"]);
    expect([...(receivedUrl?.searchParams.keys() ?? [])]).toEqual(["date", "siteSlugs"]);
  });

  it("encodes the selected site and parses the fixed five-day response", async () => {
    const expected = createForecastDaysResponse();
    let receivedUrl: URL | undefined;
    server.use(
      http.get(DAYS_URL, ({ request }) => {
        receivedUrl = new URL(request.url);
        return HttpResponse.json(expected);
      }),
    );

    await expect(
      createTestApi().getForecastDays({ siteSlug: "sopot", signal: createSignal() }),
    ).resolves.toEqual(expected);
    expect(receivedUrl?.searchParams.getAll("siteSlug")).toEqual(["sopot"]);
  });

  it("encodes a detailed site/date lookup and validates the detailed response", async () => {
    const expected = createForecastResponse();
    let receivedUrl: URL | undefined;
    server.use(
      http.get(FORECAST_URL, ({ request }) => {
        receivedUrl = new URL(request.url);
        return HttpResponse.json(expected);
      }),
    );

    await expect(
      createTestApi().getForecastDetail({
        date: "2026-07-18",
        siteSlug: "sopot",
        signal: createSignal(),
      }),
    ).resolves.toEqual(expected);
    expect(receivedUrl?.searchParams.getAll("siteSlug")).toEqual(["sopot"]);
    expect(receivedUrl?.searchParams.getAll("date")).toEqual(["2026-07-18"]);
  });

  it("retains validated Problem Details for a 4xx response without making it retryable", async () => {
    const problem = createValidationProblem();
    server.use(
      http.get(SITES_URL, () =>
        HttpResponse.json(problem, {
          status: 400,
          headers: { "X-Request-Id": problem.requestId },
        }),
      ),
    );

    const error = await captureError(createTestApi().listSites(createSignal()));

    expect(error).toBeInstanceOf(ApiHttpError);
    expect(error).toMatchObject({
      kind: "http",
      status: 400,
      code: "VALIDATION_ERROR",
      requestId: "request-validation-error",
      retryable: false,
      message: "The request query is invalid.",
    });
  });

  it("retains validated Problem Details for a retryable 5xx response", async () => {
    const problem = createInternalServerProblem();
    server.use(http.get(SITES_URL, () => HttpResponse.json(problem, { status: 500 })));

    const error = await captureError(createTestApi().listSites(createSignal()));

    expect(error).toBeInstanceOf(ApiHttpError);
    expect(error).toMatchObject({
      status: 500,
      code: "INTERNAL_SERVER_ERROR",
      requestId: "request-internal-error",
      retryable: true,
    });
  });

  it("classifies a failed fetch as a retryable network error", async () => {
    server.use(http.get(SITES_URL, () => HttpResponse.error()));

    const error = await captureError(createTestApi().listSites(createSignal()));

    expect(error).toBeInstanceOf(ApiNetworkError);
    expect(error).toMatchObject({ kind: "network", retryable: true });
  });

  it("forwards cancellation without wrapping the AbortError as a network failure", async () => {
    server.use(
      http.get(SITES_URL, async () => {
        await delay("infinite");
        return HttpResponse.json(createSitesResponse());
      }),
    );
    const controller = new AbortController();
    const request = createTestApi().listSites(controller.signal);

    controller.abort();
    const error = await captureError(request);

    expect(error).toMatchObject({ name: "AbortError" });
    expect(error).not.toBeInstanceOf(ApiNetworkError);
  });

  it("rejects malformed JSON from a successful response", async () => {
    server.use(
      http.get(
        SITES_URL,
        () =>
          new HttpResponse("{", { status: 200, headers: { "Content-Type": "application/json" } }),
      ),
    );

    const error = await captureError(createTestApi().listSites(createSignal()));

    expect(error).toBeInstanceOf(ApiResponseError);
    expect(error).toMatchObject({ reason: "malformed-json", retryable: false, status: 200 });
  });

  it("rejects a successful payload that violates the shared schema", async () => {
    server.use(http.get(SITES_URL, () => HttpResponse.json({ sites: "not-an-array" })));

    const error = await captureError(createTestApi().listSites(createSignal()));

    expect(error).toBeInstanceOf(ApiResponseError);
    expect(error).toMatchObject({ reason: "schema-validation", retryable: false, status: 200 });
  });

  it.each([
    ["malformed Problem Details JSON", "{", "application/problem+json"],
    ["an intermediary HTML response", "<h1>Bad gateway secret</h1>", "text/html"],
  ])("uses a safe HTTP fallback for %s", async (_description, body, contentType) => {
    server.use(
      http.get(
        SITES_URL,
        () =>
          new HttpResponse(body, {
            status: 502,
            headers: { "Content-Type": contentType, "X-Request-Id": "gateway-request-id" },
          }),
      ),
    );

    const error = await captureError(createTestApi().listSites(createSignal()));

    expect(error).toBeInstanceOf(ApiHttpError);
    expect(error).toMatchObject({
      status: 502,
      problem: null,
      requestId: "gateway-request-id",
      retryable: true,
    });
    expect((error as Error).message).not.toContain(body);
  });

  it("uses the actual HTTP status when a Problem Details body reports another status", async () => {
    const problem = createInternalServerProblem();
    server.use(http.get(SITES_URL, () => HttpResponse.json(problem, { status: 503 })));

    const error = await captureError(createTestApi().listSites(createSignal()));

    expect(error).toBeInstanceOf(ApiHttpError);
    expect(error).toMatchObject({ status: 503, code: null, problem: null, retryable: true });
    expect((error as Error).message).not.toBe(problem.detail);
  });
});
