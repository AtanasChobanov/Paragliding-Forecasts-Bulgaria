import { healthResponseSchema } from "@paragliding-forecasts/contracts";
import type { RequestHandler } from "express";

import { parseResponse } from "../../http/validation.js";
import { API_SERVICE_NAME } from "../../observability/logger.js";

export interface HealthControllerDependencies {
  readonly now: () => Date;
  readonly version: string;
}

export const createHealthController =
  ({ now, version }: HealthControllerDependencies): RequestHandler =>
  (_request, response) => {
    const body = parseResponse(healthResponseSchema, {
      status: "ok",
      service: API_SERVICE_NAME,
      version,
      timestamp: now().toISOString(),
    });

    response.status(200).json(body);
  };
