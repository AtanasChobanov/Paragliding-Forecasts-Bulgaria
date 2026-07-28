import { z } from "zod";

export const siteIdSchema = z.number().int().positive().max(Number.MAX_SAFE_INTEGER);

export const siteSlugSchema = z
  .string()
  .trim()
  .min(1)
  .max(80)
  .regex(/^[a-z0-9]+(?:-[a-z0-9]+)*$/);

export const siteSchema = z.strictObject({
  id: siteIdSchema,
  slug: siteSlugSchema,
  name: z.string().trim().min(1),
  latitude: z.number().min(-90).max(90),
  longitude: z.number().min(-180).max(180),
});

export const sitesResponseSchema = z.strictObject({
  sites: z.array(siteSchema),
});

export type SiteId = z.infer<typeof siteIdSchema>;
export type SiteSlug = z.infer<typeof siteSlugSchema>;
export type Site = z.infer<typeof siteSchema>;
export type SitesResponse = z.infer<typeof sitesResponseSchema>;
