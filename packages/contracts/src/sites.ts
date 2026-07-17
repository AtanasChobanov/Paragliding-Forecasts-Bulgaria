import { z } from "zod";

export const siteIdSchema = z
  .string()
  .trim()
  .min(1)
  .max(80)
  .regex(/^[a-z0-9]+(?:-[a-z0-9]+)*$/);

export const siteSchema = z.strictObject({
  id: siteIdSchema,
  name: z.string().trim().min(1),
});

export const sitesResponseSchema = z.strictObject({
  sites: z.array(siteSchema),
});

export type SiteId = z.infer<typeof siteIdSchema>;
export type Site = z.infer<typeof siteSchema>;
export type SitesResponse = z.infer<typeof sitesResponseSchema>;
