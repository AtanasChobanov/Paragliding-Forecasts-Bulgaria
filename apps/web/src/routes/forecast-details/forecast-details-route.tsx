import { CloudbaseChart } from "../../features/forecast-details/components/CloudbaseChart.js";
import type {
  ForecastDate,
  ForecastDaysResponse,
  ForecastResponse,
  Site,
} from "@paragliding-forecasts/contracts";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { ContentState } from "../../components/content-state/ContentState.js";
import { DashboardErrorState } from "../../features/dashboard/components/DashboardErrorState.js";
import { AccessibleSiteSelector } from "../../features/dashboard/components/AccessibleSiteSelector.js";
import {
  createDashboardQueryOptions,
  dashboardRefreshPolicy,
} from "../../features/dashboard/dashboard-query-options.js";
import {
  createCanonicalDashboardSearch,
  dashboardSearchesMatch,
  parseDashboardSearch,
  resolveSelectedSite,
} from "../../features/dashboard/dashboard-search-params.js";
import { ApiHttpError } from "../../services/api/api-errors.js";
import type { DashboardApi } from "../../services/api/dashboard-api.js";
import { ForecastDateSelector } from "../../features/forecast-details/components/ForecastDateSelector.js";
import {
  ForecastDetailSummary,
  ForecastInputsPanel,
  TopDriversPanel,
} from "../../features/forecast-details/components/ForecastDetailContent.js";
import { defaultCloudbaseHour } from "../../features/forecast-details/forecast-detail-presentation.js";
import { createDashboardPath } from "../../features/forecast-details/forecast-detail-navigation.js";
import { createForecastDetailQueryOptions } from "../../features/forecast-details/forecast-detail-query-options.js";
import styles from "./forecast-details-route.module.scss";

export interface ForecastDetailsRouteProps {
  readonly dashboardApi: DashboardApi;
}

export const resolveDetailDate = (
  requested: ForecastDate | undefined,
  days: ForecastDaysResponse | undefined,
) => {
  if (requested) return requested;
  const available = days?.days.filter((day) => day.availability === "available") ?? [];
  return (
    available.find((day) => day.forecastDate === days?.todayDate)?.forecastDate ??
    available.find((day) => day.forecastDate > (days?.todayDate ?? ""))?.forecastDate ??
    available.at(-1)?.forecastDate
  );
};

const ForecastLoaded = ({
  forecast,
  siteName,
}: {
  readonly forecast: ForecastResponse;
  readonly siteName: string;
}) => {
  const [selectedHour, setSelectedHour] = useState(() => defaultCloudbaseHour(forecast));
  return (
    <>
      <div className={styles.primaryGrid}>
        <ForecastDetailSummary forecast={forecast} siteName={siteName} />
        <div className={styles.sideGrid}>
          <ForecastInputsPanel
            forecast={forecast}
            selectedHour={selectedHour}
            onSelectHour={setSelectedHour}
          />
          <TopDriversPanel forecast={forecast} />
        </div>
      </div>
      <div className={styles.chartRegion}>
        <CloudbaseChart
          forecast={forecast}
          selectedHour={selectedHour}
          onSelectHour={setSelectedHour}
        />
      </div>
    </>
  );
};

const ForecastDetailBody = ({
  dashboardApi,
  forecastDate,
  selectedSite,
}: {
  readonly dashboardApi: DashboardApi;
  readonly forecastDate: ForecastDate;
  readonly selectedSite: Site;
}) => {
  const detailQuery = useQuery(
    createForecastDetailQueryOptions(dashboardApi, selectedSite.slug, forecastDate),
  );
  if (detailQuery.isPending)
    return (
      <ContentState
        title="Loading forecast…"
        message="The selected detailed forecast is loading."
        variant="loading"
      />
    );
  if (detailQuery.isError)
    return detailQuery.error instanceof ApiHttpError &&
      detailQuery.error.code === "FORECAST_NOT_FOUND" ? (
      <ContentState
        title="Forecast unavailable"
        message={detailQuery.error.message}
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
    );
  return (
    <ForecastLoaded
      key={`${selectedSite.slug}-${forecastDate}`}
      forecast={detailQuery.data}
      siteName={selectedSite.name}
    />
  );
};

export const ForecastDetailsRoute = ({ dashboardApi }: ForecastDetailsRouteProps) => {
  const [searchParameters, setSearchParameters] = useSearchParams();
  const queryOptions = useMemo(() => createDashboardQueryOptions(dashboardApi), [dashboardApi]);
  const sitesQuery = useQuery({ ...queryOptions.sites(), ...dashboardRefreshPolicy });
  const selection = useMemo(() => parseDashboardSearch(searchParameters), [searchParameters]);
  const selectedSite = resolveSelectedSite(selection, sitesQuery.data?.sites ?? []);
  const daysQuery = useQuery({
    ...queryOptions.forecastDays(selectedSite?.slug ?? "invalid-site"),
    ...dashboardRefreshPolicy,
    enabled: selectedSite !== undefined,
  });
  const selectedDate = resolveDetailDate(
    selection.date.kind === "valid" ? selection.date.value : undefined,
    daysQuery.data,
  );
  useEffect(() => {
    if (!selectedSite || !selectedDate) return;
    const canonical = createCanonicalDashboardSearch(selectedSite.slug, selectedDate);
    if (!dashboardSearchesMatch(searchParameters, canonical))
      setSearchParameters(canonical, { replace: true });
  }, [searchParameters, selectedDate, selectedSite, setSearchParameters]);

  return (
    <main aria-label="Detailed forecast" className={styles.main} data-detail>
      <nav aria-label="Detailed forecast controls" className={styles.toolbar}>
        <Link
          className={styles.backLink}
          to={
            selectedSite
              ? createDashboardPath(
                  selectedSite.slug,
                  selectedDate ?? daysQuery.data?.todayDate ?? "",
                )
              : "/"
          }
        >
          <span aria-hidden="true">←</span> All sites
        </Link>
        {selectedSite && sitesQuery.data ? (
          <AccessibleSiteSelector
            selectedSite={selectedSite}
            sites={sitesQuery.data.sites}
            onSelectSite={(slug) => {
              setSearchParameters(createCanonicalDashboardSearch(slug, selectedDate));
            }}
          />
        ) : null}
        {selectedDate && daysQuery.data ? (
          <ForecastDateSelector
            selectedDate={selectedDate}
            days={daysQuery.data.days}
            onSelectDate={(date) => {
              if (selectedSite)
                setSearchParameters(createCanonicalDashboardSearch(selectedSite.slug, date));
            }}
          />
        ) : null}
      </nav>
      {sitesQuery.isError ? (
        <DashboardErrorState
          compatibilityTitle="Locations response is incompatible"
          error={sitesQuery.error}
          onRetry={() => void sitesQuery.refetch()}
          requestTitle="Locations request failed"
          retryLabel="Retry locations"
        />
      ) : sitesQuery.isPending ? (
        <ContentState
          title="Loading locations…"
          message="Loading forecast locations."
          variant="loading"
        />
      ) : !selectedSite ? (
        <ContentState
          title="No location available"
          message="A detailed forecast needs an available forecast location."
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
      ) : daysQuery.isPending && !selectedDate ? (
        <ContentState
          title="Loading dates…"
          message="The location’s forecast dates are loading."
          variant="loading"
        />
      ) : !selectedDate ? (
        <ContentState
          title="Forecast unavailable"
          message="No published forecasts are available in this date window."
          variant="empty"
        />
      ) : (
        <ForecastDetailBody
          dashboardApi={dashboardApi}
          forecastDate={selectedDate}
          selectedSite={selectedSite}
        />
      )}
      <p className="visually-hidden" aria-live="polite">
        {selectedSite
          ? `Selected ${selectedSite.name} for ${selectedDate ?? "no available date"}.`
          : "Loading locations."}
      </p>
    </main>
  );
};
