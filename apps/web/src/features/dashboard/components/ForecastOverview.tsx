import type { ForecastDate, ForecastSummary } from "@paragliding-forecasts/contracts";

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
import styles from "./ForecastOverview.module.scss";

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

const OpportunityIcon = () => (
  <svg viewBox="0 0 24 24">
    <path d="m4 17 5-5 4 3 7-8" />
    <path d="M15 7h5v5" />
  </svg>
);

const CloudbaseIcon = () => (
  <svg viewBox="0 0 24 24">
    <path d="M6.5 17.5h10a4 4 0 0 0 .5-8 5.5 5.5 0 0 0-10.4-1A4.5 4.5 0 0 0 6.5 17.5Z" />
    <path d="M12 15V7m-3 3 3-3 3 3" />
  </svg>
);

const RouteIcon = () => (
  <svg viewBox="0 0 24 24">
    <circle cx="6" cy="17" r="2" />
    <circle cx="18" cy="7" r="2" />
    <path d="M8 17c5 0 3-10 8-10" />
  </svg>
);

const DistanceFlagIcon = () => (
  <svg viewBox="0 0 24 24">
    <path d="M6 21V4m0 1h10l-2 3 2 3H6" />
    <path d="M4 21h5" />
  </svg>
);

const OverdevelopmentIcon = () => (
  <svg viewBox="0 0 24 24">
    <path d="M6.5 15.5h10a4 4 0 0 0 .5-8 5.5 5.5 0 0 0-10.4-1A4.5 4.5 0 0 0 6.5 15.5Z" />
    <path d="m13 14-3 5h3l-1 3 4-6h-3l1-2" />
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
    <h3 className={styles.heading}>
      {siteName} · {formatForecastDateLong(forecastDate)}
    </h3>
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
        <ConfidenceIndicator confidence={confidence} />
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
      <button
        aria-label="View detailed forecast"
        className={styles.detailAction}
        disabled
        title="The detailed forecast view is not available yet."
        type="button"
      >
        <span>View detailed forecast</span>
        <ArrowIcon />
      </button>
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
