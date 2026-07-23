import { describe, expect, it } from "vitest";

import {
  getSiteLabelPresentation,
  openStreetMapStandardProvider,
} from "../../src/features/dashboard/map-provider.js";

describe("dashboard map provider", () => {
  it("keeps the OSM tile source, linked attribution, and policy together", () => {
    expect(openStreetMapStandardProvider).toEqual({
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      maximumZoom: 19,
      policyUrl: "https://operations.osmfoundation.org/policies/tiles/",
      url: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    });
  });

  it("uses presentation-only label offsets without duplicating coordinates", () => {
    expect(getSiteLabelPresentation("sopot")).toEqual({
      direction: "right",
      offset: [16, -2],
    });
    expect(getSiteLabelPresentation("dobrich-region")).toEqual({
      direction: "left",
      offset: [-16, -2],
    });
    expect(getSiteLabelPresentation("nevsha")).toEqual({
      direction: "bottom",
      offset: [0, 18],
    });
  });
});
