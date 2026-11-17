import type {
  AvailableForecastSummary,
  ForecastDate,
  ForecastSummary,
} from "@paragliding-forecasts/contracts";
import { Link } from "react-router-dom";

import { ContentState } from "../../../components/content-state/ContentState.js";
import { createForecastDetailPath } from "../../forecast-details/forecast-detail-navigation.js";
import {
  formatChancePercent,
  formatForecastDateLong,
  formatRisk,
  p100Confidence,
  presentCloudbase,
} from "../forecast-presentation.js";
import { ConfidenceIndicator } from "./ConfidenceIndicator.js";
import {
  CloudbaseIcon,
  DistanceFlagIcon,
  OpportunityIcon,
  OverdevelopmentIcon,
  RouteIcon,
} from "./ForecastIcons.js";
import { ForecastInformation } from "./ForecastInformation.js";
import { ForecastMetric, type ForecastMetricProps } from "./ForecastMetric.js";
import styles from "./ForecastOverview.module.scss";

const ArrowIcon = () => (
  <svg aria-hidden="true" focusable="false" viewBox="0 0 24 24">
    <path d="M5 12h14m-6-6 6 6-6 6" />
  </svg>
);

export interface SelectedForecastHeadingProps {
  readonly forecastDate: ForecastDate;
  readonly siteName: string;
}

export const SelectedForecastHeading = ({
  forecastDate,
  siteName,
}: SelectedForecastHeadingProps) => (
  <div className={styles.headingRow}>
    <h1 className={styles.heading}>
      {siteName} · {formatForecastDateLong(forecastDate)}
    </h1>
  </div>
);

interface AvailableOverviewProps {
  readonly forecastDate: ForecastDate;
  readonly siteName: string;
  readonly summary: AvailableForecastSummary;
}

const AvailableOverview = ({ forecastDate, siteName, summary }: AvailableOverviewProps) => {
  const { outputs } = summary;
  const chance = (
    label: string,
    metric: typeof outputs.chance100KmPct,
    icon: ForecastMetricProps["icon"],
  ): ForecastMetricProps => ({
    label,
    icon,
    dataStatus: metric.dataStatus,
    missingReason: metric.dataStatus === "missing" ? metric.missingReason : undefined,
    value: metric.value === null ? "Unavailable" : formatChancePercent(metric.value),
  });
  const risk = outputs.overdevelopmentRisk;
  const metrics: ForecastMetricProps[] = [
    { ...chance("100+ km chance", outputs.chance100KmPct, <OpportunityIcon />), primary: true },
    {
      icon: <CloudbaseIcon />,
      dataStatus: outputs.cloudbase.dataStatus,
      ...presentCloudbase(outputs.cloudbase),
      missingReason:
        outputs.cloudbase.kind === "missing" ? outputs.cloudbase.missingReason : undefined,
    },
    chance("200+ km chance", outputs.chance200KmPct, <RouteIcon />),
    chance("300+ km chance", outputs.chance300KmPct, <DistanceFlagIcon />),
    {
      icon: <OverdevelopmentIcon />,
      label: "OD risk",
      dataStatus: risk.dataStatus,
      missingReason: risk.dataStatus === "missing" ? risk.missingReason : undefined,
      value: risk.value === null ? "Unavailable" : formatRisk(risk.value),
    },
  ];

  return (
    <div>
      <SelectedForecastHeading forecastDate={forecastDate} siteName={siteName} />
      <ul aria-label="Forecast metrics" className={styles.metrics}>
        {metrics.map((metric) => (
          <ForecastMetric key={metric.label} {...metric} />
        ))}
      </ul>
      <div className={styles.footer} data-forecast-footer>
        <ConfidenceIndicator
          accessibleLabel="100+ km confidence"
          confidence={p100Confidence(outputs.chance100KmPct)}
          label="Model confidence"
          showNote={false}
        />
        <ForecastInformation
          key={`${String(summary.siteId)}:${forecastDate}`}
          siteName={siteName}
          summary={summary}
        />
      </div>
      {summary.metadata.mode === "mock" ? (
        <Link
          className={styles.detailAction}
          to={createForecastDetailPath(summary.siteSlug, forecastDate)}
        >
          <span>View detailed forecast</span>
          <ArrowIcon />
        </Link>
      ) : (
        <div className={styles.detailUnavailable}>
          <button
            aria-describedby="sqlite-detail-reason"
            className={styles.detailAction}
            disabled
            type="button"
          >
            View detailed forecast
          </button>
          <small id="sqlite-detail-reason">Forecast details are unavailable in SQLite mode.</small>
        </div>
      )}
    </div>
  );
};

export interface ForecastOverviewProps {
  readonly forecastDate: ForecastDate;
  readonly siteName: string;
  readonly summary: ForecastSummary | undefined;
}

export const ForecastOverview = ({ forecastDate, siteName, summary }: ForecastOverviewProps) => {
  if (summary?.availability === "available") {
    return <AvailableOverview forecastDate={forecastDate} siteName={siteName} summary={summary} />;
  }

  return (
    <div>
      <SelectedForecastHeading forecastDate={forecastDate} siteName={siteName} />
      <ContentState
        message={summary?.missingReason ?? "The service response omitted the selected location."}
        title={
          summary === undefined
            ? "No summary was returned for the selected location."
            : "Forecast unavailable"
        }
        variant={summary === undefined ? "info" : "empty"}
      />
    </div>
  );
};
