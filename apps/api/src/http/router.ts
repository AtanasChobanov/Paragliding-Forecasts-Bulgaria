import { Router, type Router as ExpressRouter } from "express";

export const createRootRouter = (routers: readonly ExpressRouter[]): ExpressRouter => {
  const rootRouter = Router();

  for (const router of routers) {
    rootRouter.use(router);
  }

  return rootRouter;
};
