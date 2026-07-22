import {
  problemDetailsSchema,
  requestIdSchema,
  type ProblemDetails,
} from "@paragliding-forecasts/contracts";
import type { ZodType } from "zod";

import { ApiHttpError, ApiNetworkError, ApiResponseError } from "./api-errors.js";

type SearchParameter = readonly [name: string, value: string];

export interface GetJsonOptions<Output> {
  readonly endpoint: string;
  readonly schema: ZodType<Output>;
  readonly searchParameters?: readonly SearchParameter[];
  readonly signal: AbortSignal;
}

export interface ApiClient {
  get<Output>(options: GetJsonOptions<Output>): Promise<Output>;
}

export interface CreateApiClientOptions {
  readonly baseUrl: string;
  readonly fetchImplementation?: typeof fetch;
}

type JsonParseResult =
  | { readonly success: true; readonly data: unknown }
  | { readonly success: false; readonly error: unknown };

const parseJson = (body: string): JsonParseResult => {
  try {
    return { success: true, data: JSON.parse(body) as unknown };
  } catch (error) {
    return { success: false, error };
  }
};

const isAbortError = (error: unknown, signal: AbortSignal): boolean =>
  signal.aborted || (error instanceof Error && error.name === "AbortError");

const createBaseUrl = (baseUrl: string): URL => {
  const normalized = new URL(baseUrl);
  normalized.pathname = `${normalized.pathname.replace(/\/+$/u, "")}/`;
  return normalized;
};

const createRequestUrl = (
  baseUrl: URL,
  endpoint: string,
  searchParameters: readonly SearchParameter[],
): URL => {
  const requestUrl = new URL(endpoint.replace(/^\/+/, ""), baseUrl);

  for (const [name, value] of searchParameters) {
    requestUrl.searchParams.append(name, value);
  }

  return requestUrl;
};

const parseProblemDetails = (data: unknown, status: number): ProblemDetails | null => {
  const result = problemDetailsSchema.safeParse(data);
  return result.success && result.data.status === status ? result.data : null;
};

const parseRequestId = (response: Response): string | null => {
  const result = requestIdSchema.safeParse(response.headers.get("x-request-id"));
  return result.success ? result.data : null;
};

export const createApiClient = ({
  baseUrl,
  fetchImplementation = globalThis.fetch,
}: CreateApiClientOptions): ApiClient => {
  const normalizedBaseUrl = createBaseUrl(baseUrl);

  return {
    async get<Output>({
      endpoint,
      schema,
      searchParameters = [],
      signal,
    }: GetJsonOptions<Output>): Promise<Output> {
      const requestUrl = createRequestUrl(normalizedBaseUrl, endpoint, searchParameters);
      let response: Response;

      try {
        response = await fetchImplementation(requestUrl, {
          credentials: "omit",
          headers: { Accept: "application/json, application/problem+json" },
          method: "GET",
          signal,
        });
      } catch (error) {
        if (isAbortError(error, signal)) {
          throw error;
        }

        throw new ApiNetworkError(error);
      }

      let body: string;

      try {
        body = await response.text();
      } catch (error) {
        if (isAbortError(error, signal)) {
          throw error;
        }

        if (!response.ok) {
          throw new ApiHttpError({
            status: response.status,
            problem: null,
            requestId: parseRequestId(response),
            cause: error,
          });
        }

        throw new ApiNetworkError(error);
      }

      const parsedJson = parseJson(body);

      if (!response.ok) {
        const problem = parsedJson.success
          ? parseProblemDetails(parsedJson.data, response.status)
          : null;

        throw new ApiHttpError({
          status: response.status,
          problem,
          requestId: parseRequestId(response),
          cause: parsedJson.success || problem !== null ? undefined : parsedJson.error,
        });
      }

      if (!parsedJson.success) {
        throw new ApiResponseError({
          status: response.status,
          reason: "malformed-json",
          cause: parsedJson.error,
        });
      }

      const parsedResponse = schema.safeParse(parsedJson.data);

      if (!parsedResponse.success) {
        throw new ApiResponseError({
          status: response.status,
          reason: "schema-validation",
          cause: parsedResponse.error,
        });
      }

      return parsedResponse.data;
    },
  };
};
