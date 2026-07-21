import { z } from "zod";

export const problemCodeSchema = z.enum([
  "VALIDATION_ERROR",
  "SITE_NOT_FOUND",
  "FORECAST_NOT_FOUND",
  "ROUTE_NOT_FOUND",
  "RESPONSE_CONTRACT_ERROR",
  "INTERNAL_SERVER_ERROR",
]);

export type ProblemCode = z.infer<typeof problemCodeSchema>;

export interface ProblemDefinition {
  readonly type: string;
  readonly title: string;
  readonly status: number;
}

export const problemDefinitionByCode = {
  VALIDATION_ERROR: {
    type: "urn:paragliding-forecasts:problem:validation-error",
    title: "Invalid request",
    status: 400,
  },
  SITE_NOT_FOUND: {
    type: "urn:paragliding-forecasts:problem:site-not-found",
    title: "Site not found",
    status: 404,
  },
  FORECAST_NOT_FOUND: {
    type: "urn:paragliding-forecasts:problem:forecast-not-found",
    title: "Forecast not found",
    status: 404,
  },
  ROUTE_NOT_FOUND: {
    type: "urn:paragliding-forecasts:problem:route-not-found",
    title: "Route not found",
    status: 404,
  },
  RESPONSE_CONTRACT_ERROR: {
    type: "urn:paragliding-forecasts:problem:response-contract-error",
    title: "Response contract failure",
    status: 500,
  },
  INTERNAL_SERVER_ERROR: {
    type: "urn:paragliding-forecasts:problem:internal-server-error",
    title: "Internal server error",
    status: 500,
  },
} as const satisfies Readonly<Record<ProblemCode, ProblemDefinition>>;

export const validationIssueSchema = z.strictObject({
  path: z.string(),
  message: z.string().trim().min(1),
});

export const requestIdSchema = z
  .string()
  .min(1)
  .max(128)
  .regex(/^[A-Za-z0-9._:-]+$/);

export const problemDetailsSchema = z
  .strictObject({
    type: z.string().startsWith("urn:paragliding-forecasts:problem:"),
    title: z.string().trim().min(1),
    status: z.number().int().min(400).max(599),
    detail: z.string().trim().min(1),
    code: problemCodeSchema,
    requestId: requestIdSchema,
    issues: z.array(validationIssueSchema).optional(),
  })
  .superRefine((problem, context) => {
    const definition = problemDefinitionByCode[problem.code];

    for (const field of ["type", "title", "status"] as const) {
      if (problem[field] !== definition[field]) {
        context.addIssue({
          code: "custom",
          message: `Expected ${field} to match problem code ${problem.code}.`,
          path: [field],
        });
      }
    }
  });

export type ValidationIssue = z.infer<typeof validationIssueSchema>;
export type ProblemDetails = z.infer<typeof problemDetailsSchema>;
