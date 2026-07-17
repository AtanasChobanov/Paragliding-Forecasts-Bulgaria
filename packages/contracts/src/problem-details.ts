import { z } from "zod";

export const problemCodeSchema = z.enum([
  "VALIDATION_ERROR",
  "SITE_NOT_FOUND",
  "ROUTE_NOT_FOUND",
  "RESPONSE_CONTRACT_ERROR",
  "INTERNAL_SERVER_ERROR",
]);

export const validationIssueSchema = z.strictObject({
  path: z.string(),
  message: z.string().trim().min(1),
});

export const requestIdSchema = z
  .string()
  .min(1)
  .max(128)
  .regex(/^[A-Za-z0-9._:-]+$/);

export const problemDetailsSchema = z.strictObject({
  type: z.string().startsWith("urn:paragliding-forecasts:problem:"),
  title: z.string().trim().min(1),
  status: z.number().int().min(400).max(599),
  detail: z.string().trim().min(1),
  code: problemCodeSchema,
  requestId: requestIdSchema,
  issues: z.array(validationIssueSchema).optional(),
});

export type ProblemCode = z.infer<typeof problemCodeSchema>;
export type ValidationIssue = z.infer<typeof validationIssueSchema>;
export type ProblemDetails = z.infer<typeof problemDetailsSchema>;
