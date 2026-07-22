import { type ForecastDate, type Site, type SiteSlug } from "@paragliding-forecasts/contracts";
import { useQuery } from "@tanstack/react-query";
import { type ChangeEvent, useCallback, useEffect, useMemo } from "react";
import { useSearchParams } from "react-router-dom";

import { createDashboardQueryOptions } from "../../features/dashboard/dashboard-query-options.js";
import {
  createCanonicalDashboardSearch,
  dashboardSearchesMatch,
  parseDashboardSearch,
  resolveSelectedDate,
  resolveSelectedSite,
  type DashboardSearchSelection,
} from "../../features/dashboard/dashboard-search-params.js";
import {
  createCanonicalSummarySiteSlugs,
  indexForecastSummariesBySlug,
  selectOtherLocationSites,
} from "../../features/dashboard/dashboard-summary-selection.js";
import type { DashboardApi } from "../../services/api/dashboard-api.js";

export interface DashboardRouteProps {
  readonly dashboardApi: DashboardApi;
}

const describeError = (error: unknown): string =>
  error instanceof Error ? error.message : "The forecast request failed unexpectedly.";

interface SummaryRegionsProps {
  readonly canonicalSummarySiteSlugs: readonly SiteSlug[];
  readonly dashboardApi: DashboardApi;
  readonly forecastDate: ForecastDate;
  readonly otherLocationSites: readonly Site[];
  readonly selectedSite: Site;
}

const SummaryRegions = ({
  canonicalSummarySiteSlugs,
  dashboardApi,
  forecastDate,
  otherLocationSites,
  selectedSite,
}: SummaryRegionsProps) => {
  const queryOptions = useMemo(() => createDashboardQueryOptions(dashboardApi), [dashboardApi]);
  const summariesQuery = useQuery(
    queryOptions.forecastSummaries(forecastDate, canonicalSummarySiteSlugs),
  );
  const summariesBySlug = useMemo(
    () =>
      summariesQuery.data === undefined
        ? undefined
        : indexForecastSummariesBySlug(summariesQuery.data),
    [summariesQuery.data],
  );
  const selectedSummary = summariesBySlug?.get(selectedSite.slug);

  return (
    <>
      <section aria-busy={summariesQuery.isPending} aria-labelledby="forecast-overview-heading">
        <h2 id="forecast-overview-heading">Forecast overview</h2>
        <p>
          {selectedSite.name} · {forecastDate}
        </p>
        {summariesQuery.isPending ? <p>Loading the selected forecast…</p> : null}
        {summariesQuery.isError ? (
          <div role="alert">
            <p>{describeError(summariesQuery.error)}</p>
            <button type="button" onClick={() => void summariesQuery.refetch()}>
              Retry selected forecast
            </button>
          </div>
        ) : null}
        {selectedSummary?.availability === "available" ? (
          <p>
            Available · {selectedSummary.outputs.chance100KmPct.dataStatus} · source{" "}
            {selectedSummary.provenance.source}
          </p>
        ) : null}
        {selectedSummary?.availability === "missing" ? (
          <p>Forecast unavailable: {selectedSummary.missingReason}</p>
        ) : null}
        {summariesQuery.isSuccess && selectedSummary === undefined ? (
          <p>No summary was returned for the selected location.</p>
        ) : null}
      </section>

      <section aria-busy={summariesQuery.isPending} aria-labelledby="other-locations-heading">
        <h2 id="other-locations-heading">Other locations for this date</h2>
        {summariesQuery.isPending ? <p>Loading other locations…</p> : null}
        {summariesQuery.isError ? <p>Other-location summaries are unavailable.</p> : null}
        {!summariesQuery.isPending && !summariesQuery.isError ? (
          <ul>
            {otherLocationSites.map((site) => {
              const summary = summariesBySlug?.get(site.slug);

              return (
                <li key={site.id} data-site-slug={site.slug}>
                  <span>{site.name}</span>{" "}
                  {summary?.availability === "available" ? (
                    <span>{summary.outputs.chance100KmPct.value}% chance of 100+ km</span>
                  ) : null}
                  {summary?.availability === "missing" ? (
                    <span>Forecast unavailable: {summary.missingReason}</span>
                  ) : null}
                  {summary === undefined ? <span>No summary returned</span> : null}
                </li>
              );
            })}
          </ul>
        ) : null}
      </section>
    </>
  );
};

interface ResolvedDashboardProps {
  readonly dashboardApi: DashboardApi;
  readonly searchSelection: DashboardSearchSelection;
  readonly selectedSite: Site;
  readonly sites: readonly Site[];
}

const ResolvedDashboard = ({
  dashboardApi,
  searchSelection,
  selectedSite,
  sites,
}: ResolvedDashboardProps) => {
  const [searchParameters, setSearchParameters] = useSearchParams();
  const queryOptions = useMemo(() => createDashboardQueryOptions(dashboardApi), [dashboardApi]);
  const forecastDaysQuery = useQuery(queryOptions.forecastDays(selectedSite.slug));
  const forecastDays = forecastDaysQuery.data;
  const selectedDate = resolveSelectedDate(searchSelection, forecastDays);
  const canonicalSummarySiteSlugs = useMemo(
    () => createCanonicalSummarySiteSlugs(sites, selectedSite),
    [selectedSite, sites],
  );
  const otherLocationSites = useMemo(() => selectOtherLocationSites(sites), [sites]);

  useEffect(() => {
    const canonicalSearch = createCanonicalDashboardSearch(selectedSite.slug, selectedDate);

    if (!dashboardSearchesMatch(searchParameters, canonicalSearch)) {
      setSearchParameters(canonicalSearch, { replace: true });
    }
  }, [searchParameters, selectedDate, selectedSite.slug, setSearchParameters]);

  const selectSite = useCallback(
    (siteSlug: SiteSlug) => {
      if (siteSlug === selectedSite.slug) {
        return;
      }

      const nextSite = sites.find((site) => site.slug === siteSlug);

      if (nextSite === undefined) {
        return;
      }

      setSearchParameters(createCanonicalDashboardSearch(nextSite.slug, selectedDate));
    },
    [selectedDate, selectedSite.slug, setSearchParameters, sites],
  );

  const handleSiteChange = (event: ChangeEvent<HTMLSelectElement>) => {
    selectSite(event.target.value);
  };

  const selectDate = useCallback(
    (forecastDate: ForecastDate) => {
      if (forecastDate === selectedDate) {
        return;
      }

      setSearchParameters(createCanonicalDashboardSearch(selectedSite.slug, forecastDate));
    },
    [selectedDate, selectedSite.slug, setSearchParameters],
  );

  return (
    <>
      <section aria-labelledby="site-selector-heading">
        <h2 id="site-selector-heading">Select a location</h2>
        <label htmlFor="dashboard-site-selector">Location</label>
        <select id="dashboard-site-selector" value={selectedSite.slug} onChange={handleSiteChange}>
          {sites
            .slice()
            .sort((left, right) => left.id - right.id)
            .map((site) => (
              <option key={site.id} value={site.slug}>
                {site.name}
              </option>
            ))}
        </select>
      </section>

      {selectedDate === undefined ? (
        <>
          <section aria-labelledby="forecast-overview-heading">
            <h2 id="forecast-overview-heading">Forecast overview</h2>
            <p>Waiting for the selected location's forecast dates.</p>
          </section>
          <section aria-labelledby="other-locations-heading">
            <h2 id="other-locations-heading">Other locations for this date</h2>
            <p>Selecting a valid forecast date is still in progress.</p>
          </section>
        </>
      ) : (
        <SummaryRegions
          canonicalSummarySiteSlugs={canonicalSummarySiteSlugs}
          dashboardApi={dashboardApi}
          forecastDate={selectedDate}
          otherLocationSites={otherLocationSites}
          selectedSite={selectedSite}
        />
      )}

      <section aria-busy={forecastDaysQuery.isPending} aria-labelledby="forecast-date-heading">
        <h2 id="forecast-date-heading">Select forecast date</h2>
        {forecastDaysQuery.isPending ? <p>Loading forecast dates…</p> : null}
        {forecastDaysQuery.isError ? (
          <div role="alert">
            <p>{describeError(forecastDaysQuery.error)}</p>
            <button type="button" onClick={() => void forecastDaysQuery.refetch()}>
              Retry forecast dates
            </button>
          </div>
        ) : null}
        {forecastDaysQuery.isSuccess ? (
          <ol>
            {forecastDaysQuery.data.days.map((day) => (
              <li key={day.forecastDate}>
                <button
                  aria-current={day.forecastDate === selectedDate ? "date" : undefined}
                  type="button"
                  onClick={() => {
                    selectDate(day.forecastDate);
                  }}
                >
                  {day.forecastDate}
                </button>
              </li>
            ))}
          </ol>
        ) : null}
      </section>

      <p aria-live="polite" role="status">
        Selected {selectedSite.name}
        {selectedDate === undefined ? "" : ` for ${selectedDate}`}.
      </p>
    </>
  );
};

export const DashboardRoute = ({ dashboardApi }: DashboardRouteProps) => {
  const [searchParameters] = useSearchParams();
  const queryOptions = useMemo(() => createDashboardQueryOptions(dashboardApi), [dashboardApi]);
  const sitesQuery = useQuery(queryOptions.sites());
  const searchSelection = useMemo(() => parseDashboardSearch(searchParameters), [searchParameters]);
  const selectedSite = useMemo(
    () => resolveSelectedSite(searchSelection, sitesQuery.data?.sites ?? []),
    [searchSelection, sitesQuery.data?.sites],
  );

  return (
    <main aria-labelledby="dashboard-heading">
      <h1 id="dashboard-heading">XC Forecast dashboard</h1>
      {sitesQuery.isPending ? (
        <section aria-busy="true" aria-labelledby="site-selector-heading">
          <h2 id="site-selector-heading">Select a location</h2>
          <p>Loading available locations…</p>
        </section>
      ) : null}
      {sitesQuery.isError ? (
        <section aria-labelledby="site-selector-heading">
          <h2 id="site-selector-heading">Select a location</h2>
          <div role="alert">
            <p>{describeError(sitesQuery.error)}</p>
            <button type="button" onClick={() => void sitesQuery.refetch()}>
              Retry locations
            </button>
          </div>
        </section>
      ) : null}
      {sitesQuery.isSuccess && sitesQuery.data.sites.length === 0 ? (
        <section aria-labelledby="site-selector-heading">
          <h2 id="site-selector-heading">Select a location</h2>
          <p>No forecast locations are configured.</p>
        </section>
      ) : null}
      {sitesQuery.isSuccess && selectedSite !== undefined ? (
        <ResolvedDashboard
          dashboardApi={dashboardApi}
          searchSelection={searchSelection}
          selectedSite={selectedSite}
          sites={sitesQuery.data.sites}
        />
      ) : null}
    </main>
  );
};
