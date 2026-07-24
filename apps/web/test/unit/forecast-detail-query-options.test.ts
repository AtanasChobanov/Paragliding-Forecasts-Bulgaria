import { describe, expect, it, vi } from "vitest";

import { createForecastDetailQueryOptions } from "../../src/features/forecast-details/forecast-detail-query-options.js";
import type { DashboardApi } from "../../src/services/api/dashboard-api.js";
import { createForecastResponse } from "../support/dashboard-fixtures.js";
import { createTestQueryClient } from "../support/render.js";

describe("forecast detail query options", () => {
  it("uses a site/date cache key and forwards the cancellation signal", async () => {
    const getForecastDetail = vi
      .fn<DashboardApi["getForecastDetail"]>()
      .mockResolvedValue(createForecastResponse());
    const api = {
      getForecastDetail,
      getForecastDays: vi.fn(),
      getForecastSummaries: vi.fn(),
      listSites: vi.fn(),
    } satisfies DashboardApi;
    const queryClient = createTestQueryClient();
    const options = createForecastDetailQueryOptions(api, "sopot", "2026-07-18");

    expect(options.queryKey).toEqual(["forecastDetail", "sopot", "2026-07-18"]);
    await expect(queryClient.fetchQuery(options)).resolves.toEqual(createForecastResponse());
    const request = getForecastDetail.mock.calls[0]?.[0];
    expect(request).toMatchObject({ date: "2026-07-18", siteSlug: "sopot" });
    expect(request?.signal).toBeInstanceOf(AbortSignal);
    queryClient.clear();
  });

  it("rejects a response correlated to a different site or date", async () => {
    const getForecastDetail = vi
      .fn<DashboardApi["getForecastDetail"]>()
      .mockResolvedValue({ ...createForecastResponse(), siteSlug: "zlatitsa" });
    const api = {
      getForecastDetail,
      getForecastDays: vi.fn(),
      getForecastSummaries: vi.fn(),
      listSites: vi.fn(),
    } satisfies DashboardApi;
    const queryClient = createTestQueryClient();

    await expect(
      queryClient.fetchQuery(createForecastDetailQueryOptions(api, "sopot", "2026-07-18")),
    ).rejects.toMatchObject({ kind: "api-compatibility", resource: "forecast-detail" });
    queryClient.clear();
  });
});
