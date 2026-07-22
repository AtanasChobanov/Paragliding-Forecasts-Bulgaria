import type { ForecastSummary, Site } from "@paragliding-forecasts/contracts";

import {
  formatInteger,
  formatRisk,
  summarizeConfidence,
  summarizeDataStatus,
} from "../forecast-presentation.js";
import { ConfidenceIndicator } from "./ConfidenceIndicator.js";
import { DataStatusBadge } from "./DataStatusBadge.js";
import styles from "./LocationSummaryCard.module.scss";

export interface LocationSummaryCardProps {
  readonly site: Site;
  readonly summary: ForecastSummary | undefined;
}

const PinIcon = () => (
  <svg aria-hidden="true" viewBox="0 0 24 24">
    <path d="M12 22s7-6.1 7-13A7 7 0 0 0 5 9c0 6.9 7 13 7 13Z" />
    <circle cx="12" cy="9" r="2.5" />
  </svg>
);

const CloudIcon = () => (
  <svg aria-hidden="true" viewBox="0 0 24 24">
    <path d="M7.5 18.5h9.3a4.2 4.2 0 0 0 .5-8.4A6 6 0 0 0 6 9a4.8 4.8 0 0 0 1.5 9.5Z" />
  </svg>
);

const ShieldIcon = () => (
  <svg aria-hidden="true" viewBox="0 0 24 24">
    <path d="M12 3 19 6v5c0 4.7-2.8 8.3-7 10-4.2-1.7-7-5.3-7-10V6l7-3Z" />
    <path d="M12 8v6m-2-2 2 2 2-2" />
  </svg>
);

const UnavailableMetric = ({ reason }: { readonly reason: string }) => (
  <span className={styles.unavailable} title={reason}>
    Unavailable
  </span>
);

export const LocationSummaryCard = ({ site, summary }: LocationSummaryCardProps) => {
  const headingId = `other-location-${site.slug}`;

  if (summary === undefined) {
    return (
      <article aria-labelledby={headingId} className={styles.card}>
        <h3 id={headingId}>
          <PinIcon />
          {site.name}
        </h3>
        <div className={styles.missingSummary}>
          <DataStatusBadge compact status="missing" />
          <strong>No summary returned</strong>
          <p>The service response omitted this comparison location.</p>
        </div>
      </article>
    );
  }

  if (summary.availability === "missing") {
    return (
      <article aria-labelledby={headingId} className={styles.card}>
        <h3 id={headingId}>
          <PinIcon />
          {site.name}
        </h3>
        <div className={styles.missingSummary}>
          <DataStatusBadge compact status="missing" />
          <strong>Forecast unavailable</strong>
          <p>{summary.missingReason}</p>
        </div>
      </article>
    );
  }

  const { outputs } = summary;
  const summaryStatus = summarizeDataStatus(outputs);
  const confidence = summarizeConfidence(outputs);
  const showMetricStatus = summaryStatus === "mixed";
  const chance100 = outputs.chance100KmPct;
  const cloudbase = outputs.cloudbaseMslM;
  const risk = outputs.overdevelopmentRisk;

  return (
    <article aria-labelledby={headingId} className={styles.card}>
      <div className={styles.cardHeader}>
        <h3 id={headingId}>
          <PinIcon />
          {site.name}
        </h3>
        <DataStatusBadge compact status={summaryStatus} />
      </div>
      <div className={styles.primaryMetric}>
        {chance100.dataStatus === "missing" ? (
          <UnavailableMetric reason={chance100.missingReason} />
        ) : (
          <>
            <strong>{formatInteger(chance100.value)}%</strong>
            <div
              aria-label={`${String(chance100.value)} percent chance of 100 kilometres or more`}
              aria-valuemax={100}
              aria-valuemin={0}
              aria-valuenow={chance100.value}
              className={styles.progress}
              role="progressbar"
            >
              <span style={{ width: `${String(chance100.value)}%` }} />
            </div>
          </>
        )}
        <span>100+ km chance</span>
        {chance100.dataStatus === "missing" ? (
          <p>{chance100.missingReason}</p>
        ) : showMetricStatus ? (
          <DataStatusBadge compact status={chance100.dataStatus} />
        ) : null}
      </div>
      <dl className={styles.secondaryMetrics}>
        <div>
          <dt>
            <CloudIcon /> Cloudbase
          </dt>
          <dd>
            {cloudbase.dataStatus === "missing" ? (
              <UnavailableMetric reason={cloudbase.missingReason} />
            ) : (
              `${formatInteger(cloudbase.value)} m MSL`
            )}
          </dd>
          {showMetricStatus ? <DataStatusBadge compact status={cloudbase.dataStatus} /> : null}
        </div>
        <div>
          <dt>
            <ShieldIcon /> OD risk
          </dt>
          <dd>
            {risk.dataStatus === "missing" ? (
              <UnavailableMetric reason={risk.missingReason} />
            ) : (
              formatRisk(risk.value)
            )}
          </dd>
          {showMetricStatus ? <DataStatusBadge compact status={risk.dataStatus} /> : null}
        </div>
      </dl>
      <div className={styles.confidence}>
        <ConfidenceIndicator compact confidence={confidence} />
      </div>
    </article>
  );
};
