import type { RequestHandler } from "express";

import { AppError } from "../errors/app-error.js";

export const notFoundHandler: RequestHandler = (request, _response, next) => {
  next(
    new AppError({
      status: 404,
      code: "ROUTE_NOT_FOUND",
      title: "Route not found",
      detail: `${request.method} ${request.path} does not exist.`,
    }),
  );
};
