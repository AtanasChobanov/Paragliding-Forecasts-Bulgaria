import type { ForecastSummary, Site, SiteSlug } from "@paragliding-forecasts/contracts";
import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";

import { LocationSummaryCard } from "../../src/features/dashboard/components/LocationSummaryCard.js";
import { OtherLocationsSection } from "../../src/features/dashboard/components/OtherLocationsSection.js";
import {
  createForecastSummariesResponse,
  createSitesResponse,
  missingMetric,
} from "../support/dashboard-fixtures.js";

type AvailableSummary = Extract<ForecastSummary, { readonly availability: "available" }>;

const renderWithRouter = (content: ReactNode) => render(<MemoryRouter>{content}</MemoryRouter>);

const availableSummary = (): AvailableSummary => {
  const summary = createForecastSummariesResponse().summaries.find(
    (candidate): candidate is AvailableSummary => candidate.availability === "available",
  );

  if (summary === undefined) {
    throw new Error("Expected an available summary fixture.");
  }

  return summary;
};

const requireSite = (slug: SiteSlug): Site => {
  const site = createSitesResponse().sites.find((candidate) => candidate.slug === slug);

  if (site === undefined) {
    throw new Error(`Expected site ${slug}.`);
  }

  return site;
};

const summaryFor = (site: Site): AvailableSummary => ({
  ...availableSummary(),
  siteId: site.id,
  siteSlug: site.slug,
});

describe("OtherLocationsSection", () => {
  it("preserves the explicit UI order independently of map insertion order", () => {
    const zlatitsa = requireSite("zlatitsa");
    const sofia = requireSite("sofia-vitosha-kominite");
    const dobrich = requireSite("dobrich-region");
    const sites = [zlatitsa, sofia, dobrich];
    const summaries = new Map<SiteSlug, ForecastSummary>([
      [dobrich.slug, summaryFor(dobrich)],
      [zlatitsa.slug, summaryFor(zlatitsa)],
      [sofia.slug, summaryFor(sofia)],
    ]);

    renderWithRouter(
      <OtherLocationsSection forecastDate="2026-07-18" sites={sites} summariesBySlug={summaries} />,
    );

    const items = screen.getAllByRole("listitem");
    expect(items.map((item) => item.getAttribute("data-site-slug"))).toEqual([
      "zlatitsa",
      "sofia-vitosha-kominite",
      "dobrich-region",
    ]);
    expect(screen.getAllByText("Mock data")).toHaveLength(3);
    expect(screen.getAllByRole("progressbar")).toHaveLength(3);
    expect(screen.getAllByText("Confidence")).toHaveLength(3);
    expect(screen.getAllByRole("link", { name: /View detailed forecast for/i })).toHaveLength(3);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("keeps a selected location when it is also configured as an Other card", () => {
    const selectedSite = requireSite("zlatitsa");
    renderWithRouter(
      <OtherLocationsSection
        forecastDate="2026-07-18"
        sites={[selectedSite]}
        summariesBySlug={new Map([[selectedSite.slug, summaryFor(selectedSite)]])}
      />,
    );

    expect(screen.getByRole("heading", { name: "Zlatitsa" })).toBeVisible();
  });

  it("renders per-metric missing values without progress or zero substitution", () => {
    const site = requireSite("sopot");
    const summary = availableSummary();
    renderWithRouter(
      <LocationSummaryCard
        forecastDate="2026-07-18"
        site={site}
        summary={{
          ...summary,
          outputs: { ...summary.outputs, chance100KmPct: missingMetric },
        }}
      />,
    );

    expect(screen.getByText("Mixed data")).toBeVisible();
    expect(screen.getAllByText("Unavailable").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("No forecast run is available for this site and date.")).toBeVisible();
    expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
    expect(screen.queryByText("0")).not.toBeInTheDocument();
  });

  it("distinguishes missing summaries from omitted summaries", () => {
    const zlatitsa = requireSite("zlatitsa");
    const missingSummary = createForecastSummariesResponse().summaries.find(
      (summary) => summary.availability === "missing",
    );
    const { rerender } = renderWithRouter(
      <LocationSummaryCard forecastDate="2026-07-18" site={zlatitsa} summary={missingSummary} />,
    );

    expect(screen.getByText("Forecast unavailable")).toBeVisible();
    expect(screen.getByText("No forecast exists for Zlatitsa on 2026-07-18.")).toBeVisible();

    rerender(
      <MemoryRouter>
        <LocationSummaryCard forecastDate="2026-07-18" site={zlatitsa} summary={undefined} />
      </MemoryRouter>,
    );
    expect(screen.getByText("No summary returned")).toBeVisible();
    expect(
      screen.getByText("The service response omitted this comparison location."),
    ).toBeVisible();
    expect(within(screen.getByRole("article")).queryByText("mock-v2")).not.toBeInTheDocument();
  });
});
