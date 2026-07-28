import { Router, type Router as ExpressRouter } from "express";

import {
  createGetForecastDaysController,
  createGetForecastController,
  createGetForecastSummariesController,
  type ForecastControllerDependencies,
} from "./forecast.controller.js";

export const createForecastRouter = (
  dependencies: ForecastControllerDependencies,
): ExpressRouter => {
  const router = Router();

  router.get("/api/v1/forecasts/summaries", createGetForecastSummariesController(dependencies));
  router.get("/api/v1/forecasts/days", createGetForecastDaysController(dependencies));
  router.get("/api/v1/forecasts", createGetForecastController(dependencies));

  return router;
};
