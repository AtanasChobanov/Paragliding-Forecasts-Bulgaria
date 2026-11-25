import { render, screen, within, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import {
  ForecastDetailSummary,
  ForecastInputsPanel,
  TopDriversPanel,
} from "../../src/features/forecast-details/components/ForecastDetailContent.js";
import { MeasuredPages } from "../../src/features/forecast-details/components/MeasuredPages.js";
import { createForecastResponse, missingMetric } from "../support/dashboard-fixtures.js";

const inputs = () => {
  const forecast = createForecastResponse();
  return render(
    <ForecastInputsPanel
      forecast={forecast}
      selectedHour={forecast.forecastInputs.windowStartUtc}
      onSelectHour={() => undefined}
    />,
  );
};

describe("forecast detail content", () => {
  it("stacks three probability rows above cloudbase and OD with metric-specific badges", () => {
    const forecast = createForecastResponse();
    forecast.outputs.chance100KmPct = { ...missingMetric };
    forecast.outputs.chance200KmPct = {
      value: 0.001,
      dataStatus: "baseline",
      confidence: { level: "high" },
    };
    render(<ForecastDetailSummary forecast={forecast} siteName="Sopot" />);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Sopot · Saturday, 18 Jul");
    const cards = screen.getAllByRole("article");
    expect(cards.map((card) => card.getAttribute("aria-label"))).toEqual([
      "100+ km",
      "200+ km",
      "300+ km",
      "Cloudbase",
      "OD risk",
    ]);
    for (const card of cards) {
      const header = card.querySelector("svg")?.parentElement?.parentElement;
      expect(header?.firstElementChild?.querySelector("svg")).not.toBeNull();
      expect(header?.lastElementChild).toHaveTextContent(/Mock|Baseline|Unavailable/u);
    }
    const third = cards[1];
    if (!third) throw new Error("Missing card");
    expect(within(third).getByText("<0.01%")).toBeVisible();
    expect(screen.getAllByRole("progressbar")).toHaveLength(2);
    expect(
      screen.getByRole("group", { name: "P100 model confidence. Confidence unavailable" }),
    ).toBeVisible();
  });
  it("keeps signed site/model AGL without general guidance in cloudbase information", async () => {
    const forecast = createForecastResponse();
    const maximum = forecast.cloudbaseHours[3];
    if (!maximum) throw new Error("Missing fixture maximum");
    maximum.heightSiteAglM = -125;
    render(<ForecastDetailSummary forecast={forecast} siteName="Sopot" />);
    const cloud = screen.getByRole("article", { name: "Cloudbase" });
    expect(within(cloud).queryByText(/AGL/u)).not.toBeInTheDocument();
    await userEvent.click(within(cloud).getByRole("button", { name: "Cloudbase information" }));
    const popup = screen.getByRole("region", { name: "Cloudbase evidence" });
    expect(within(popup).getByText("-125 m")).toBeVisible();
    expect(popup).toHaveTextContent("Model AGL");
    expect(popup).not.toHaveTextContent("Height references");
    expect(popup).not.toHaveTextContent("Cloud formation");
    await userEvent.keyboard("{Escape}");
    expect(within(cloud).getByText("Confidence")).toBeVisible();
    expect(
      within(screen.getByRole("article", { name: "OD risk" })).getByText("Confidence"),
    ).toBeVisible();
    expect(screen.queryByText(/daily maximum ·/u)).not.toBeInTheDocument();
  });
  it("shows summary metadata and readable metric evidence without pagination or repeated status", async () => {
    const forecast = createForecastResponse();
    forecast.outputs.cloudbase.limitationsNote =
      "uncalibrated_baseline; model_column_not_terrain_corrected";
    render(<ForecastDetailSummary forecast={forecast} siteName="Sopot" />);
    for (const label of ["100+ km", "200+ km", "300+ km", "Cloudbase", "OD risk"]) {
      await userEvent.click(screen.getByRole("button", { name: `${label} information` }));
      const popup = screen.getByRole("region", { name: `${label} evidence` });
      expect(within(popup).queryByRole("navigation")).not.toBeInTheDocument();
      expect(popup).not.toHaveTextContent(/Mock ·|Baseline ·|low confidence/u);
      if (label === "Cloudbase") {
        expect(popup).toHaveTextContent(
          "The atmospheric profile is not corrected for local terrain.",
        );
        expect(popup).not.toHaveTextContent("uncalibrated_baseline");
      }
      await userEvent.keyboard("{Escape}");
    }
    await userEvent.click(screen.getByRole("button", { name: "Forecast information" }));
    const popup = screen.getByRole("region", { name: "Forecast information for Sopot" });
    expect(popup).toHaveTextContent("Source");
    expect(popup).not.toHaveTextContent("Height references");
    expect(popup).not.toHaveTextContent("Cloud formation");
    expect(popup).not.toHaveTextContent("Synthetic demonstration value.");
    expect(within(popup).queryByRole("navigation")).not.toBeInTheDocument();
  });
  it("paginates all XC groups and exposes canonical input values through information", async () => {
    inputs();
    expect(screen.getByLabelText("Input category")).toHaveValue("xc");
    expect(screen.getByLabelText("XC input group")).toHaveValue("Surface temperature");
    expect(screen.getByText("1 of 4")).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByText("2 of 4")).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: /Input information:/u }));
    const popup = screen.getByRole("region", { name: /input$/u });
    expect(popup).toBeVisible();
    expect(within(popup).queryByRole("navigation")).not.toBeInTheDocument();
    expect(popup).toHaveTextContent("Exact source value");
    expect(popup).toHaveTextContent("Statistic");
    expect(popup).not.toHaveTextContent("Air temperature 2 m mean");
    await userEvent.keyboard("{Escape}");
    await userEvent.selectOptions(screen.getByLabelText("XC input group"), "Humidity");
    expect(screen.getByText("1 of 3")).toBeVisible();
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();
    await userEvent.selectOptions(screen.getByLabelText("Input category"), "od");
    expect(screen.getByLabelText("Input hour")).toHaveValue("2026-07-18T07:00:00Z");
  });
  it("clamps pagination to measured row capacity after resize", () => {
    let available = 90;
    const rect = vi
      .spyOn(HTMLElement.prototype, "getBoundingClientRect")
      .mockImplementation(function (this: HTMLElement) {
        return new DOMRect(0, 0, 200, this.hasAttribute("data-page-row") ? 30 : available);
      });
    render(
      <MeasuredPages
        items={[1, 2, 3, 4, 5, 6, 7]}
        label="Measured"
        maxRows={6}
        render={(n) => <span>{n}</span>}
      />,
    );
    expect(screen.getByText("1 of 3")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    available = 180;
    fireEvent(window, new Event("resize"));
    expect(screen.getByText("2 of 2")).toBeVisible();
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
    available = 240;
    fireEvent(window, new Event("resize"));
    expect(screen.getByText("2 of 2")).toBeVisible();
    rect.mockRestore();
  });
  it("shows one of one and disables both arrows when all four rows fit", () => {
    const rect = vi
      .spyOn(HTMLElement.prototype, "getBoundingClientRect")
      .mockImplementation(function (this: HTMLElement) {
        return new DOMRect(0, 0, 200, this.hasAttribute("data-page-row") ? 30 : 120);
      });
    render(
      <MeasuredPages
        items={[1, 2, 3, 4]}
        label="Measured"
        maxRows={6}
        render={(n) => <span>{n}</span>}
      />,
    );
    const pagination = screen.getByRole("navigation", { name: "Measured pagination" });
    expect(pagination).toHaveTextContent(/^1 of 1$/u);
    expect(within(pagination).getByRole("button", { name: "Previous" })).toBeDisabled();
    expect(within(pagination).getByRole("button", { name: "Next" })).toBeDisabled();
    rect.mockRestore();
  });
  it("uses five explanation groups, Q200 semantics, actual support and risk-specific icons", async () => {
    const f = createForecastResponse();
    const q = f.explanations[1],
      p = f.explanations[2],
      od = f.explanations[3],
      cloud = f.explanations[4];
    if (!q || !p || !od || !cloud) throw new Error("Fixture groups missing");
    q.drivers = [
      {
        kind: "xc_contribution",
        code: "humidity",
        message: "Raises Q200",
        rank: 1,
        xcStage: "q200",
        direction: "raises",
        contributionLogit: 0.3,
        inputs: [],
      },
    ];
    p.drivers = [
      {
        kind: "pooled_conversion",
        code: "pooled",
        message: "Pooled conversion",
        rank: 1,
        supportSuccesses: 3,
        supportTotal: 42,
        inputs: [],
      },
    ];
    od.drivers = [
      { kind: "od_override", code: "rain", message: "Critical rain override", rank: 1, inputs: [] },
    ];
    cloud.drivers = [
      {
        kind: "cloudbase_reason",
        code: "future_code",
        message: "Unknown cloud reason",
        rank: 1,
        inputs: [],
      },
    ];
    render(<TopDriversPanel forecast={f} />);
    expect(screen.getAllByRole("tab")).toHaveLength(5);
    await userEvent.click(screen.getByRole("tab", { name: "200+ km" }));
    expect(screen.getByText(/Conditional step P\(200\+ \| 100\+\)/u)).toBeVisible();
    expect(screen.getByLabelText("Raises the model estimate")).toHaveTextContent("+");
    await userEvent.click(screen.getByRole("tab", { name: "300+ km" }));
    expect(screen.getByText("Pooled conversion · 3/42")).toBeVisible();
    await userEvent.click(screen.getByRole("tab", { name: "OD risk" }));
    expect(screen.getByLabelText("Critical risk rule")).toHaveTextContent("△");
    await userEvent.click(screen.getByRole("tab", { name: "Cloudbase" }));
    expect(screen.getByLabelText("Cloudbase explanation")).toHaveTextContent("ⓘ");
  });
});
