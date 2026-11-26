import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { ForecastDriver, ForecastInputRow } from "@paragliding-forecasts/contracts";
import {
  DriverEvidence,
  InputEvidence,
} from "../../src/features/forecast-details/components/ForecastEvidence.js";

const row: ForecastInputRow = {
  key: "wind",
  label: "Wind speed",
  group: "Wind",
  scope: "surface",
  unit: "m/s",
  value: 3,
  dataStatus: "baseline",
  qualityState: "complete",
  statistic: "interval_average",
  provenanceId: 42,
  intervalStartUtc: "2026-11-25T08:00:00Z",
  intervalEndUtc: "2026-11-25T09:00:00Z",
};
const driver: ForecastDriver = {
  kind: "xc_contribution",
  code: "wind",
  message: "Wind lowers the estimate",
  rank: 1,
  xcStage: "p100",
  direction: "lowers",
  contributionLogit: -0.12,
  inputs: [],
};

describe("structured forecast evidence", () => {
  it("omits repeated display values while retaining metadata, true intervals and extra precision", () => {
    const view = render(<InputEvidence row={row} omitDisplayedValue />);
    expect(screen.queryByText("Exact source value")).not.toBeInTheDocument();
    expect(screen.queryByText("Wind speed")).not.toBeInTheDocument();
    expect(screen.getByText("interval average")).toBeVisible();
    expect(screen.getByText("Source record ID")).toBeVisible();
    expect(screen.getByText(/10:00 Sofia – 25 Nov 2026, 11:00 Sofia/u)).toBeVisible();
    view.rerender(<InputEvidence row={{ ...row, value: 3.123456 }} omitDisplayedValue />);
    expect(screen.getByText("3.123456 m/s")).toBeVisible();
  });
  it("rounds hourly values and condenses intervals while retaining quality and source metadata", () => {
    render(<InputEvidence row={{ ...row, value: 57.62231287546873, unit: "W/m2" }} presentation />);
    expect(screen.getByText("57.62 W/m2")).toBeVisible();
    expect(screen.getByText("Quality")).toBeVisible();
    expect(screen.getByText("Source record ID")).toBeVisible();
    const interval = screen.getByText(/Sofia$/u);
    expect(interval).toHaveTextContent("10:00");
    expect(interval).toHaveTextContent("11:00");
    expect(interval.textContent.match(/25 Nov 2026/gu)).toHaveLength(1);
  });
  it("keeps a short driver with its calculation and input values together", () => {
    render(<DriverEvidence driver={{ ...driver, inputs: [{ inputKey: row.key, field: row }] }} />);
    expect(screen.getByText("Calculation details")).toBeVisible();
    expect(screen.getByText("-0.12 logits")).toBeVisible();
    expect(screen.getByText("Wind speed")).toBeVisible();
    expect(screen.getByText("3 m/s")).toBeVisible();
    for (const label of [
      "Statistic",
      "Quality",
      "Source record ID",
      "Interval",
      "Exact source value",
    ]) {
      expect(screen.queryByText(label)).not.toBeInTheDocument();
    }
  });
  it("separates longer evidence by input topic rather than individual metadata fields", () => {
    const inputs = [
      "Wind",
      "Wind",
      "Wind",
      "Humidity",
      "Humidity",
      "Humidity",
      "Thermals",
      "Thermals",
      "Thermals",
    ].map((group, i) => ({
      inputKey: String(i),
      field: { ...row, key: String(i), group },
    }));
    render(<DriverEvidence driver={{ ...driver, inputs }} />);
    expect(screen.getByRole("heading", { name: "Wind", level: 3 })).toBeVisible();
    expect(screen.getAllByText("Wind speed")).toHaveLength(9);
    expect(screen.getByRole("heading", { name: "Humidity", level: 3 })).toBeVisible();
  });
});
