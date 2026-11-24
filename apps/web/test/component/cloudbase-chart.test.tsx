import { useState } from "react";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ForecastResponse } from "@paragliding-forecasts/contracts";
import { CloudbaseChart } from "../../src/features/forecast-details/components/CloudbaseChart.js";
import {
  cloudbaseScale,
  cloudbaseSegments,
} from "../../src/features/forecast-details/cloudbase-chart.js";
import { defaultCloudbaseHour } from "../../src/features/forecast-details/forecast-detail-presentation.js";
import { createForecastResponse } from "../support/dashboard-fixtures.js";
const Wrapper = ({ forecast }: { readonly forecast: ForecastResponse }) => {
  const [at, setAt] = useState(defaultCloudbaseHour(forecast));
  return <CloudbaseChart forecast={forecast} selectedHour={at} onSelectHour={setAt} />;
};

describe("hourly cloudbase chart", () => {
  beforeEach(() => {
    // JSDOM has no layout; exercise the real Recharts render at a known plot size.
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (
      this: HTMLElement,
    ) {
      return this.classList.contains("recharts-responsive-container")
        ? new DOMRect(0, 0, 1000, 180)
        : new DOMRect();
    });
  });
  it("breaks lines and gradients at regime changes and missing hours", async () => {
    const f = createForecastResponse();
    f.cloudbaseHours = f.cloudbaseHours.map((h, i) => ({
      ...h,
      regime: i === 2 ? "blue" : i === 5 ? "missing" : i >= 6 ? "indeterminate" : "cumulus",
      heightMslM: [2, 5].includes(i) ? null : i >= 6 ? 3000 : 2000,
      heightModelAglM: [2, 5].includes(i) ? null : 1000,
      heightSiteAglM: [2, 5].includes(i) ? null : -100,
      confidenceLevel: i === 5 ? null : "low",
    }));
    expect(cloudbaseSegments(f.cloudbaseHours).map((s) => s.indices)).toEqual([
      [0, 1],
      [3, 4],
      [6, 7, 8, 9, 10],
    ]);
    expect(cloudbaseScale(f.cloudbaseHours)).toEqual({ min: 0, max: 3000 });
    const { container } = render(<Wrapper forecast={f} />);
    await waitFor(() => {
      expect(container.querySelectorAll(".recharts-line-curve")).toHaveLength(3);
    });
    for (const path of container.querySelectorAll(".recharts-line-curve")) {
      const d = path.getAttribute("d") ?? "";
      expect(d.match(/M/gu)).toHaveLength(1);
      expect(d).not.toMatch(/[CQ]/u);
    }
    expect(container.querySelectorAll("[data-gradient-segment]")).toHaveLength(3);
    expect(container.querySelectorAll('[data-numeric-marker="conditional"]')).toHaveLength(5);
    expect(screen.getByLabelText("Cloudbase legend")).toHaveTextContent("Conditional LCL");
  });
  it.each(["blue", "missing", "indeterminate"] as const)(
    "keeps all eleven interactive %s hours without numeric zero heights",
    async (regime) => {
      const f = createForecastResponse();
      f.cloudbaseHours = f.cloudbaseHours.map((h) => ({
        ...h,
        regime,
        heightMslM: null,
        heightModelAglM: null,
        heightSiteAglM: null,
        confidenceLevel: regime === "missing" ? null : "low",
      }));
      const { container } = render(<Wrapper forecast={f} />);
      expect(await screen.findByText("No numeric cloudbase heights published")).toBeVisible();
      expect(container.querySelectorAll(".recharts-line-curve")).toHaveLength(0);
      expect(container.querySelectorAll("[data-numeric-marker]")).toHaveLength(0);
      expect(
        screen.getByRole("group", { name: "Select cloudbase hour" }).querySelectorAll("button"),
      ).toHaveLength(11);
      const last = screen.getAllByRole("button").at(-1);
      if (!last) throw new Error("Missing hour controls");
      await userEvent.click(last);
      expect(last).toHaveAttribute("aria-pressed", "true");
      expect(screen.getByRole("region", { name: "Cloudbase hour information" })).toHaveTextContent(
        "No numeric height.",
      );
    },
  );
  it("marks a single numeric hour without a gradient bridge and retains signed site AGL", async () => {
    const f = createForecastResponse();
    f.cloudbaseHours = f.cloudbaseHours.map((h, i) => ({
      ...h,
      regime: i === 3 ? "cumulus" : "blue",
      heightMslM: i === 3 ? 2400 : null,
      heightModelAglM: i === 3 ? 1000 : null,
      heightSiteAglM: i === 3 ? -200 : null,
    }));
    const { container } = render(<Wrapper forecast={f} />);
    await waitFor(() => {
      expect(container.querySelectorAll("[data-numeric-marker]")).toHaveLength(1);
    });
    expect(container.querySelectorAll("[data-gradient-segment]")).toHaveLength(0);
    await userEvent.click(
      screen.getByRole("button", { name: "13:00 Sofia · Estimated cloudbase" }),
    );
    expect(screen.getByRole("region", { name: "Cloudbase hour information" })).toHaveTextContent(
      "-200 m site AGL",
    );
    expect(screen.getByRole("region", { name: "Cloudbase hour information" })).toHaveTextContent(
      "Daily maximum",
    );
    const popup = screen.getByRole("region", { name: "Cloudbase hour information" });
    expect(within(popup).getByText("2,400").tagName).toBe("STRONG");
    expect(within(popup).getByRole("group", { name: /Hourly confidence/u })).toBeVisible();
    expect(within(popup).queryByText(/Estimated cloudbase/u)).not.toBeInTheDocument();
    expect(within(popup).queryByRole("button", { name: /Close/u })).not.toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    expect(
      screen.queryByRole("region", { name: "Cloudbase hour information" }),
    ).not.toBeInTheDocument();
  });
  it("supports keyboard edges and conditional-only data with a lower negative scale bound", async () => {
    const f = createForecastResponse();
    f.outputs.cloudbase = {
      kind: "conditional_lcl",
      valueMslM: 2400,
      dataStatus: "baseline",
      confidence: { level: "low" },
    };
    f.cloudbaseHours = f.cloudbaseHours.map((h, i) => ({
      ...h,
      regime: "indeterminate",
      heightMslM: i === 0 ? -123 : h.heightMslM,
    }));
    expect(cloudbaseScale(f.cloudbaseHours)).toEqual({ min: -500, max: 2500 });
    render(<Wrapper forecast={f} />);
    const selected = screen.getByRole("button", { name: "13:00 Sofia · Conditional LCL" });
    await userEvent.click(selected);
    await userEvent.keyboard("{ArrowRight}{End}");
    expect(screen.getByRole("button", { name: "20:00 Sofia · Conditional LCL" })).toHaveFocus();
    await userEvent.keyboard("{Home}");
    expect(screen.getByRole("button", { name: "10:00 Sofia · Conditional LCL" })).toHaveFocus();
  });
});
