import cors from "cors";
import express, { type Express, type Router } from "express";
import type { Logger } from "pino";

import { errorHandler } from "./http/middleware/error-handler.js";
import { notFoundHandler } from "./http/middleware/not-found.js";
import { createHttpLogger } from "./observability/http-logger.js";

export interface AppDependencies {
  readonly corsOrigin: string;
  readonly logger: Logger;
  readonly router: Router;
}

export const createApp = ({ corsOrigin, logger, router }: AppDependencies): Express => {
  const app = express();

  app.disable("x-powered-by");
  app.use(createHttpLogger(logger));
  app.use(
    cors({
      allowedHeaders: ["Content-Type", "X-Request-Id"],
      credentials: false,
      exposedHeaders: ["X-Request-Id"],
      methods: ["GET", "OPTIONS"],
      origin(requestOrigin, callback) {
        callback(null, requestOrigin === undefined || requestOrigin === corsOrigin);
      },
      optionsSuccessStatus: 204,
    }),
  );
  app.use(router);
  app.use(notFoundHandler);
  app.use(errorHandler);

  return app;
};
