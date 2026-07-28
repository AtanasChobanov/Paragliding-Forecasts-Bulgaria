import type { ProblemCode, ProblemDetails } from "@paragliding-forecasts/contracts";

export type ApiErrorKind = "network" | "http" | "invalid-response";
export type ApiResponseFailureReason = "malformed-json" | "schema-validation";

export abstract class ApiError extends Error {
  abstract readonly kind: ApiErrorKind;
  abstract readonly retryable: boolean;

  protected constructor(name: string, message: string, cause: unknown) {
    super(message, { cause });
    this.name = name;
  }
}

export class ApiNetworkError extends ApiError {
  readonly kind = "network" as const;
  readonly retryable = true;

  constructor(cause: unknown) {
    super(
      "ApiNetworkError",
      "Unable to reach the local forecast API. Check that it is running and try again.",
      cause,
    );
  }
}

export interface ApiHttpErrorOptions {
  readonly status: number;
  readonly problem: ProblemDetails | null;
  readonly requestId: string | null;
  readonly cause: unknown;
}

const fallbackHttpMessage = (status: number): string =>
  status >= 500
    ? `The forecast service returned an error (HTTP ${String(status)}). Try again.`
    : `The forecast service rejected the request (HTTP ${String(status)}).`;

export class ApiHttpError extends ApiError {
  readonly kind = "http" as const;
  readonly retryable: boolean;
  readonly status: number;
  readonly problem: ProblemDetails | null;
  readonly code: ProblemCode | null;
  readonly requestId: string | null;

  constructor({ status, problem, requestId, cause }: ApiHttpErrorOptions) {
    super("ApiHttpError", problem?.detail ?? fallbackHttpMessage(status), cause);
    this.status = status;
    this.problem = problem;
    this.code = problem?.code ?? null;
    this.requestId = problem?.requestId ?? requestId;
    this.retryable = status >= 500 && status <= 599;
  }
}

export interface ApiResponseErrorOptions {
  readonly status: number;
  readonly reason: ApiResponseFailureReason;
  readonly cause: unknown;
}

export class ApiResponseError extends ApiError {
  readonly kind = "invalid-response" as const;
  readonly retryable = false;
  readonly status: number;
  readonly reason: ApiResponseFailureReason;

  constructor({ status, reason, cause }: ApiResponseErrorOptions) {
    super(
      "ApiResponseError",
      "The forecast service returned data that this dashboard cannot read.",
      cause,
    );
    this.status = status;
    this.reason = reason;
  }
}
