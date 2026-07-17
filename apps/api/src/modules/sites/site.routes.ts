import { Router, type Router as ExpressRouter } from "express";

import { createListSitesController, type SiteControllerDependencies } from "./site.controller.js";

export const createSiteRouter = (dependencies: SiteControllerDependencies): ExpressRouter => {
  const router = Router();

  router.get("/api/v1/sites", createListSitesController(dependencies));

  return router;
};
