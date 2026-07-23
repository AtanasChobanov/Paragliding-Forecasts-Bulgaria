import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { AccessibleSiteSelector } from "../../src/features/dashboard/components/AccessibleSiteSelector.js";
import { createSitesResponse } from "../support/dashboard-fixtures.js";

describe("AccessibleSiteSelector", () => {
  it("provides every site in numeric ID order and selects through one callback", async () => {
    const sites = createSitesResponse().sites.slice().reverse();
    const selectedSite = sites.find((site) => site.slug === "sopot");
    const onSelectSite = vi.fn();

    if (selectedSite === undefined) {
      throw new Error("Expected the Sopot fixture.");
    }

    render(
      <AccessibleSiteSelector
        onSelectSite={onSelectSite}
        selectedSite={selectedSite}
        sites={sites}
      />,
    );

    const selector = screen.getByLabelText("Location");
    expect(selector).toHaveValue("sopot");
    expect(screen.getAllByRole("option").map((option) => option.textContent)).toEqual([
      "Sofia - Vitosha (Kominite)",
      "Zlatitsa",
      "Sopot",
      "Nevsha",
      "Shumen",
      "Pastrina",
      "Dobrich region",
    ]);

    await userEvent.selectOptions(selector, "zlatitsa");
    expect(onSelectSite).toHaveBeenCalledWith("zlatitsa");
  });
});
