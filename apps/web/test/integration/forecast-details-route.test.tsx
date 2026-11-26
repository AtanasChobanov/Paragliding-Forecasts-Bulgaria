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
import { ApiNetworkError } from "../../src/services/api/api-errors.js";

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
  it("loads detail without a map and fetches the exact selector values", async () => {
    const { dashboardApi, getForecastDetail } = createDetailApi();
    renderWithQueryClient(
      <MemoryRouter initialEntries={["/forecast?site=sopot&date=2026-07-18"]}>
        <AppRoutes dashboardApi={dashboardApi} />
      </MemoryRouter>,
    );

    expect(
      await screen.findByRole("heading", { level: 1, name: "Sopot · Saturday, 18 Jul" }),
    ).toBeVisible();
    expect(screen.getByRole("main", { name: "Detailed forecast" })).toBeVisible();
    expect(screen.getByRole("link", { name: "All sites" })).toHaveAttribute(
      "href",
      "/?site=sopot&date=2026-07-18",
    );
    expect(screen.queryByTestId("forecast-detail-map")).not.toBeInTheDocument();
    expect(siteSelectorSectionMock).not.toHaveBeenCalled();

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

  it.each([
    { method: "listSites", retry: "Retry locations" },
    { method: "getForecastDays", retry: "Retry forecast dates" },
    { method: "getForecastDetail", retry: "Retry detailed forecast" },
  ] as const)(
    "retries the failed $method request and replaces its error",
    async ({ method, retry }) => {
      const { dashboardApi } = createDetailApi();
      dashboardApi[method].mockRejectedValueOnce(new ApiNetworkError(new Error("fixture network")));
      renderWithQueryClient(
        <MemoryRouter initialEntries={["/forecast?site=sopot&date=2026-07-18"]}>
          <AppRoutes dashboardApi={dashboardApi} />
        </MemoryRouter>,
      );
      await userEvent.click(await screen.findByRole("button", { name: retry }));
      expect(
        await screen.findByRole("heading", { name: "Sopot · Saturday, 18 Jul" }),
      ).toBeVisible();
      expect(dashboardApi[method]).toHaveBeenCalledTimes(2);
      expect(screen.queryByRole("button", { name: retry })).not.toBeInTheDocument();
    },
  );

  it("requests direct dates outside days and preserves the date when changing sites", async () => {
    const { dashboardApi, getForecastDetail } = createDetailApi();
    renderWithQueryClient(
      <MemoryRouter initialEntries={["/forecast?site=sopot&date=2026-06-01"]}>
        <AppRoutes dashboardApi={dashboardApi} />
      </MemoryRouter>,
    );
    expect(await screen.findByRole("heading", { name: "Sopot · Monday, 01 Jun" })).toBeVisible();
    expect(screen.getByLabelText("Forecast date")).toHaveValue("2026-06-01");
    await userEvent.selectOptions(screen.getByLabelText("Location"), "zlatitsa");
    await waitFor(() => {
      expect(getForecastDetail).toHaveBeenLastCalledWith(
        expect.objectContaining({ date: "2026-06-01", siteSlug: "zlatitsa" }),
      );
    });
  });

  it("selects the nearest future date when Today is unpublished, and disables fully missing dates", async () => {
    const { dashboardApi, getForecastDetail } = createDetailApi();
    const days = createForecastDaysResponse();
    days.days = days.days.map((day) =>
      day.forecastDate === days.todayDate
        ? {
            availability: "missing",
            forecastDate: day.forecastDate,
            chance100KmPct: {
              value: null,
              dataStatus: "missing",
              confidence: null,
              missingReason: "Unpublished",
            },
            missingReason: "Unpublished",
          }
        : day,
    );
    dashboardApi.getForecastDays.mockResolvedValue(days);
    renderWithQueryClient(
      <MemoryRouter initialEntries={["/forecast?site=sopot&date=invalid"]}>
        <AppRoutes dashboardApi={dashboardApi} />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(getForecastDetail).toHaveBeenCalledWith(
        expect.objectContaining({ date: "2026-07-19" }),
      );
    });
    expect(screen.getByRole("option", { name: "Saturday, 18 Jul" })).toBeDisabled();
  });

  it("shows an empty window without requesting arbitrary detail dates", async () => {
    const { dashboardApi, getForecastDetail } = createDetailApi();
    const days = createForecastDaysResponse();
    days.days = days.days.map((day) => ({
      availability: "missing",
      forecastDate: day.forecastDate,
      chance100KmPct: {
        value: null,
        dataStatus: "missing",
        confidence: null,
        missingReason: "Unpublished",
      },
      missingReason: "Unpublished",
    }));
    dashboardApi.getForecastDays.mockResolvedValue(days);
    renderWithQueryClient(
      <MemoryRouter initialEntries={["/forecast?site=sopot"]}>
        <AppRoutes dashboardApi={dashboardApi} />
      </MemoryRouter>,
    );
    expect(
      await screen.findByText("No published forecasts are available in this date window."),
    ).toBeVisible();
    expect(getForecastDetail).not.toHaveBeenCalled();
  });

  it("clears previous evidence while loading, resets selectors and reuses cached site/date requests", async () => {
    const { dashboardApi, getForecastDetail } = createDetailApi();
    renderWithQueryClient(
      <MemoryRouter initialEntries={["/forecast?site=sopot&date=2026-07-18"]}>
        <AppRoutes dashboardApi={dashboardApi} />
      </MemoryRouter>,
    );
    await screen.findByRole("heading", { level: 1 });
    await userEvent.selectOptions(screen.getByLabelText("XC input group"), "Humidity");
    await userEvent.click(screen.getByRole("tab", { name: "200+ km" }));
    let complete: ((response: ReturnType<typeof createForecastResponse>) => void) | undefined;
    getForecastDetail.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          complete = resolve;
        }),
    );
    await userEvent.selectOptions(screen.getByLabelText("Forecast date"), "2026-07-19");
    expect(await screen.findByText("The selected detailed forecast is loading.")).toBeVisible();
    expect(screen.queryByLabelText("XC input group")).not.toBeInTheDocument();
    complete?.({ ...createForecastResponse(), forecastDate: "2026-07-19" });
    expect(await screen.findByLabelText("XC input group")).toHaveValue("Surface temperature");
    expect(screen.getByRole("tab", { name: "100+ km" })).toHaveAttribute("aria-selected", "true");
    await userEvent.selectOptions(screen.getByLabelText("Forecast date"), "2026-07-18");
    expect(await screen.findByRole("heading", { name: "Sopot · Saturday, 18 Jul" })).toBeVisible();
    expect(getForecastDetail).toHaveBeenCalledTimes(2);
  });
});
