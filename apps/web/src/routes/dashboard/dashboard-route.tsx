import {
  type ForecastDate,
  type ForecastDaysResponse,
  type Site,
  type SiteSlug,
} from "@paragliding-forecasts/contracts";
import { useQuery } from "@tanstack/react-query";
import { type ReactNode, useCallback, useEffect, useMemo } from "react";
import { useSearchParams } from "react-router-dom";

import { ContentState } from "../../components/content-state/ContentState.js";
import { DashboardErrorState } from "../../features/dashboard/components/DashboardErrorState.js";
import { DashboardShell } from "../../features/dashboard/components/DashboardShell.js";
import { ForecastDateStrip } from "../../features/dashboard/components/ForecastDateStrip.js";
import {
  ForecastOverview,
  SelectedForecastHeading,
} from "../../features/dashboard/components/ForecastOverview.js";
import { OtherLocationsSection } from "../../features/dashboard/components/OtherLocationsSection.js";
import { SiteSelectorSection } from "../../features/dashboard/components/SiteSelectorSection.js";
import { presentDashboardError } from "../../features/dashboard/dashboard-error-presentation.js";
import {
  createDashboardQueryOptions,
  dashboardRefreshPolicy,
} from "../../features/dashboard/dashboard-query-options.js";
import {
  createCanonicalDashboardSearch,
  dashboardSearchesMatch,
  parseDashboardSearch,
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

interface SummaryDashboardProps {
  readonly canonicalSummarySiteSlugs: readonly SiteSlug[];
  readonly dashboardApi: DashboardApi;
  readonly datesContent: ReactNode;
  readonly forecastDate: ForecastDate;
  readonly locationSelector: ReactNode;
  readonly otherLocationSites: readonly Site[];
  readonly selectedSite: Site;
}

const SummaryDashboard = ({
  canonicalSummarySiteSlugs,
  dashboardApi,
  datesContent,
  forecastDate,
  locationSelector,
  otherLocationSites,
  selectedSite,
}: SummaryDashboardProps) => {
  const queryOptions = useMemo(() => createDashboardQueryOptions(dashboardApi), [dashboardApi]);
  const summariesQuery = useQuery({
    ...queryOptions.forecastSummaries(forecastDate, canonicalSummarySiteSlugs),
    ...dashboardRefreshPolicy,
  });
  const summariesBySlug = useMemo(
    () =>
      summariesQuery.data === undefined
        ? undefined
        : indexForecastSummariesBySlug(summariesQuery.data),
    [summariesQuery.data],
  );
  const selectedSummary = summariesBySlug?.get(selectedSite.slug);
  const summaryError = summariesQuery.isError ? presentDashboardError(summariesQuery.error) : null;

  const overview = summariesQuery.isPending ? (
    <div>
      <SelectedForecastHeading forecastDate={forecastDate} siteName={selectedSite.name} />
      <ContentState
        message="The selected forecast is being validated and loaded."
        title="Loading the selected forecast…"
        variant="loading"
      />
    </div>
  ) : summariesQuery.isError ? (
    <div>
      <SelectedForecastHeading forecastDate={forecastDate} siteName={selectedSite.name} />
      <DashboardErrorState
        compatibilityTitle="Forecast response is incompatible"
        error={summariesQuery.error}
        onRetry={() => void summariesQuery.refetch()}
        retryLabel="Retry selected forecast"
        requestTitle="Forecast request failed"
      />
    </div>
  ) : (
    <ForecastOverview
      forecastDate={forecastDate}
      siteName={selectedSite.name}
      summary={selectedSummary}
    />
  );

  const otherLocations = summariesQuery.isPending ? (
    <ContentState
      message="The configured comparison locations are loading."
      title="Loading other locations…"
      variant="loading"
    />
  ) : summariesQuery.isError ? (
    <ContentState
      message={
        summaryError?.category === "api-compatibility"
          ? "The shared forecast response could not be used. Diagnostic details are shown in the selected forecast region."
          : "Other-location summaries are unavailable until the shared request succeeds. Use the selected forecast retry to request both regions again."
      }
      title={
        summaryError?.category === "api-compatibility"
          ? "Comparison response is incompatible"
          : "Comparison unavailable"
      }
      variant="info"
    />
  ) : (
    <OtherLocationsSection
      forecastDate={forecastDate}
      sites={otherLocationSites}
      summariesBySlug={summariesBySlug}
    />
  );

  return (
    <DashboardShell
      announcement={`Selected ${selectedSite.name} for ${forecastDate}.`}
      forecastDates={datesContent}
      locationSelector={locationSelector}
      otherBusy={summariesQuery.isPending}
      otherLocations={otherLocations}
      overview={overview}
      overviewBusy={summariesQuery.isPending}
    />
  );
};

interface ResolvedDashboardProps {
  readonly dashboardApi: DashboardApi;
  readonly searchSelection: DashboardSearchSelection;
  readonly selectedSite: Site;
  readonly sites: readonly Site[];
}

const selectAvailableDate = (
  selection: DashboardSearchSelection,
  response: ForecastDaysResponse,
): ForecastDate | undefined => {
  const available = response.days.filter((day) => day.availability === "available");
  const requested = selection.date.kind === "valid" ? selection.date.value : undefined;
  return (
    available.find((day) => day.forecastDate === requested)?.forecastDate ??
    available.find((day) => day.forecastDate >= response.todayDate)?.forecastDate ??
    available.at(-1)?.forecastDate
  );
};

const ResolvedDashboard = ({
  dashboardApi,
  searchSelection,
  selectedSite,
  sites,
}: ResolvedDashboardProps) => {
  const [searchParameters, setSearchParameters] = useSearchParams();
  const queryOptions = useMemo(() => createDashboardQueryOptions(dashboardApi), [dashboardApi]);
  const forecastDaysQuery = useQuery({
    ...queryOptions.forecastDays(selectedSite.slug),
    ...dashboardRefreshPolicy,
  });
  const dates = forecastDaysQuery.isSuccess ? forecastDaysQuery.data : undefined;
  const selectedDate =
    dates === undefined ? undefined : selectAvailableDate(searchSelection, dates);
  const canonicalSummarySiteSlugs = useMemo(
    () => createCanonicalSummarySiteSlugs(sites, selectedSite),
    [selectedSite, sites],
  );
  const otherLocationSites = useMemo(() => selectOtherLocationSites(sites), [sites]);

  useEffect(() => {
    if (dates === undefined) {
      return;
    }
    const canonicalSearch = createCanonicalDashboardSearch(selectedSite.slug, selectedDate);

    if (!dashboardSearchesMatch(searchParameters, canonicalSearch)) {
      setSearchParameters(canonicalSearch, { replace: true });
    }
  }, [dates, searchParameters, selectedDate, selectedSite.slug, setSearchParameters]);

  const selectSite = useCallback(
    (siteSlug: SiteSlug) => {
      if (siteSlug === selectedSite.slug) {
        return;
      }

      const nextSite = sites.find((site) => site.slug === siteSlug);

      if (nextSite !== undefined) {
        setSearchParameters(createCanonicalDashboardSearch(nextSite.slug, selectedDate));
      }
    },
    [selectedDate, selectedSite.slug, setSearchParameters, sites],
  );

  const selectDate = useCallback(
    (date: ForecastDate) => {
      if (
        date !== selectedDate &&
        dates?.days.some((day) => day.forecastDate === date && day.availability === "available")
      ) {
        setSearchParameters(createCanonicalDashboardSearch(selectedSite.slug, date));
      }
    },
    [dates, selectedDate, selectedSite.slug, setSearchParameters],
  );

  const locationSelector = (
    <SiteSelectorSection onSelectSite={selectSite} selectedSite={selectedSite} sites={sites} />
  );
  const datesContent = forecastDaysQuery.isPending ? (
    <ContentState
      message="The selected location's five Sofia calendar dates are loading."
      title="Loading forecast dates…"
      variant="loading"
    />
  ) : forecastDaysQuery.isError ? (
    <DashboardErrorState
      compatibilityTitle="Forecast dates response is incompatible"
      error={forecastDaysQuery.error}
      onRetry={() => void forecastDaysQuery.refetch()}
      retryLabel="Retry forecast dates"
      requestTitle="Forecast dates failed"
    />
  ) : (
    <ForecastDateStrip
      days={forecastDaysQuery.data.days}
      onSelectDate={selectDate}
      selectedDate={selectedDate}
      todayDate={forecastDaysQuery.data.todayDate}
    />
  );

  if (selectedDate === undefined) {
    const allDatesMissing = dates !== undefined;
    return (
      <DashboardShell
        announcement={`Selected ${selectedSite.name}.`}
        datesBusy={forecastDaysQuery.isPending}
        forecastDates={datesContent}
        locationSelector={locationSelector}
        otherLocations={
          <ContentState
            message="Comparison forecasts require an available date."
            title="Waiting for a date"
            variant="info"
          />
        }
        overview={
          allDatesMissing ? (
            <ContentState
              message={`No published forecast for ${selectedSite.name} in this five-day window.`}
              title="Forecast unavailable"
              variant="empty"
            />
          ) : (
            <ContentState
              message="Forecasts load after the location's dates."
              title="Waiting for forecast dates"
              variant={forecastDaysQuery.isError ? "info" : "loading"}
            />
          )
        }
        overviewBusy={forecastDaysQuery.isPending}
      />
    );
  }

  return (
    <SummaryDashboard
      canonicalSummarySiteSlugs={canonicalSummarySiteSlugs}
      dashboardApi={dashboardApi}
      datesContent={datesContent}
      forecastDate={selectedDate}
      locationSelector={locationSelector}
      otherLocationSites={otherLocationSites}
      selectedSite={selectedSite}
    />
  );
};

const waitingForSites = (message: string) => (
  <ContentState message={message} title="Waiting for locations" variant="info" />
);

export const DashboardRoute = ({ dashboardApi }: DashboardRouteProps) => {
  const [searchParameters] = useSearchParams();
  const queryOptions = useMemo(() => createDashboardQueryOptions(dashboardApi), [dashboardApi]);
  const sitesQuery = useQuery({ ...queryOptions.sites(), ...dashboardRefreshPolicy });
  const searchSelection = useMemo(() => parseDashboardSearch(searchParameters), [searchParameters]);
  const selectedSite = useMemo(
    () => resolveSelectedSite(searchSelection, sitesQuery.data?.sites ?? []),
    [searchSelection, sitesQuery.data?.sites],
  );

  if (sitesQuery.isPending) {
    return (
      <DashboardShell
        announcement="Loading available forecast locations."
        forecastDates={waitingForSites("Forecast dates load after a location is selected.")}
        locationBusy
        locationSelector={
          <ContentState
            message="The dashboard is validating the available site catalog."
            title="Loading available locations…"
            variant="loading"
          />
        }
        otherLocations={waitingForSites("Comparison locations load with the catalog.")}
        overview={waitingForSites("The forecast overview loads after a location is selected.")}
      />
    );
  }

  if (sitesQuery.isError) {
    return (
      <DashboardShell
        announcement="The forecast location catalog could not be loaded."
        forecastDates={waitingForSites("Forecast dates require the location catalog.")}
        locationSelector={
          <DashboardErrorState
            compatibilityTitle="Locations response is incompatible"
            error={sitesQuery.error}
            onRetry={() => void sitesQuery.refetch()}
            retryLabel="Retry locations"
            requestTitle="Locations request failed"
          />
        }
        otherLocations={waitingForSites("Comparison locations require the catalog.")}
        overview={waitingForSites("The forecast overview requires a known location.")}
      />
    );
  }

  if (sitesQuery.data.sites.length === 0 || selectedSite === undefined) {
    return (
      <DashboardShell
        announcement="The site catalog is empty."
        forecastDates={waitingForSites("Forecast dates require a configured location.")}
        locationSelector={
          <ContentState
            message="No forecast locations are configured."
            title="No locations available"
            variant="empty"
          />
        }
        otherLocations={waitingForSites("There are no comparison locations to show.")}
        overview={waitingForSites("There is no location forecast to show.")}
      />
    );
  }

  return (
    <ResolvedDashboard
      dashboardApi={dashboardApi}
      searchSelection={searchSelection}
      selectedSite={selectedSite}
      sites={sitesQuery.data.sites}
    />
  );
};
