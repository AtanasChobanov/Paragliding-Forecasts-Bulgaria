import { QueryClient } from "@tanstack/react-query";

import { ApiHttpError, ApiNetworkError } from "../services/api/api-errors.js";

export const FORECAST_QUERY_STALE_TIME_MS = 5 * 60 * 1_000;

export const shouldRetryDashboardQuery = (failureCount: number, error: Error): boolean =>
  failureCount === 0 &&
  (error instanceof ApiNetworkError ||
    (error instanceof ApiHttpError && error.status >= 500 && error.status <= 599));

export const createDashboardQueryClient = (): QueryClient =>
  new QueryClient({
    defaultOptions: {
      queries: {
        refetchOnWindowFocus: false,
        retry: shouldRetryDashboardQuery,
        staleTime: FORECAST_QUERY_STALE_TIME_MS,
      },
    },
  });
