import { ApiError, ApiHttpError, ApiResponseError } from "../../services/api/api-errors.js";
import { DashboardCompatibilityError } from "./dashboard-compatibility-error.js";

export type DashboardErrorCategory = "api-compatibility" | "request";

export interface DashboardErrorPresentation {
  readonly category: DashboardErrorCategory;
  readonly message: string;
  readonly requestId: string | null;
  readonly retryable: boolean;
}

export const presentDashboardError = (error: unknown): DashboardErrorPresentation => {
  if (error instanceof DashboardCompatibilityError || error instanceof ApiResponseError) {
    return {
      category: "api-compatibility",
      message: error.message,
      requestId: null,
      retryable: false,
    };
  }

  if (error instanceof ApiHttpError) {
    return {
      category: "request",
      message: error.message,
      requestId: error.requestId,
      retryable: error.retryable,
    };
  }

  if (error instanceof ApiError) {
    return {
      category: "request",
      message: error.message,
      requestId: null,
      retryable: error.retryable,
    };
  }

  return {
    category: "request",
    message:
      error instanceof Error
        ? error.message
        : "The forecast request failed unexpectedly. Try again.",
    requestId: null,
    retryable: true,
  };
};
