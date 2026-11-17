import type { ForecastDate, ForecastSummary, Site } from "@paragliding-forecasts/contracts";
import { Link } from "react-router-dom";

import { createForecastDetailPath } from "../../forecast-details/forecast-detail-navigation.js";
import {
  formatChancePercent,
  formatRisk,
  p100Confidence,
  presentCloudbase,
} from "../forecast-presentation.js";
import { ConfidenceIndicator } from "./ConfidenceIndicator.js";
import { DataStatusBadge } from "./DataStatusBadge.js";
import { ForecastChanceProgress } from "./ForecastChanceProgress.js";
import { ForecastInformation } from "./ForecastInformation.js";
import styles from "./LocationSummaryCard.module.scss";

export interface LocationSummaryCardProps {
  readonly forecastDate: ForecastDate;
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

const ChevronIcon = () => (
  <svg aria-hidden="true" className={styles.chevron} viewBox="0 0 24 24">
    <path d="m9 7 5 5-5 5" />
  </svg>
);

export const LocationSummaryCard = ({ forecastDate, site, summary }: LocationSummaryCardProps) => {
  const headingId = `other-location-${site.slug}`;
  const heading = (
    <h3 id={headingId}>
      <PinIcon />
      {site.name}
    </h3>
  );

  if (summary?.availability !== "available") {
    return (
      <article aria-labelledby={headingId} className={styles.card}>
        <div className={styles.cardHeader}>{heading}</div>
        <div className={styles.missingSummary} title={summary?.missingReason}>
          <strong>{summary === undefined ? "No summary returned" : "Forecast unavailable"}</strong>
          <span className="visually-hidden">{summary?.missingReason}</span>
        </div>
      </article>
    );
  }

  const { chance100KmPct, cloudbase, overdevelopmentRisk } = summary.outputs;
  const cloud = presentCloudbase(cloudbase);

  return (
    <article aria-labelledby={headingId} className={styles.card}>
      <div className={styles.cardHeader}>
        {heading}
        {summary.metadata.mode === "mock" ? (
          <Link
            aria-label={`View detailed forecast for ${site.name}`}
            className={styles.cardLink}
            to={createForecastDetailPath(site.slug, forecastDate)}
          >
            <ChevronIcon />
          </Link>
        ) : null}
        <ForecastInformation key={forecastDate} siteName={site.name} summary={summary} />
      </div>
      <div className={styles.primaryMetric}>
        <div
          aria-label="100+ km chance"
          className={styles.valueRow}
          role="group"
          title={chance100KmPct.dataStatus === "missing" ? chance100KmPct.missingReason : undefined}
        >
          {chance100KmPct.dataStatus === "missing" ? (
            <span aria-hidden="true" className={styles.unavailable}>
              —
            </span>
          ) : (
            <strong>{formatChancePercent(chance100KmPct.value)}</strong>
          )}
          <DataStatusBadge compact short status={chance100KmPct.dataStatus} />
        </div>
        {chance100KmPct.dataStatus !== "missing" ? (
          <ForecastChanceProgress
            label="chance of 100 kilometres or more"
            value={chance100KmPct.value}
          />
        ) : null}
        <span className={styles.metricLabel}>100+ km chance</span>
      </div>
      <dl className={styles.secondaryMetrics}>
        <div>
          <dt className="visually-hidden">{cloud.label}</dt>
          <dd title={cloudbase.kind === "missing" ? cloudbase.missingReason : undefined}>
            <CloudIcon />
            <span>
              {cloud.value}
              {cloud.unit === undefined ? "" : ` ${cloud.unit}`}
              {cloudbase.kind === "conditional_lcl" ? (
                <small className={styles.cloudbaseLabel}>Conditional LCL</small>
              ) : null}
            </span>
          </dd>
        </div>
        <div className={styles.riskMetric}>
          <dt className="visually-hidden">OD risk</dt>
          <dd
            title={
              overdevelopmentRisk.dataStatus === "missing"
                ? overdevelopmentRisk.missingReason
                : undefined
            }
          >
            <ShieldIcon />
            {overdevelopmentRisk.value === null
              ? "Unavailable"
              : formatRisk(overdevelopmentRisk.value)}
          </dd>
        </div>
      </dl>
      <div className={styles.confidence}>
        <ConfidenceIndicator
          accessibleLabel="100+ km confidence"
          compact
          confidence={p100Confidence(chance100KmPct)}
          label="Conf."
        />
      </div>
    </article>
  );
};
