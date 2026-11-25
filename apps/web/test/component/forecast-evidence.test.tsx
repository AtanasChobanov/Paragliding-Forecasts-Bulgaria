import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { ForecastDriver, ForecastInputRow } from "@paragliding-forecasts/contracts";
import {
  driverEvidencePages,
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
    expect(screen.getByText(/10:00 Sofia – 25 Nov 2026, 11:00 Sofia/u)).toBeVisible();
    view.rerender(<InputEvidence row={{ ...row, value: 3.123456 }} omitDisplayedValue />);
    expect(screen.getByText("3.123456 m/s")).toBeVisible();
  });
  it("keeps a short driver with its calculation and input values together", () => {
    const pages = driverEvidencePages({ ...driver, inputs: [{ inputKey: row.key, field: row }] });
    expect(pages).toHaveLength(1);
    render(<>{pages[0]}</>);
    expect(screen.getByText("Calculation details")).toBeVisible();
    expect(screen.getByText("-0.12 logits")).toBeVisible();
    expect(screen.getByText("Wind speed")).toBeVisible();
    expect(screen.getByText("3 m/s")).toBeVisible();
  });
  it("separates longer evidence by input topic rather than individual metadata fields", () => {
    const inputs = ["Wind", "Wind", "Humidity", "Humidity"].map((group, i) => ({
      inputKey: String(i),
      field: { ...row, key: String(i), group },
    }));
    const pages = driverEvidencePages({ ...driver, inputs });
    expect(pages).toHaveLength(3);
    const view = render(<>{pages[1]}</>);
    expect(screen.getByRole("heading", { name: "Wind", level: 3 })).toBeVisible();
    expect(screen.getAllByText("Wind speed")).toHaveLength(2);
    view.rerender(<>{pages[2]}</>);
    expect(screen.getByRole("heading", { name: "Humidity", level: 3 })).toBeVisible();
  });
});
