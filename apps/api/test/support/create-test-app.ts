import { Router, type Express, type Router as ExpressRouter } from "express";
import pino from "pino";

import { createApp } from "../../src/app.js";
import { createRootRouter } from "../../src/http/router.js";
import { createHealthRouter } from "../../src/modules/health/health.routes.js";
import { InMemorySiteRepository } from "../../src/modules/sites/in-memory-site.repository.js";
import { createSiteRouter } from "../../src/modules/sites/site.routes.js";
import { SiteService } from "../../src/modules/sites/site.service.js";
import { API_VERSION } from "../../src/observability/logger.js";

export const FIXED_NOW = new Date("2026-07-17T12:00:00.000Z");

export interface TestAppOptions {
  readonly additionalRouters?: readonly ExpressRouter[];
  readonly corsOrigin?: string;
  readonly version?: string;
}

export const createTestApp = ({
  additionalRouters = [],
  corsOrigin = "http://localhost:5173",
  version = API_VERSION,
}: TestAppOptions = {}): Express => {
  const healthRouter = createHealthRouter({
    now: () => FIXED_NOW,
    version,
  });
  const siteRepository = new InMemorySiteRepository();
  const siteService = new SiteService(siteRepository);
  const siteRouter = createSiteRouter({ siteService });
  const router = createRootRouter([healthRouter, siteRouter, ...additionalRouters]);

  return createApp({
    corsOrigin,
    logger: pino({ level: "silent" }),
    router,
  });
};

export const createThrowingRouter = (): ExpressRouter => {
  const router = Router();

  router.get("/boom", () => {
    throw new Error("Internal secret failure");
  });

  return router;
};
