import type { ForecastOutputs, ForecastSummary } from "@paragliding-forecasts/contracts";
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";

import { ForecastOverview } from "../../src/features/dashboard/components/ForecastOverview.js";
import { createForecastSummariesResponse, missingMetric } from "../support/dashboard-fixtures.js";

type AvailableSummary = Extract<ForecastSummary, { readonly availability: "available" }>;
type MissingSummary = Extract<ForecastSummary, { readonly availability: "missing" }>;

const renderWithRouter = (content: ReactNode) => render(<MemoryRouter>{content}</MemoryRouter>);

const getAvailableSummary = (): AvailableSummary => {
  const summary = createForecastSummariesResponse().summaries.find(
    (candidate): candidate is AvailableSummary => candidate.availability === "available",
  );

  if (summary === undefined) {
    throw new Error("Expected an available summary fixture.");
  }

  return summary;
};

const getMissingSummary = (): MissingSummary => {
  const summary = createForecastSummariesResponse().summaries.find(
    (candidate): candidate is MissingSummary => candidate.availability === "missing",
  );

  if (summary === undefined) {
    throw new Error("Expected a missing summary fixture.");
  }

  return summary;
};

describe("ForecastOverview", () => {
  it("renders the selected site, five formatted metrics, mock provenance, and confidence", () => {
    renderWithRouter(
      <ForecastOverview
        forecastDate="2026-07-18"
        siteName="Sopot"
        summary={getAvailableSummary()}
      />,
    );

    expect(
      screen.getByRole("heading", { level: 1, name: "Sopot · Saturday, 18 Jul" }),
    ).toBeVisible();
    expect(screen.getByText("Mock data")).toBeVisible();
    const metrics = screen.getByRole("list", { name: "Forecast metrics" });
    expect(within(metrics).getAllByRole("listitem")).toHaveLength(5);
    expect(metrics.querySelectorAll("svg")).toHaveLength(5);
    expect(within(metrics).getByText("2,400")).toBeVisible();
    expect(within(metrics).getByText("m MSL")).toBeVisible();
    expect(within(metrics).getByText("100+ km chance")).toBeVisible();
    expect(within(metrics).getByText("200+ km chance")).toBeVisible();
    expect(within(metrics).getByText("300+ km chance")).toBeVisible();
    expect(within(metrics).getByText("Medium")).toBeVisible();
    expect(screen.getByText("mock-v2")).toBeVisible();
    expect(screen.getByText("source t-003-t-005-mock-provider")).toBeVisible();
    expect(screen.getByText(/generated 23:00 EEST/)).toBeVisible();
    expect(screen.getByText("Synthetic demonstration value.")).toBeVisible();
    expect(screen.getByRole("link", { name: "View detailed forecast" })).toHaveAttribute(
      "href",
      "/forecast?site=sopot&date=2026-07-18",
    );
  });

  it("keeps available values while rendering a partial metric as unavailable", () => {
    const available = getAvailableSummary();
    const outputs: ForecastOutputs = {
      ...available.outputs,
      chance200KmPct: missingMetric,
    };

    renderWithRouter(
      <ForecastOverview
        forecastDate="2026-07-18"
        siteName="Sopot"
        summary={{ ...available, outputs }}
      />,
    );

    expect(screen.getByText("Mixed data")).toBeVisible();
    const metrics = screen.getByRole("list", { name: "Forecast metrics" });
    expect(within(metrics).getByText("2,400")).toBeVisible();
    expect(within(metrics).getAllByText("Unavailable")).toHaveLength(2);
    expect(
      within(metrics).getByText("No forecast run is available for this site and date."),
    ).toBeVisible();
    expect(within(metrics).queryByText("0")).not.toBeInTheDocument();
  });

  it("renders all metrics and confidence as unavailable without inventing zeros", () => {
    const available = getAvailableSummary();
    const outputs: ForecastOutputs = {
      cloudbaseMslM: missingMetric,
      chance100KmPct: missingMetric,
      chance200KmPct: missingMetric,
      chance300KmPct: missingMetric,
      overdevelopmentRisk: missingMetric,
    };

    renderWithRouter(
      <ForecastOverview
        forecastDate="2026-07-18"
        siteName="Sopot"
        summary={{ ...available, outputs }}
      />,
    );

    expect(screen.getByText("All forecast metrics are unavailable.")).toBeVisible();
    expect(screen.getByText("Confidence unavailable")).toBeVisible();
    expect(screen.getAllByText("Unavailable").length).toBeGreaterThanOrEqual(5);
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });

  it("renders a summary-level missing reason without outputs or metadata", () => {
    renderWithRouter(
      <ForecastOverview
        forecastDate="2026-07-18"
        siteName="Zlatitsa"
        summary={getMissingSummary()}
      />,
    );

    expect(screen.getByText("Forecast unavailable")).toBeVisible();
    expect(screen.getByText("No forecast exists for Zlatitsa on 2026-07-18.")).toBeVisible();
    expect(screen.queryByRole("list", { name: "Forecast metrics" })).not.toBeInTheDocument();
    expect(screen.queryByText("mock-v2")).not.toBeInTheDocument();
  });

  it("treats an omitted summary as partial service content", () => {
    renderWithRouter(
      <ForecastOverview forecastDate="2026-07-18" siteName="Sopot" summary={undefined} />,
    );

    expect(screen.getByText("No summary was returned for the selected location.")).toBeVisible();
    expect(
      screen.getByText(
        "The service response omitted the selected location. No values were inferred.",
      ),
    ).toBeVisible();
  });
});
