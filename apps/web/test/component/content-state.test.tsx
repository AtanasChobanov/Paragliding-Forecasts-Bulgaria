import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ContentState } from "../../src/components/content-state/ContentState.js";

describe("ContentState", () => {
  it("uses status semantics only for loading and alert semantics only for failures", () => {
    const { rerender } = render(
      <ContentState message="Please wait." title="Loading" variant="loading" />,
    );
    expect(screen.getByRole("status")).toHaveTextContent("Please wait.");

    rerender(<ContentState message="Nothing configured." title="Empty" variant="empty" />);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();

    rerender(<ContentState message="Supporting context." title="Information" variant="info" />);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("renders a native retry button for an actionable failure", async () => {
    const onRetry = vi.fn();
    const user = userEvent.setup();
    render(
      <ContentState
        message="The service could not be reached."
        onRetry={onRetry}
        retryLabel="Try again"
        title="Request failed"
        variant="error"
      />,
    );

    expect(screen.getByRole("alert")).toHaveTextContent("The service could not be reached.");
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(onRetry).toHaveBeenCalledOnce();
  });
});
