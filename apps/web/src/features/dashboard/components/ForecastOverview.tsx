import type { ForecastDate, ForecastSummary } from "@paragliding-forecasts/contracts";
import { Link } from "react-router-dom";

import { ContentState } from "../../../components/content-state/ContentState.js";
import {
  formatForecastDateLong,
  formatGeneratedAt,
  formatInteger,
  formatRisk,
  summarizeConfidence,
  summarizeDataStatus,
} from "../forecast-presentation.js";
import { ConfidenceIndicator } from "./ConfidenceIndicator.js";
import { DataStatusBadge } from "./DataStatusBadge.js";
import { ForecastMetric } from "./ForecastMetric.js";
import {
  CloudbaseIcon,
  DistanceFlagIcon,
  OpportunityIcon,
  OverdevelopmentIcon,
  RouteIcon,
} from "./ForecastIcons.js";
import styles from "./ForecastOverview.module.scss";
import { createForecastDetailPath } from "../../forecast-details/forecast-detail-navigation.js";

const InformationIcon = () => (
  <svg aria-hidden="true" focusable="false" viewBox="0 0 24 24">
    <circle cx="12" cy="12" r="9" />
    <path d="M12 11v6m0-10h.01" />
  </svg>
);

const ArrowIcon = () => (
  <svg aria-hidden="true" focusable="false" viewBox="0 0 24 24">
    <path d="M5 12h14m-6-6 6 6-6 6" />
  </svg>
);

export interface SelectedForecastHeadingProps {
  readonly forecastDate: ForecastDate;
  readonly siteName: string;
  readonly status?: ReturnType<typeof summarizeDataStatus>;
}

export const SelectedForecastHeading = ({
  forecastDate,
  siteName,
  status,
}: SelectedForecastHeadingProps) => (
  <div className={styles.headingRow}>
    <h1 className={styles.heading}>
      {siteName} · {formatForecastDateLong(forecastDate)}
    </h1>
    {status === undefined ? null : <DataStatusBadge status={status} />}
  </div>
);

interface AvailableOverviewProps {
  readonly forecastDate: ForecastDate;
  readonly siteName: string;
  readonly summary: Extract<ForecastSummary, { readonly availability: "available" }>;
}

const AvailableOverview = ({ forecastDate, siteName, summary }: AvailableOverviewProps) => {
  const { outputs } = summary;
  const status = summarizeDataStatus(outputs);
  const confidence = summarizeConfidence(outputs);
  const showMetricStatus = status === "mixed";
  const allMetricsMissing = status === "missing";

  return (
    <div>
      <SelectedForecastHeading forecastDate={forecastDate} siteName={siteName} status={status} />
      {allMetricsMissing ? (
        <p className={styles.unavailableNotice}>All forecast metrics are unavailable.</p>
      ) : null}
      <ul aria-label="Forecast metrics" className={styles.metrics}>
        <ForecastMetric
          icon={<OpportunityIcon />}
          label="100+ km chance"
          metric={outputs.chance100KmPct}
          primary
          showStatus={showMetricStatus}
          unit="%"
          value={
            outputs.chance100KmPct.dataStatus === "missing"
              ? null
              : formatInteger(outputs.chance100KmPct.value)
          }
        />
        <ForecastMetric
          icon={<CloudbaseIcon />}
          label="Cloudbase"
          metric={outputs.cloudbaseMslM}
          showStatus={showMetricStatus}
          unit="m MSL"
          value={
            outputs.cloudbaseMslM.dataStatus === "missing"
              ? null
              : formatInteger(outputs.cloudbaseMslM.value)
          }
        />
        <ForecastMetric
          icon={<RouteIcon />}
          label="200+ km chance"
          metric={outputs.chance200KmPct}
          showStatus={showMetricStatus}
          unit="%"
          value={
            outputs.chance200KmPct.dataStatus === "missing"
              ? null
              : formatInteger(outputs.chance200KmPct.value)
          }
        />
        <ForecastMetric
          icon={<DistanceFlagIcon />}
          label="300+ km chance"
          metric={outputs.chance300KmPct}
          showStatus={showMetricStatus}
          unit="%"
          value={
            outputs.chance300KmPct.dataStatus === "missing"
              ? null
              : formatInteger(outputs.chance300KmPct.value)
          }
        />
        <ForecastMetric
          icon={<OverdevelopmentIcon />}
          label="OD risk"
          metric={outputs.overdevelopmentRisk}
          showStatus={showMetricStatus}
          value={
            outputs.overdevelopmentRisk.dataStatus === "missing"
              ? null
              : formatRisk(outputs.overdevelopmentRisk.value)
          }
        />
      </ul>
      <div className={styles.footer}>
        <ConfidenceIndicator confidence={confidence} label="Model confidence" />
        <p className={styles.metadata}>
          <span>{summary.provenance.version}</span>
          <span>generated {formatGeneratedAt(summary.generatedAt)}</span>
          <span
            className={styles.provenanceDetails}
            title={`Source: ${summary.provenance.source}. ${confidence.notes.join(" ")}`}
          >
            <InformationIcon />
            <span className="visually-hidden">source {summary.provenance.source}</span>
          </span>
        </p>
      </div>
      <Link
        aria-label="View detailed forecast"
        className={styles.detailAction}
        to={createForecastDetailPath(summary.siteSlug, forecastDate)}
      >
        <span>View detailed forecast</span>
        <ArrowIcon />
      </Link>
    </div>
  );
};

export interface ForecastOverviewProps {
  readonly forecastDate: ForecastDate;
  readonly siteName: string;
  readonly summary: ForecastSummary | undefined;
}

export const ForecastOverview = ({ forecastDate, siteName, summary }: ForecastOverviewProps) => {
  if (summary === undefined) {
    return (
      <div>
        <SelectedForecastHeading forecastDate={forecastDate} siteName={siteName} />
        <ContentState
          message="The service response omitted the selected location. No values were inferred."
          title="No summary was returned for the selected location."
          variant="info"
        />
      </div>
    );
  }

  if (summary.availability === "missing") {
    return (
      <div>
        <SelectedForecastHeading forecastDate={forecastDate} siteName={siteName} status="missing" />
        <ContentState
          message={summary.missingReason}
          title="Forecast unavailable"
          variant="empty"
        />
      </div>
    );
  }

  return <AvailableOverview forecastDate={forecastDate} siteName={siteName} summary={summary} />;
};
