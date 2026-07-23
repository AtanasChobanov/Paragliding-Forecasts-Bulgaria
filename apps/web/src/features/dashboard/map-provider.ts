import type { SiteSlug } from "@paragliding-forecasts/contracts";
import type { Direction, PointTuple } from "leaflet";

export interface RasterTileProvider {
  readonly attribution: string;
  readonly maximumZoom: number;
  readonly policyUrl: string;
  readonly url: string;
}

export const openStreetMapStandardProvider: RasterTileProvider = {
  attribution:
    '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  maximumZoom: 19,
  policyUrl: "https://operations.osmfoundation.org/policies/tiles/",
  url: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
};

export interface SiteLabelPresentation {
  readonly direction: Direction;
  readonly offset: PointTuple;
}

const defaultLabelPresentation: SiteLabelPresentation = {
  direction: "right",
  offset: [16, -2],
};

const siteLabelOverrides: Readonly<Partial<Record<SiteSlug, SiteLabelPresentation>>> = {
  "dobrich-region": { direction: "left", offset: [-16, -2] },
  nevsha: { direction: "bottom", offset: [0, 18] },
  pastrina: { direction: "right", offset: [16, 2] },
  shumen: { direction: "left", offset: [-16, -2] },
  "sofia-vitosha-kominite": { direction: "right", offset: [16, 2] },
};

export const getSiteLabelPresentation = (siteSlug: SiteSlug): SiteLabelPresentation =>
  siteLabelOverrides[siteSlug] ?? defaultLabelPresentation;
