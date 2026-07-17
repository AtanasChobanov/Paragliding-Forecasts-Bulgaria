import { randomUUID } from "node:crypto";

import type { Logger } from "pino";
import { pinoHttp } from "pino-http";

const REQUEST_ID_PATTERN = /^[A-Za-z0-9._:-]+$/;
const MAX_REQUEST_ID_LENGTH = 128;

export const sanitizeRequestId = (value: string | string[] | undefined): string | undefined => {
  if (
    typeof value !== "string" ||
    value.length === 0 ||
    value.length > MAX_REQUEST_ID_LENGTH ||
    !REQUEST_ID_PATTERN.test(value)
  ) {
    return undefined;
  }

  return value;
};

export const createHttpLogger = (logger: Logger) =>
  pinoHttp({
    logger,
    quietReqLogger: true,
    genReqId(request, response) {
      const requestId = sanitizeRequestId(request.headers["x-request-id"]) ?? randomUUID();
      response.setHeader("X-Request-Id", requestId);
      return requestId;
    },
    customLogLevel(_request, response, error) {
      if (error !== undefined || response.statusCode >= 500) {
        return "error";
      }

      if (response.statusCode >= 400) {
        return "warn";
      }

      return "info";
    },
  });
