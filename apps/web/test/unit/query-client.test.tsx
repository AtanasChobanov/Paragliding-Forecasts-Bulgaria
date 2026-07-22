import { useQueryClient } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AppProviders } from "../../src/app/AppProviders.js";
import {
  FORECAST_QUERY_STALE_TIME_MS,
  createDashboardQueryClient,
  shouldRetryDashboardQuery,
} from "../../src/app/query-client.js";
import {
  ApiHttpError,
  ApiNetworkError,
  ApiResponseError,
} from "../../src/services/api/api-errors.js";
const createHttpError = (status: number) =>
  new ApiHttpError({ status, problem: null, requestId: null, cause: undefined });

describe("dashboard query client", () => {
  it("provides the explicitly created client to the React tree", () => {
    const queryClient = createDashboardQueryClient();

    const QueryClientProbe = () => {
      const providedClient = useQueryClient();
      return <span>{providedClient === queryClient ? "provided client" : "wrong client"}</span>;
    };

    render(
      <AppProviders queryClient={queryClient}>
        <QueryClientProbe />
      </AppProviders>,
    );

    expect(screen.getByText("provided client")).toBeInTheDocument();
    queryClient.clear();
  });

  it("uses the documented freshness and focus defaults", () => {
    const queryClient = createDashboardQueryClient();
    const defaults = queryClient.getDefaultOptions().queries;

    expect(defaults?.staleTime).toBe(FORECAST_QUERY_STALE_TIME_MS);
    expect(defaults?.refetchOnWindowFocus).toBe(false);
    expect(defaults?.placeholderData).toBeUndefined();
    queryClient.clear();
  });

  it("retries only the first network or 5xx failure", () => {
    const networkError = new ApiNetworkError(new TypeError("network failure"));
    const serverError = createHttpError(503);

    expect(shouldRetryDashboardQuery(0, networkError)).toBe(true);
    expect(shouldRetryDashboardQuery(1, networkError)).toBe(false);
    expect(shouldRetryDashboardQuery(0, serverError)).toBe(true);
    expect(shouldRetryDashboardQuery(1, serverError)).toBe(false);
  });

  it.each([
    ["a 4xx response", createHttpError(400)],
    [
      "an invalid successful response",
      new ApiResponseError({ status: 200, reason: "schema-validation", cause: undefined }),
    ],
    ["an abort", new DOMException("The request was aborted.", "AbortError")],
    ["an unknown error", new Error("unexpected")],
  ])("does not retry %s", (_description, error) => {
    expect(shouldRetryDashboardQuery(0, error)).toBe(false);
  });

  it.each([
    ["network", new ApiNetworkError(new TypeError("network failure")), 2],
    ["5xx", createHttpError(500), 2],
    ["4xx", createHttpError(404), 1],
    [
      "invalid response",
      new ApiResponseError({ status: 200, reason: "malformed-json", cause: undefined }),
      1,
    ],
  ])("makes the expected number of attempts for a %s error", async (_description, error, count) => {
    const queryClient = createDashboardQueryClient();
    const queryFn = vi.fn<() => Promise<never>>().mockRejectedValue(error);

    await expect(
      queryClient.fetchQuery({
        queryKey: ["retry-test", _description],
        queryFn,
        retryDelay: 0,
      }),
    ).rejects.toBe(error);
    expect(queryFn).toHaveBeenCalledTimes(count);
    queryClient.clear();
  });
});
