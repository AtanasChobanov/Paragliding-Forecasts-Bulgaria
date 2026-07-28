import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AppHeader } from "../../src/components/app-header/AppHeader.js";
import { DashboardShell } from "../../src/features/dashboard/components/DashboardShell.js";

describe("dashboard visual shell", () => {
  it("renders the application banner and one semantic dashboard main", () => {
    render(
      <>
        <AppHeader />
        <DashboardShell
          announcement="Sopot on 20 July selected."
          forecastDates={<span>dates slot</span>}
          locationSelector={<span>location slot</span>}
          otherLocations={<span>other slot</span>}
          overview={<span>overview slot</span>}
        />
      </>,
    );

    expect(screen.getByRole("banner")).toBeVisible();
    expect(screen.getByLabelText("XC Forecast")).toBeVisible();
    expect(screen.getByText("Decision support only")).toBeVisible();
    expect(screen.getByText("Not aviation weather")).toBeVisible();

    const main = screen.getByRole("main", { name: "XC Forecast dashboard" });
    expect(within(main).getByRole("heading", { level: 1 })).toHaveTextContent(
      "XC Forecast dashboard",
    );
    expect(
      within(main)
        .getAllByRole("heading", { level: 2 })
        .map((heading) => heading.textContent),
    ).toEqual([
      "Select a location",
      "Forecast overview",
      "Other locations for this date",
      "Select forecast date",
    ]);
  });

  it("places every route-owned slot once and keeps a restrained live region", () => {
    const { container } = render(
      <DashboardShell
        announcement="Selection changed."
        forecastDates={<span>unique dates</span>}
        locationSelector={<span>unique location</span>}
        otherLocations={<span>unique other</span>}
        overview={<span>unique overview</span>}
      />,
    );

    for (const content of ["unique location", "unique overview", "unique other", "unique dates"]) {
      expect(screen.getAllByText(content)).toHaveLength(1);
    }

    expect(container.querySelector("[aria-live='polite']")).toHaveTextContent("Selection changed.");
    expect(screen.queryByRole("button", { name: /notification/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /detailed forecast/i })).not.toBeInTheDocument();
  });
});
