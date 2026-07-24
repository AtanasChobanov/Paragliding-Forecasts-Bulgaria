import type {
  ForecastInputs,
  ForecastOutputs,
  ForecastResponse,
} from "@paragliding-forecasts/contracts";
import type { ReactNode } from "react";

import { DashboardPanel } from "../../../components/dashboard-panel/DashboardPanel.js";
import {
  formatForecastDateLong,
  formatGeneratedAt,
  formatInteger,
  formatRisk,
  summarizeDataStatus,
} from "../../dashboard/forecast-presentation.js";
import { ConfidenceIndicator } from "../../dashboard/components/ConfidenceIndicator.js";
import { DataStatusBadge } from "../../dashboard/components/DataStatusBadge.js";
import { ForecastChanceProgress } from "../../dashboard/components/ForecastChanceProgress.js";
import {
  CloudbaseIcon,
  DistanceFlagIcon,
  OpportunityIcon,
  OverdevelopmentIcon,
  RouteIcon,
} from "../../dashboard/components/ForecastIcons.js";
import styles from "./ForecastDetailContent.module.scss";

type DetailOutputMetric = ForecastOutputs[keyof ForecastOutputs];
type DetailInputKey = Exclude<keyof ForecastInputs, "provenance" | "sourceRunAt">;
type DetailInputMetric = ForecastInputs[DetailInputKey];

const summarizeInputDataStatus = (forecastInputs: ForecastInputs) => {
  const statuses = new Set(forecastInputRows.map((row) => forecastInputs[row.key].dataStatus));

  return statuses.size === 1 ? ([...statuses][0] ?? "missing") : "mixed";
};

const displayConfidence = (metric: DetailOutputMetric) =>
  metric.dataStatus === "missing"
    ? { level: "unavailable" as const, notes: [metric.missingReason] }
    : { level: metric.confidence.level, notes: [metric.confidence.note] };

const OutputMetric = ({
  icon,
  label,
  metric,
  value,
}: {
  readonly icon: ReactNode;
  readonly label: string;
  readonly metric: DetailOutputMetric;
  readonly value: string | null;
}) => {
  const unavailable = metric.dataStatus === "missing" || value === null;

  return (
    <article className={styles.outputMetric}>
      <span aria-hidden="true" className={styles.outputIcon}>
        {icon}
      </span>
      <span className={styles.outputLabel}>{label}</span>
      {unavailable ? (
        <strong className={styles.unavailable}>Unavailable</strong>
      ) : (
        <strong className={styles.outputValue}>{value}</strong>
      )}
      {metric.dataStatus === "missing" ? (
        <p className={styles.reason}>{metric.missingReason}</p>
      ) : null}
      <DataStatusBadge compact status={metric.dataStatus} />
      <ConfidenceIndicator compact confidence={displayConfidence(metric)} />
    </article>
  );
};

const forecastInputRows: readonly {
  readonly format: (value: unknown) => string;
  readonly key: DetailInputKey;
  readonly label: string;
}[] = [
  {
    key: "surfaceTemperatureC",
    label: "Surface temperature",
    format: (value) => `${String(value)} °C`,
  },
  { key: "dewPointC", label: "Dew point", format: (value) => `${String(value)} °C` },
  {
    key: "boundaryLayerHeightM",
    label: "Boundary-layer height",
    format: (value) => `${formatInteger(value as number)} m`,
  },
  {
    key: "thermalStrengthMps",
    label: "Thermal strength",
    format: (value) => `${String(value)} m/s`,
  },
  {
    key: "boundaryLayerWindSpeedKmh",
    label: "Boundary-layer wind",
    format: (value) => `${String(value)} km/h`,
  },
  {
    key: "boundaryLayerWindDirectionDeg",
    label: "BL wind direction",
    format: (value) => `${String(value)}°`,
  },
  {
    key: "windByAltitude",
    label: "Wind by altitude",
    format: (value) =>
      (value as readonly { readonly altitudeMslM: number; readonly speedKmh: number }[])
        .map((wind) => `${formatInteger(wind.altitudeMslM)} m: ${String(wind.speedKmh)} km/h`)
        .join(" · "),
  },
  { key: "windShearMpsPerKm", label: "Wind shear", format: (value) => `${String(value)} m/s/km` },
  {
    key: "relativeHumidityPct",
    label: "Relative humidity",
    format: (value) => `${String(value)}%`,
  },
  { key: "capeJPerKg", label: "CAPE", format: (value) => `${String(value)} J/kg` },
  { key: "cinJPerKg", label: "CIN", format: (value) => `${String(value)} J/kg` },
  { key: "lapseRateCPerKm", label: "Lapse rate", format: (value) => `${String(value)} °C/km` },
  { key: "lowCloudCoverPct", label: "Low cloud", format: (value) => `${String(value)}%` },
  { key: "totalCloudCoverPct", label: "Total cloud", format: (value) => `${String(value)}%` },
  { key: "precipitationMm", label: "Precipitation", format: (value) => `${String(value)} mm` },
  {
    key: "surfacePressureHpa",
    label: "Surface pressure",
    format: (value) => `${String(value)} hPa`,
  },
  {
    key: "convergenceSignal",
    label: "Convergence",
    format: (value) => `${String(value).charAt(0).toUpperCase()}${String(value).slice(1)}`,
  },
];

const InputMetric = ({
  label,
  metric,
  format,
}: {
  readonly label: string;
  readonly metric: DetailInputMetric;
  readonly format: (value: unknown) => string;
}) => (
  <div className={styles.inputMetric}>
    <dt>{label}</dt>
    {metric.dataStatus === "missing" ? (
      <dd>
        <strong className={styles.unavailable}>Unavailable</strong>
        <DataStatusBadge compact status="missing" />
        <span className={styles.reason}>{metric.missingReason}</span>
      </dd>
    ) : (
      <dd>
        <strong>{format(metric.value)}</strong>
        <DataStatusBadge compact status={metric.dataStatus} />
      </dd>
    )}
  </div>
);

export const ForecastDetailSummary = ({
  forecast,
  siteName,
}: {
  readonly forecast: ForecastResponse;
  readonly siteName: string;
}) => {
  const { outputs } = forecast;
  const chance100 = outputs.chance100KmPct;

  return (
    <section aria-labelledby="forecast-detail-heading" className={styles.summary}>
      <div className={styles.summaryHeading}>
        <div>
          <h2 id="forecast-detail-heading">
            {siteName} · {formatForecastDateLong(forecast.forecastDate)}
          </h2>
          <p>
            {forecast.provenance.version} · generated {formatGeneratedAt(forecast.generatedAt)}
          </p>
        </div>
        <DataStatusBadge status={summarizeDataStatus(outputs)} />
      </div>
      <div className={styles.primaryChance}>
        {chance100.dataStatus === "missing" ? (
          <strong className={styles.unavailable}>Unavailable</strong>
        ) : (
          <strong>{formatInteger(chance100.value)}%</strong>
        )}
        <span>100+ km chance</span>
        <DataStatusBadge compact status={chance100.dataStatus} />
        {chance100.dataStatus === "missing" ? (
          <p className={styles.reason}>{chance100.missingReason}</p>
        ) : (
          <div className={styles.primaryProgress}>
            <ForecastChanceProgress
              label="chance of 100 kilometres or more"
              value={chance100.value}
            />
          </div>
        )}
        <span>Model confidence</span>
        <ConfidenceIndicator compact confidence={displayConfidence(chance100)} />
      </div>
      <div aria-label="Detailed forecast outputs" className={styles.outputGrid}>
        <OutputMetric
          icon={<CloudbaseIcon />}
          label="Cloudbase"
          metric={outputs.cloudbaseMslM}
          value={
            outputs.cloudbaseMslM.dataStatus === "missing"
              ? null
              : `${formatInteger(outputs.cloudbaseMslM.value)} m MSL`
          }
        />
        <OutputMetric
          icon={<OpportunityIcon />}
          label="100+ km chance"
          metric={outputs.chance100KmPct}
          value={
            outputs.chance100KmPct.dataStatus === "missing"
              ? null
              : `${formatInteger(outputs.chance100KmPct.value)}%`
          }
        />
        <OutputMetric
          icon={<RouteIcon />}
          label="200+ km chance"
          metric={outputs.chance200KmPct}
          value={
            outputs.chance200KmPct.dataStatus === "missing"
              ? null
              : `${formatInteger(outputs.chance200KmPct.value)}%`
          }
        />
        <OutputMetric
          icon={<DistanceFlagIcon />}
          label="300+ km chance"
          metric={outputs.chance300KmPct}
          value={
            outputs.chance300KmPct.dataStatus === "missing"
              ? null
              : `${formatInteger(outputs.chance300KmPct.value)}%`
          }
        />
        <OutputMetric
          icon={<OverdevelopmentIcon />}
          label="Overdevelopment"
          metric={outputs.overdevelopmentRisk}
          value={
            outputs.overdevelopmentRisk.dataStatus === "missing"
              ? null
              : formatRisk(outputs.overdevelopmentRisk.value)
          }
        />
      </div>
    </section>
  );
};

export const ForecastInputsPanel = ({
  forecastInputs,
}: {
  readonly forecastInputs: ForecastInputs;
}) => (
  <DashboardPanel
    accessory={<DataStatusBadge status={summarizeInputDataStatus(forecastInputs)} />}
    headingId="forecast-inputs-heading"
    title="Forecast inputs"
  >
    <p className={styles.panelMetadata}>
      {forecastInputs.provenance.source} · updated {formatGeneratedAt(forecastInputs.sourceRunAt)}
    </p>
    <dl className={styles.inputGrid}>
      {forecastInputRows.map((row) => (
        <InputMetric
          format={row.format}
          key={row.key}
          label={row.label}
          metric={forecastInputs[row.key]}
        />
      ))}
    </dl>
  </DashboardPanel>
);

export const TopDriversPanel = ({ forecast }: { readonly forecast: ForecastResponse }) => (
  <DashboardPanel
    accessory={<DataStatusBadge status={summarizeDataStatus(forecast.outputs)} />}
    headingId="forecast-drivers-heading"
    title="Why this result"
  >
    <p className={styles.driverIntro}>Top drivers from the current forecast response.</p>
    <ul className={styles.drivers}>
      {forecast.topDrivers.map((driver) => (
        <li key={driver}>{driver}</li>
      ))}
    </ul>
  </DashboardPanel>
);

export const PreviousRunComparison = () => (
  <section aria-labelledby="previous-run-heading" className={styles.comparison}>
    <h2 id="previous-run-heading">Compared with previous run</h2>
    <ul>
      {[
        "100+ km chance",
        "200+ km chance",
        "300+ km chance",
        "Cloudbase",
        "Overdevelopment risk",
      ].map((label) => (
        <li key={label}>
          <span>{label}</span>
          <strong>Unchanged</strong>
        </li>
      ))}
    </ul>
    <p className="visually-hidden">Previous-run comparison data is not loaded yet.</p>
  </section>
);
