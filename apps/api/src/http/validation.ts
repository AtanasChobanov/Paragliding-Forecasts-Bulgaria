import type { ValidationIssue } from "@paragliding-forecasts/contracts";
import type { z } from "zod";

import { AppError } from "./errors/app-error.js";

const toValidationIssues = (error: z.ZodError): ValidationIssue[] =>
  error.issues.map((issue) => ({
    path: issue.path.length === 0 ? "$" : issue.path.map(String).join("."),
    message: issue.message,
  }));

export const parseRequest = <Schema extends z.ZodType>(
  schema: Schema,
  input: unknown,
): z.output<Schema> => {
  const result = schema.safeParse(input);

  if (!result.success) {
    throw new AppError({
      code: "VALIDATION_ERROR",
      detail: "The request parameters are invalid.",
      issues: toValidationIssues(result.error),
      cause: result.error,
    });
  }

  return result.data;
};

export const parseResponse = <Schema extends z.ZodType>(
  schema: Schema,
  input: unknown,
): z.output<Schema> => {
  const result = schema.safeParse(input);

  if (!result.success) {
    throw new AppError({
      code: "RESPONSE_CONTRACT_ERROR",
      detail: "The server could not produce a valid response.",
      cause: result.error,
    });
  }

  return result.data;
};
