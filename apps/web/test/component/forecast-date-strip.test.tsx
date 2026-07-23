import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ForecastDateStrip } from "../../src/features/dashboard/components/ForecastDateStrip.js";
import { createForecastDaysResponse } from "../support/dashboard-fixtures.js";

describe("ForecastDateStrip", () => {
  it("renders exactly the five API slots in order with separate today and selected states", () => {
    const response = createForecastDaysResponse();
    render(
      <ForecastDateStrip
        days={response.days}
        onSelectDate={vi.fn()}
        selectedDate="2026-07-17"
        todayDate={response.todayDate}
      />,
    );

    expect(screen.getByText("2026")).toBeVisible();
    const list = screen.getByRole("list", { name: "Five-day forecast dates" });
    const items = within(list).getAllByRole("listitem");
    expect(items).toHaveLength(5);
    expect(
      items.map((item) => within(item).getByRole("button").getAttribute("aria-label")),
    ).toEqual(["2026-07-16", "2026-07-17", "2026-07-18", "2026-07-19", "2026-07-20"]);
    expect(screen.getByRole("button", { name: "2026-07-17" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByRole("button", { name: "2026-07-17" })).not.toHaveAttribute("aria-current");
    expect(screen.getByRole("button", { name: "2026-07-18" })).toHaveAttribute(
      "aria-current",
      "date",
    );
    expect(screen.getByRole("button", { name: "2026-07-18" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
    expect(screen.getByText("Today")).toBeVisible();
    expect(screen.getAllByText("Mock data")).toHaveLength(4);
    expect(within(list).getAllByRole("button")).toHaveLength(5);
    expect(screen.queryByRole("button", { name: /previous|next/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("pushes the supplied calendar date through one callback", async () => {
    const response = createForecastDaysResponse();
    const onSelectDate = vi.fn();
    render(
      <ForecastDateStrip
        days={response.days}
        onSelectDate={onSelectDate}
        selectedDate="2026-07-18"
        todayDate={response.todayDate}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: "2026-07-19" }));
    expect(onSelectDate).toHaveBeenCalledWith("2026-07-19");
  });

  it("supports keyboard-only date selection through native buttons", async () => {
    const response = createForecastDaysResponse();
    const onSelectDate = vi.fn();
    const user = userEvent.setup();
    render(
      <ForecastDateStrip
        days={response.days}
        onSelectDate={onSelectDate}
        selectedDate="2026-07-18"
        todayDate={response.todayDate}
      />,
    );

    await user.tab();
    expect(screen.getByRole("button", { name: "2026-07-16" })).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(onSelectDate).toHaveBeenCalledWith("2026-07-16");
  });

  it("keeps a missing slot selectable and explains it without substituting zero", async () => {
    const response = createForecastDaysResponse();
    const onSelectDate = vi.fn();
    render(
      <ForecastDateStrip
        days={response.days}
        onSelectDate={onSelectDate}
        selectedDate="2026-07-20"
        todayDate={response.todayDate}
      />,
    );

    const missingDate = screen.getByRole("button", { name: "2026-07-20" });
    expect(missingDate).toHaveAttribute("aria-pressed", "true");
    expect(within(missingDate).getAllByText("Unavailable")).toHaveLength(2);
    expect(
      within(missingDate).getByText("No forecast run is available for this site and date."),
    ).toBeVisible();
    expect(missingDate).toHaveAccessibleDescription(
      "100 or more kilometre chance unavailable. No forecast run is available for this site and date.",
    );
    expect(within(missingDate).queryByText("0%")).not.toBeInTheDocument();

    await userEvent.click(missingDate);
    expect(onSelectDate).toHaveBeenCalledWith("2026-07-20");
  });
});
