import { Router, type Router as ExpressRouter } from "express";

import { createHealthController, type HealthControllerDependencies } from "./health.controller.js";

export const createHealthRouter = (dependencies: HealthControllerDependencies): ExpressRouter => {
  const router = Router();

  router.get("/health", createHealthController(dependencies));

  return router;
};
