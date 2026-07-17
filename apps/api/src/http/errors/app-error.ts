import type { ProblemCode, ValidationIssue } from "@paragliding-forecasts/contracts";

export interface AppErrorOptions {
  readonly status: number;
  readonly code: ProblemCode;
  readonly title: string;
  readonly detail: string;
  readonly issues?: readonly ValidationIssue[];
  readonly cause?: unknown;
}

export class AppError extends Error {
  readonly status: number;
  readonly code: ProblemCode;
  readonly title: string;
  readonly detail: string;
  readonly issues: readonly ValidationIssue[] | undefined;

  constructor(options: AppErrorOptions) {
    super(options.detail, options.cause === undefined ? undefined : { cause: options.cause });
    this.name = "AppError";
    this.status = options.status;
    this.code = options.code;
    this.title = options.title;
    this.detail = options.detail;
    this.issues = options.issues;
  }
}
