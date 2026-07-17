import { forecastQuerySchema, forecastResponseSchema } from "@paragliding-forecasts/contracts";
import type { RequestHandler } from "express";

import { parseRequest, parseResponse } from "../../http/validation.js";
import type { ForecastService } from "./forecast.service.js";

export interface ForecastControllerDependencies {
  readonly forecastService: ForecastService;
}

export const createGetForecastController =
  ({ forecastService }: ForecastControllerDependencies): RequestHandler =>
  async (request, response) => {
    const query = parseRequest(forecastQuerySchema, request.query);
    const forecast = await forecastService.getForecast(query);
    const body = parseResponse(forecastResponseSchema, forecast);

    response.status(200).json(body);
  };
