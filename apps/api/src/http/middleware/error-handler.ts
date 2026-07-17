import { randomUUID } from "node:crypto";

import type { ProblemCode, ProblemDetails } from "@paragliding-forecasts/contracts";
import type { ErrorRequestHandler, Response } from "express";

import { AppError } from "../errors/app-error.js";

const problemTypeByCode: Readonly<Record<ProblemCode, string>> = {
  VALIDATION_ERROR: "urn:paragliding-forecasts:problem:validation-error",
  SITE_NOT_FOUND: "urn:paragliding-forecasts:problem:site-not-found",
  ROUTE_NOT_FOUND: "urn:paragliding-forecasts:problem:route-not-found",
  RESPONSE_CONTRACT_ERROR: "urn:paragliding-forecasts:problem:response-contract-error",
  INTERNAL_SERVER_ERROR: "urn:paragliding-forecasts:problem:internal-server-error",
};

type ResponseWithError = Response & { err?: Error };

const normalizeError = (error: unknown): AppError => {
  if (error instanceof AppError) {
    return error;
  }

  return new AppError({
    status: 500,
    code: "INTERNAL_SERVER_ERROR",
    title: "Internal server error",
    detail: "An unexpected error occurred.",
    cause: error,
  });
};

const errorForLogging = (error: unknown, normalized: AppError): Error => {
  if (error instanceof Error) {
    return error;
  }

  if (normalized.cause instanceof Error) {
    return normalized.cause;
  }

  return normalized;
};

export const errorHandler: ErrorRequestHandler = (error, request, response, next) => {
  if (response.headersSent) {
    next(error);
    return;
  }

  const normalized = normalizeError(error);
  const requestId = typeof request.id === "string" ? request.id : randomUUID();
  const problem: ProblemDetails = {
    type: problemTypeByCode[normalized.code],
    title: normalized.title,
    status: normalized.status,
    detail: normalized.detail,
    code: normalized.code,
    requestId,
    ...(normalized.issues === undefined ? {} : { issues: [...normalized.issues] }),
  };

  if (normalized.status >= 500) {
    (response as ResponseWithError).err = errorForLogging(error, normalized);
  }

  response.status(normalized.status).type("application/problem+json").send(problem);
};
