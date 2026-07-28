import { describe, expect, it } from "vitest";

import { DashboardCompatibilityError } from "../../src/features/dashboard/dashboard-compatibility-error.js";
import { presentDashboardError } from "../../src/features/dashboard/dashboard-error-presentation.js";
import {
  ApiHttpError,
  ApiNetworkError,
  ApiResponseError,
} from "../../src/services/api/api-errors.js";
import { createInternalServerProblem } from "../support/dashboard-fixtures.js";

describe("dashboard error presentation", () => {
  it("preserves HTTP Problem Details request IDs and retryability", () => {
    const problem = createInternalServerProblem();
    expect(
      presentDashboardError(
        new ApiHttpError({ status: 500, problem, requestId: null, cause: undefined }),
      ),
    ).toEqual({
      category: "request",
      message: problem.detail,
      requestId: "request-internal-error",
      retryable: true,
    });

    expect(
      presentDashboardError(
        new ApiHttpError({ status: 404, problem: null, requestId: "header-id", cause: undefined }),
      ),
    ).toMatchObject({ requestId: "header-id", retryable: false });
  });

  it("distinguishes network, invalid-response, and correlation failures", () => {
    expect(presentDashboardError(new ApiNetworkError(new Error("offline")))).toMatchObject({
      category: "request",
      requestId: null,
      retryable: true,
    });
    expect(
      presentDashboardError(
        new ApiResponseError({ status: 200, reason: "schema-validation", cause: undefined }),
      ),
    ).toMatchObject({ category: "api-compatibility", requestId: null, retryable: false });
    expect(
      presentDashboardError(
        new DashboardCompatibilityError("forecast-days", "Mismatched location."),
      ),
    ).toEqual({
      category: "api-compatibility",
      message: "Mismatched location.",
      requestId: null,
      retryable: false,
    });
  });

  it("keeps unexpected failures actionable without leaking a stack", () => {
    expect(presentDashboardError(new Error("Unexpected query failure."))).toMatchObject({
      category: "request",
      message: "Unexpected query failure.",
      retryable: true,
    });
    expect(presentDashboardError({ unsafe: true })).toMatchObject({
      message: "The forecast request failed unexpectedly. Try again.",
      retryable: true,
    });
  });
});
