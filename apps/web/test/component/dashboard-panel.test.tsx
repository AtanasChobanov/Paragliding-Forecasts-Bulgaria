import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DashboardPanel } from "../../src/components/dashboard-panel/DashboardPanel.js";

describe("DashboardPanel", () => {
  it("associates its section with the heading and optional accessory", () => {
    render(
      <DashboardPanel
        accessory={<button type="button">Panel action</button>}
        headingId="test-panel-heading"
        title="Test panel"
      >
        Panel body
      </DashboardPanel>,
    );

    const panel = screen.getByRole("region", { name: "Test panel" });
    expect(panel).toHaveAttribute("aria-labelledby", "test-panel-heading");
    expect(screen.getByRole("heading", { level: 2, name: "Test panel" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Panel action" })).toBeVisible();
    expect(screen.getByText("Panel body")).toBeVisible();
  });

  it("adds busy semantics only while its owning region is waiting", () => {
    const { rerender } = render(
      <DashboardPanel busy headingId="busy-heading" title="Busy panel">
        Waiting
      </DashboardPanel>,
    );

    expect(screen.getByRole("region", { name: "Busy panel" })).toHaveAttribute("aria-busy", "true");

    rerender(
      <DashboardPanel headingId="busy-heading" title="Busy panel">
        Ready
      </DashboardPanel>,
    );
    expect(screen.getByRole("region", { name: "Busy panel" })).not.toHaveAttribute("aria-busy");
  });
});
