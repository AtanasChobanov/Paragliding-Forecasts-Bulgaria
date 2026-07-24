import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  ForecastDetailSummary,
  ForecastInputsPanel,
  PreviousRunComparison,
  TopDriversPanel,
} from "../../src/features/forecast-details/components/ForecastDetailContent.js";
import { createForecastResponse } from "../support/dashboard-fixtures.js";

describe("forecast detail content", () => {
  it("renders all detailed outputs, status context, inputs, drivers, and five comparison placeholders", () => {
    const forecast = createForecastResponse();
    render(
      <>
        <ForecastDetailSummary forecast={forecast} siteName="Sopot" />
        <ForecastInputsPanel forecastInputs={forecast.forecastInputs} />
        <TopDriversPanel forecast={forecast} />
        <PreviousRunComparison />
      </>,
    );

    expect(screen.getByRole("heading", { name: "Sopot · Saturday, 18 Jul" })).toBeVisible();
    expect(screen.getByText("Model confidence")).toBeVisible();
    expect(screen.getAllByText("Conf.")).toHaveLength(5);
    expect(screen.getAllByText("Mock data").length).toBeGreaterThanOrEqual(3);
    expect(screen.getByRole("progressbar", { name: /100 kilometres/i })).toHaveAttribute(
      "aria-valuenow",
      "65",
    );
    expect(screen.getAllByText("Cloudbase").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("200+ km chance").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("300+ km chance").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Overdevelopment").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Surface temperature")).toBeVisible();
    expect(screen.getByText("Wind by altitude")).toBeVisible();
    expect(screen.getByText("Synthetic thermal strength")).toBeVisible();
    const comparison = screen.getByRole("heading", {
      name: "Compared with previous run",
    }).parentElement;
    if (comparison === null) {
      throw new Error("Expected the previous-run comparison container.");
    }
    expect(within(comparison).getAllByText("Unchanged")).toHaveLength(5);
  });

  it("preserves missing outputs and inputs without rendering a zero", () => {
    const forecast = createForecastResponse();
    const missingForecast = {
      ...forecast,
      outputs: {
        ...forecast.outputs,
        chance200KmPct: {
          value: null,
          dataStatus: "missing" as const,
          confidence: null,
          missingReason: "No 200 kilometre estimate is available.",
        },
      },
      forecastInputs: {
        ...forecast.forecastInputs,
        capeJPerKg: {
          value: null,
          dataStatus: "missing" as const,
          missingReason: "No CAPE input is available.",
        },
      },
    };

    render(
      <>
        <ForecastDetailSummary forecast={missingForecast} siteName="Sopot" />
        <ForecastInputsPanel forecastInputs={missingForecast.forecastInputs} />
      </>,
    );

    expect(screen.getByText("No 200 kilometre estimate is available.")).toBeVisible();
    expect(screen.getByText("No CAPE input is available.")).toBeVisible();
    expect(screen.getAllByText("Unavailable").length).toBeGreaterThanOrEqual(2);
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });
});
