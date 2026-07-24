import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ForecastDateSelector } from "../../src/features/forecast-details/components/ForecastDateSelector.js";
import { createForecastDaysResponse } from "../support/dashboard-fixtures.js";

describe("ForecastDateSelector", () => {
  it("uses the API-provided date slots and reports a selected date without pagination controls", async () => {
    const onSelectDate = vi.fn();
    const { days } = createForecastDaysResponse();
    render(
      <ForecastDateSelector days={days} onSelectDate={onSelectDate} selectedDate="2026-07-18" />,
    );

    const selector = screen.getByLabelText("Forecast date");
    expect(screen.getAllByRole("option")).toHaveLength(5);
    await userEvent.selectOptions(selector, "2026-07-19");
    expect(onSelectDate).toHaveBeenCalledWith("2026-07-19");
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
