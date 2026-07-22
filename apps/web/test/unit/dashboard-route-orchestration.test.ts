import type { ForecastDate, Site } from "@paragliding-forecasts/contracts";
import { describe, expect, it } from "vitest";

import {
  DashboardCompatibilityError,
  assertForecastDaysCorrelation,
  assertForecastSummariesCorrelation,
} from "../../src/features/dashboard/dashboard-compatibility-error.js";
import {
  createCanonicalDashboardSearch,
  dashboardSearchesMatch,
  findDefaultSite,
  parseDashboardSearch,
  resolveSelectedDate,
  resolveSelectedSite,
} from "../../src/features/dashboard/dashboard-search-params.js";
import {
  OTHER_LOCATION_SLUGS,
  createCanonicalSummarySiteSlugs,
  indexForecastSummariesBySlug,
  selectOtherLocationSites,
} from "../../src/features/dashboard/dashboard-summary-selection.js";
import {
  createForecastDaysResponse,
  createForecastSummariesResponse,
  createSitesResponse,
} from "../support/dashboard-fixtures.js";

const sites = createSitesResponse().sites;

const parse = (search: string) => parseDashboardSearch(new URLSearchParams(search));

describe("dashboard URL selection", () => {
  it("parses site and date only when each parameter is single-valued and the date is real", () => {
    expect(parse("site=sopot&date=2026-07-18")).toEqual({
      site: { kind: "single", value: "sopot" },
      date: { kind: "valid", value: "2026-07-18" },
    });
    expect(parse("")).toEqual({ site: { kind: "missing" }, date: { kind: "missing" } });
    expect(parse("site=sopot&site=zlatitsa&date=2026-07-18&date=2026-07-19")).toEqual({
      site: { kind: "repeated" },
      date: { kind: "repeated" },
    });
    expect(parse("site=sopot&date=2026-02-30").date).toEqual({
      kind: "invalid",
      value: "2026-02-30",
    });
  });

  it("finds the minimum numeric site ID explicitly and handles an empty catalog", () => {
    const unorderedSites = [sites[3], sites[6], sites[2], sites[0]].filter(
      (site): site is Site => site !== undefined,
    );

    expect(findDefaultSite(unorderedSites)?.slug).toBe("sofia-vitosha-kominite");
    expect(findDefaultSite([])).toBeUndefined();
  });

  it.each([
    ["known", "site=sopot", "sopot"],
    ["missing", "", "sofia-vitosha-kominite"],
    ["unknown", "site=unknown", "sofia-vitosha-kominite"],
    ["repeated", "site=sopot&site=zlatitsa", "sofia-vitosha-kominite"],
  ])("resolves a %s site selection", (_description, search, expectedSlug) => {
    expect(resolveSelectedSite(parse(search), sites)?.slug).toBe(expectedSlug);
  });

  it("uses a valid URL date immediately, then normalizes against the returned strip", () => {
    const days = createForecastDaysResponse();

    expect(resolveSelectedDate(parse("date=2026-07-17"), undefined)).toBe("2026-07-17");
    expect(resolveSelectedDate(parse("date=2026-07-17"), days)).toBe("2026-07-17");
    expect(resolveSelectedDate(parse("date=2026-08-01"), days)).toBe(days.todayDate);
  });

  it.each(["", "date=not-a-date", "date=2026-07-18&date=2026-07-19"])(
    "waits for days before defaulting a non-valid date from %s",
    (search) => {
      const days = createForecastDaysResponse();

      expect(resolveSelectedDate(parse(search), undefined)).toBeUndefined();
      expect(resolveSelectedDate(parse(search), days)).toBe(days.todayDate);
    },
  );

  it("creates only owned parameters in canonical site-then-date order", () => {
    const canonical = createCanonicalDashboardSearch("sopot", "2026-07-18");

    expect(canonical.toString()).toBe("site=sopot&date=2026-07-18");
    expect(dashboardSearchesMatch(new URLSearchParams(canonical), canonical)).toBe(true);
    expect(
      dashboardSearchesMatch(
        new URLSearchParams("date=2026-07-18&site=sopot&unowned=value"),
        canonical,
      ),
    ).toBe(false);
  });
});

describe("dashboard summary selection", () => {
  it("keeps the image-defined Other Locations order including a selected duplicate", () => {
    expect(OTHER_LOCATION_SLUGS).toEqual(["zlatitsa", "sofia-vitosha-kominite", "dobrich-region"]);
    expect(selectOtherLocationSites(sites).map((site) => site.slug)).toEqual(OTHER_LOCATION_SLUGS);
  });

  it("requests selected plus available configured sites, deduped by ID and sorted by ID", () => {
    const sopot = sites.find((site) => site.slug === "sopot");
    expect(sopot).toBeDefined();

    expect(createCanonicalSummarySiteSlugs(sites, sopot as Site)).toEqual([
      "sofia-vitosha-kominite",
      "zlatitsa",
      "sopot",
      "dobrich-region",
    ]);

    const duplicatedIdCatalog = [
      ...(sites.filter((site) => site.slug === "sopot" || site.slug === "zlatitsa") as Site[]),
      { ...(sites.find((site) => site.slug === "dobrich-region") as Site), id: 2 },
    ];
    expect(createCanonicalSummarySiteSlugs(duplicatedIdCatalog, sopot as Site)).toEqual([
      "dobrich-region",
      "sopot",
    ]);
  });

  it("filters absent configured sites without changing the remaining presentation order", () => {
    const partialCatalog = sites.filter(
      (site) => site.slug === "sopot" || site.slug === "dobrich-region" || site.slug === "zlatitsa",
    );
    const selectedSite = partialCatalog.find((site) => site.slug === "sopot");

    expect(selectOtherLocationSites(partialCatalog).map((site) => site.slug)).toEqual([
      "zlatitsa",
      "dobrich-region",
    ]);
    expect(createCanonicalSummarySiteSlugs(partialCatalog, selectedSite as Site)).toEqual([
      "zlatitsa",
      "sopot",
      "dobrich-region",
    ]);
  });

  it("indexes summaries by slug instead of relying on a presentation position", () => {
    const response = createForecastSummariesResponse();
    const summariesBySlug = indexForecastSummariesBySlug(response);

    expect(summariesBySlug.get("sopot")?.siteId).toBe(3);
    expect(summariesBySlug.get("zlatitsa")?.siteId).toBe(2);
    expect(summariesBySlug.get("dobrich-region")).toBeUndefined();
  });
});

describe("dashboard response correlation", () => {
  it("accepts correlated days and a partial summaries subset", () => {
    const days = createForecastDaysResponse();
    const summaries = createForecastSummariesResponse();

    expect(assertForecastDaysCorrelation(days, "sopot")).toBe(days);
    expect(
      assertForecastSummariesCorrelation(summaries, "2026-07-18", [
        "zlatitsa",
        "sopot",
        "dobrich-region",
      ]),
    ).toBe(summaries);
  });

  it("rejects days returned for another requested site with a typed compatibility error", () => {
    const response = { ...createForecastDaysResponse(), siteSlug: "zlatitsa" };

    expect(() => assertForecastDaysCorrelation(response, "sopot")).toThrow(
      DashboardCompatibilityError,
    );
    expect(() => assertForecastDaysCorrelation(response, "sopot")).toThrow(
      "days for a different location",
    );
  });

  it("rejects a correlated-schema summary response for another requested date", () => {
    const date = "2026-07-19" satisfies ForecastDate;
    const base = createForecastSummariesResponse();
    const response = {
      ...base,
      forecastDate: date,
      summaries: base.summaries.map((summary) => ({ ...summary, forecastDate: date })),
    };

    expect(() =>
      assertForecastSummariesCorrelation(response, "2026-07-18", ["zlatitsa", "sopot"]),
    ).toThrow("summaries for a different date");
  });

  it("rejects returned summary slugs outside the exact requested set", () => {
    const response = createForecastSummariesResponse();

    expect(() => assertForecastSummariesCorrelation(response, "2026-07-18", ["sopot"])).toThrow(
      "summary for an unrequested location",
    );
  });
});
