import type { DashboardApi } from "../../src/services/api/dashboard-api.js";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

const siteSelectorSectionMock = vi.hoisted(() => vi.fn());

vi.mock("../../src/features/dashboard/components/SiteSelectorSection.js", () => ({
  SiteSelectorSection: (props: unknown) => {
    siteSelectorSectionMock(props);
    return <div data-testid="forecast-detail-map" />;
  },
}));

import { AppRoutes } from "../../src/app/app-routes.js";
import {
  createForecastDaysResponse,
  createForecastResponse,
  createSitesResponse,
} from "../support/dashboard-fixtures.js";
import { renderWithQueryClient } from "../support/render.js";

const createDetailApi = () => {
  const sites = createSitesResponse().sites;
  const listSites = vi.fn<DashboardApi["listSites"]>().mockResolvedValue({ sites });
  const getForecastSummaries = vi.fn<DashboardApi["getForecastSummaries"]>();
  const getForecastDays = vi
    .fn<DashboardApi["getForecastDays"]>()
    .mockImplementation(({ siteSlug }) => {
      const site = sites.find((candidate) => candidate.slug === siteSlug);
      const response = createForecastDaysResponse();

      return Promise.resolve({
        ...response,
        siteId: site?.id ?? response.siteId,
        siteSlug,
      });
    });
  const getForecastDetail = vi
    .fn<DashboardApi["getForecastDetail"]>()
    .mockImplementation(({ date, siteSlug }) => {
      const site = sites.find((candidate) => candidate.slug === siteSlug);
      const response = createForecastResponse();

      return Promise.resolve({
        ...response,
        forecastDate: date,
        siteId: site?.id ?? response.siteId,
        siteSlug,
      });
    });

  return {
    dashboardApi: {
      getForecastDetail,
      getForecastDays,
      getForecastSummaries,
      listSites,
    } satisfies DashboardApi,
    getForecastDetail,
  };
};

describe("ForecastDetailsRoute", () => {
  it("loads the detail view, keeps all map sites available, and auto-fetches after selector changes", async () => {
    const { dashboardApi, getForecastDetail } = createDetailApi();
    renderWithQueryClient(
      <MemoryRouter initialEntries={["/forecast?site=sopot&date=2026-07-18"]}>
        <AppRoutes dashboardApi={dashboardApi} />
      </MemoryRouter>,
    );

    expect(await screen.findByRole("heading", { name: "Sopot · Saturday, 18 Jul" })).toBeVisible();
    expect(screen.getByRole("link", { name: "All sites" })).toHaveAttribute(
      "href",
      "/?site=sopot&date=2026-07-18",
    );
    expect(screen.getByTestId("forecast-detail-map")).toBeVisible();
    expect(siteSelectorSectionMock).toHaveBeenLastCalledWith(
      expect.objectContaining({ showCompass: true, viewportMode: "selected-site" }),
    );

    await userEvent.selectOptions(screen.getByLabelText("Location"), "zlatitsa");
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Zlatitsa · Saturday, 18 Jul" })).toBeVisible();
    });
    await userEvent.selectOptions(screen.getByLabelText("Forecast date"), "2026-07-19");
    await waitFor(() => {
      expect(getForecastDetail).toHaveBeenCalledWith(
        expect.objectContaining({ date: "2026-07-19", siteSlug: "zlatitsa" }),
      );
    });
  });
});
