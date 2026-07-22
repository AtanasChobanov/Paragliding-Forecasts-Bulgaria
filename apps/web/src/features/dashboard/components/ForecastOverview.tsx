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
          <span>source {summary.provenance.source}</span>
          <span>generated {formatGeneratedAt(summary.generatedAt)} in Sofia</span>
        </p>
      </div>
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
