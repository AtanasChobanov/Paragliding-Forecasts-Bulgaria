import type { ForecastDate, Site, SiteSlug } from "@paragliding-forecasts/contracts";
import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { ContentState } from "../../components/content-state/ContentState.js";
import { DashboardErrorState } from "../../features/dashboard/components/DashboardErrorState.js";
import { AccessibleSiteSelector } from "../../features/dashboard/components/AccessibleSiteSelector.js";
import { SiteSelectorSection } from "../../features/dashboard/components/SiteSelectorSection.js";
import { createDashboardQueryOptions } from "../../features/dashboard/dashboard-query-options.js";
import {
  createCanonicalDashboardSearch,
  dashboardSearchesMatch,
  parseDashboardSearch,
  resolveSelectedDate,
  resolveSelectedSite,
} from "../../features/dashboard/dashboard-search-params.js";
import { ApiHttpError } from "../../services/api/api-errors.js";
import type { DashboardApi } from "../../services/api/dashboard-api.js";
import { ForecastDateSelector } from "../../features/forecast-details/components/ForecastDateSelector.js";
import {
  ForecastDetailSummary,
  ForecastInputsPanel,
  PreviousRunComparison,
  TopDriversPanel,
} from "../../features/forecast-details/components/ForecastDetailContent.js";
import { createDashboardPath } from "../../features/forecast-details/forecast-detail-navigation.js";
import { createForecastDetailQueryOptions } from "../../features/forecast-details/forecast-detail-query-options.js";
import styles from "./forecast-details-route.module.scss";

export interface ForecastDetailsRouteProps {
  readonly dashboardApi: DashboardApi;
}

const BackIcon = () => (
  <svg aria-hidden="true" focusable="false" viewBox="0 0 24 24">
    <path d="M19 12H5m6-6-6 6 6 6" />
  </svg>
);

interface ForecastDetailBodyProps {
  readonly dashboardApi: DashboardApi;
  readonly forecastDate: ForecastDate;
  readonly selectedSite: Site;
  readonly sites: readonly Site[];
}

const ForecastDetailBody = ({
  dashboardApi,
  forecastDate,
  selectedSite,
  sites,
}: ForecastDetailBodyProps) => {
  const [, setSearchParameters] = useSearchParams();
  const detailQuery = useQuery(
    createForecastDetailQueryOptions(dashboardApi, selectedSite.slug, forecastDate),
  );
  const selectSite = useCallback(
    (siteSlug: SiteSlug) => {
      if (siteSlug !== selectedSite.slug) {
        setSearchParameters(createCanonicalDashboardSearch(siteSlug, forecastDate));
      }
    },
    [forecastDate, selectedSite.slug, setSearchParameters],
  );

  const forecastContent = detailQuery.isPending ? (
    <ContentState
      message="The selected detailed forecast is loading."
      title="Loading forecast…"
      variant="loading"
    />
  ) : detailQuery.isError ? (
    detailQuery.error instanceof ApiHttpError && detailQuery.error.code === "FORECAST_NOT_FOUND" ? (
      <ContentState
        message={detailQuery.error.message}
        title="Forecast unavailable"
        variant="empty"
      />
    ) : (
      <DashboardErrorState
        compatibilityTitle="Detailed forecast response is incompatible"
        error={detailQuery.error}
        onRetry={() => void detailQuery.refetch()}
        requestTitle="Detailed forecast request failed"
        retryLabel="Retry detailed forecast"
      />
    )
  ) : (
    <ForecastDetailSummary forecast={detailQuery.data} siteName={selectedSite.name} />
  );

  return (
    <>
      <section className={styles.primaryGrid}>
        <div className={styles.summaryRegion}>{forecastContent}</div>
        <section aria-label="Forecast site map" className={styles.mapRegion}>
          <SiteSelectorSection
            onSelectSite={selectSite}
            selectedSite={selectedSite}
            showInstructions={false}
            showSelector={false}
            sites={sites}
            viewportMode="selected-site"
          />
        </section>
      </section>
      {detailQuery.data === undefined ? (
        <section className={styles.lowerGrid}>
          <ContentState
            message="Forecast inputs and result drivers load with the detailed forecast."
            title="Waiting for forecast details"
            variant="info"
          />
        </section>
      ) : (
        <section className={styles.lowerGrid}>
          <ForecastInputsPanel forecastInputs={detailQuery.data.forecastInputs} />
          <TopDriversPanel forecast={detailQuery.data} />
        </section>
      )}
      <PreviousRunComparison />
      <p aria-live="polite" className="visually-hidden">
        Selected {selectedSite.name} for {forecastDate}.
      </p>
    </>
  );
};

export const ForecastDetailsRoute = ({ dashboardApi }: ForecastDetailsRouteProps) => {
  const [searchParameters, setSearchParameters] = useSearchParams();
  const queryOptions = useMemo(() => createDashboardQueryOptions(dashboardApi), [dashboardApi]);
  const sitesQuery = useQuery(queryOptions.sites());
  const searchSelection = useMemo(() => parseDashboardSearch(searchParameters), [searchParameters]);
  const selectedSite = useMemo(
    () => resolveSelectedSite(searchSelection, sitesQuery.data?.sites ?? []),
    [searchSelection, sitesQuery.data?.sites],
  );
  const daysQuery = useQuery({
    ...queryOptions.forecastDays(selectedSite?.slug ?? "invalid-site"),
    enabled: selectedSite !== undefined,
  });
  const selectedDate = resolveSelectedDate(searchSelection, daysQuery.data);

  useEffect(() => {
    if (selectedSite === undefined || selectedDate === undefined) {
      return;
    }

    const canonicalSearch = createCanonicalDashboardSearch(selectedSite.slug, selectedDate);
    if (!dashboardSearchesMatch(searchParameters, canonicalSearch)) {
      setSearchParameters(canonicalSearch, { replace: true });
    }
  }, [searchParameters, selectedDate, selectedSite, setSearchParameters]);

  const selectSite = useCallback(
    (siteSlug: SiteSlug) => {
      if (selectedDate !== undefined && siteSlug !== selectedSite?.slug) {
        setSearchParameters(createCanonicalDashboardSearch(siteSlug, selectedDate));
      }
    },
    [selectedDate, selectedSite?.slug, setSearchParameters],
  );
  const selectDate = useCallback(
    (forecastDate: ForecastDate) => {
      if (selectedSite !== undefined && forecastDate !== selectedDate) {
        setSearchParameters(createCanonicalDashboardSearch(selectedSite.slug, forecastDate));
      }
    },
    [selectedDate, selectedSite, setSearchParameters],
  );

  const toolbar = (
    <nav aria-label="Detailed forecast controls" className={styles.toolbar}>
      {selectedSite !== undefined && selectedDate !== undefined ? (
        <Link className={styles.backLink} to={createDashboardPath(selectedSite.slug, selectedDate)}>
          <BackIcon />
          <span>All sites</span>
        </Link>
      ) : (
        <span className={styles.backLink}>
          <BackIcon />
          <span>All sites</span>
        </span>
      )}
      {selectedSite === undefined || sitesQuery.data === undefined ? (
        <ContentState
          message="Locations are loading."
          title="Loading locations…"
          variant="loading"
        />
      ) : (
        <AccessibleSiteSelector
          onSelectSite={selectSite}
          selectedSite={selectedSite}
          sites={sitesQuery.data.sites}
        />
      )}
      {daysQuery.data === undefined || selectedDate === undefined ? (
        <ContentState message="Dates are loading." title="Loading dates…" variant="loading" />
      ) : (
        <ForecastDateSelector
          days={daysQuery.data.days}
          onSelectDate={selectDate}
          selectedDate={selectedDate}
        />
      )}
    </nav>
  );

  return (
    <main aria-label="Detailed forecast" className={styles.main}>
      {toolbar}
      {sitesQuery.isError ? (
        <DashboardErrorState
          compatibilityTitle="Locations response is incompatible"
          error={sitesQuery.error}
          onRetry={() => void sitesQuery.refetch()}
          requestTitle="Locations request failed"
          retryLabel="Retry locations"
        />
      ) : selectedSite === undefined || sitesQuery.data === undefined ? (
        <ContentState
          message="A detailed forecast needs an available forecast location."
          title="No location available"
          variant="empty"
        />
      ) : daysQuery.isError ? (
        <DashboardErrorState
          compatibilityTitle="Forecast dates response is incompatible"
          error={daysQuery.error}
          onRetry={() => void daysQuery.refetch()}
          requestTitle="Forecast dates failed"
          retryLabel="Retry forecast dates"
        />
      ) : selectedDate === undefined ? (
        <ContentState
          message="Waiting for the selected location's valid forecast dates."
          title="Waiting for forecast date"
          variant="loading"
        />
      ) : (
        <ForecastDetailBody
          dashboardApi={dashboardApi}
          forecastDate={selectedDate}
          selectedSite={selectedSite}
          sites={sitesQuery.data.sites}
        />
      )}
    </main>
  );
};
