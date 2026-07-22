import type { SiteSlug } from "@paragliding-forecasts/contracts";
import { describe, expect, it, vi } from "vitest";

import { createDashboardQueryOptions } from "../../src/features/dashboard/dashboard-query-options.js";
import type { DashboardApi } from "../../src/services/api/dashboard-api.js";
import {
  createForecastDaysResponse,
  createForecastSummariesResponse,
  createSitesResponse,
} from "../support/dashboard-fixtures.js";
import { createTestQueryClient } from "../support/render.js";

const createApiSpies = () => {
  const listSites = vi.fn<DashboardApi["listSites"]>().mockResolvedValue(createSitesResponse());
  const getForecastSummaries = vi
    .fn<DashboardApi["getForecastSummaries"]>()
    .mockResolvedValue(createForecastSummariesResponse());
  const getForecastDays = vi
    .fn<DashboardApi["getForecastDays"]>()
    .mockResolvedValue(createForecastDaysResponse());

  return {
    api: { listSites, getForecastSummaries, getForecastDays } satisfies DashboardApi,
    getForecastDays,
    getForecastSummaries,
    listSites,
  };
};

describe("dashboard query options", () => {
  it("uses the stable site key, infinite freshness, and the TanStack cancellation signal", async () => {
    const { api, listSites } = createApiSpies();
    const options = createDashboardQueryOptions(api).sites();
    const queryClient = createTestQueryClient();

    expect(options.queryKey).toEqual(["sites"]);
    expect(options.staleTime).toBe(Infinity);
    await expect(queryClient.fetchQuery(options)).resolves.toEqual(createSitesResponse());
    expect(listSites).toHaveBeenCalledOnce();
    expect(listSites.mock.calls[0]?.[0]).toBeInstanceOf(AbortSignal);
    queryClient.clear();
  });

  it("uses the selected-site day key and forwards the query signal", async () => {
    const { api, getForecastDays } = createApiSpies();
    const options = createDashboardQueryOptions(api).forecastDays("sopot");
    const queryClient = createTestQueryClient();

    expect(options.queryKey).toEqual(["forecastDays", "sopot"]);
    await expect(queryClient.fetchQuery(options)).resolves.toEqual(createForecastDaysResponse());
    const request = getForecastDays.mock.calls[0]?.[0];
    expect(request?.siteSlug).toBe("sopot");
    expect(request?.signal).toBeInstanceOf(AbortSignal);
    queryClient.clear();
  });

  it("copies the canonical summary slugs for both the key and request", async () => {
    const { api, getForecastSummaries } = createApiSpies();
    const callerSlugs: SiteSlug[] = ["zlatitsa", "sopot"];
    const options = createDashboardQueryOptions(api).forecastSummaries("2026-07-18", callerSlugs);
    const queryClient = createTestQueryClient();

    callerSlugs.reverse();
    expect(options.queryKey).toEqual(["forecastSummaries", "2026-07-18", ["zlatitsa", "sopot"]]);
    await expect(queryClient.fetchQuery(options)).resolves.toEqual(
      createForecastSummariesResponse(),
    );
    const request = getForecastSummaries.mock.calls[0]?.[0];
    expect(request?.date).toBe("2026-07-18");
    expect(request?.siteSlugs).toEqual(["zlatitsa", "sopot"]);
    expect(request?.signal).toBeInstanceOf(AbortSignal);
    queryClient.clear();
  });
});
