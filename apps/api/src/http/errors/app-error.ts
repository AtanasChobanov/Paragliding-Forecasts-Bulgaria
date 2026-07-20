import {
  problemDefinitionByCode,
  type ProblemCode,
  type ValidationIssue,
} from "@paragliding-forecasts/contracts";

export interface AppErrorOptions {
  readonly code: ProblemCode;
  readonly detail: string;
  readonly issues?: readonly ValidationIssue[];
  readonly cause?: unknown;
}

export class AppError extends Error {
  readonly code: ProblemCode;
  readonly detail: string;
  readonly issues: readonly ValidationIssue[] | undefined;

  get status(): number {
    return problemDefinitionByCode[this.code].status;
  }

  get title(): string {
    return problemDefinitionByCode[this.code].title;
  }

  get type(): string {
    return problemDefinitionByCode[this.code].type;
  }

  constructor(options: AppErrorOptions) {
    super(options.detail, options.cause === undefined ? undefined : { cause: options.cause });
    this.name = "AppError";
    this.code = options.code;
    this.detail = options.detail;
    this.issues = options.issues;
  }
}
