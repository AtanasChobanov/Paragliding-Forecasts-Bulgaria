import { sitesResponseSchema } from "@paragliding-forecasts/contracts";
import type { RequestHandler } from "express";

import { parseResponse } from "../../http/validation.js";
import type { SiteService } from "./site.service.js";

export interface SiteControllerDependencies {
  readonly siteService: SiteService;
}

export const createListSitesController =
  ({ siteService }: SiteControllerDependencies): RequestHandler =>
  async (_request, response) => {
    const sites = await siteService.listSites();
    const body = parseResponse(sitesResponseSchema, { sites });

    response.status(200).json(body);
  };
