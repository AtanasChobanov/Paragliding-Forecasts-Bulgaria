import {
  forecastDaysQuerySchema,
  forecastDaysResponseSchema,
  forecastQuerySchema,
  forecastResponseSchema,
  forecastSummariesQuerySchema,
  forecastSummariesResponseSchema,
} from "@paragliding-forecasts/contracts";
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

export const createGetForecastSummariesController =
  ({ forecastService }: ForecastControllerDependencies): RequestHandler =>
  async (request, response) => {
    const query = parseRequest(forecastSummariesQuerySchema, request.query);
    const summaries = await forecastService.getForecastSummaries(query);
    const body = parseResponse(forecastSummariesResponseSchema, summaries);

    response.status(200).json(body);
  };

export const createGetForecastDaysController =
  ({ forecastService }: ForecastControllerDependencies): RequestHandler =>
  async (request, response) => {
    const query = parseRequest(forecastDaysQuerySchema, request.query);
    const forecastDays = await forecastService.getForecastDays(query);
    const body = parseResponse(forecastDaysResponseSchema, forecastDays);

    response.status(200).json(body);
  };
