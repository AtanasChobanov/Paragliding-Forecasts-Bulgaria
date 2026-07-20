import { randomUUID } from "node:crypto";

import { problemDefinitionByCode, type ProblemDetails } from "@paragliding-forecasts/contracts";
import type { ErrorRequestHandler, Response } from "express";

import { AppError } from "../errors/app-error.js";

type ResponseWithError = Response & { err?: Error };

const normalizeError = (error: unknown): AppError => {
  if (error instanceof AppError) {
    return error;
  }

  return new AppError({
    code: "INTERNAL_SERVER_ERROR",
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
  const definition = problemDefinitionByCode[normalized.code];
  const requestId = typeof request.id === "string" ? request.id : randomUUID();
  const problem: ProblemDetails = {
    type: definition.type,
    title: definition.title,
    status: definition.status,
    detail: normalized.detail,
    code: normalized.code,
    requestId,
    ...(normalized.issues === undefined ? {} : { issues: [...normalized.issues] }),
  };

  if (definition.status >= 500) {
    (response as ResponseWithError).err = errorForLogging(error, normalized);
  }

  response.status(definition.status).type("application/problem+json").send(problem);
};
