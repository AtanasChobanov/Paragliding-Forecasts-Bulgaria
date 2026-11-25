import type {
  DashboardForecastOutputs,
  ForecastInputRow,
  ForecastResponse,
} from "@paragliding-forecasts/contracts";
import { useState, type ComponentProps, type ReactNode } from "react";

import { DashboardPanel } from "../../../components/dashboard-panel/DashboardPanel.js";
import {
  formatChancePercent,
  formatForecastDateLong,
  formatInteger,
  formatRisk,
  p100Confidence,
  presentCloudbase,
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
import {
  ForecastInformation,
  InformationPopover,
} from "../../dashboard/components/ForecastInformation.js";
import {
  defaultCloudbaseHour,
  formatInputValue,
  formatSofiaHour,
  presentDriver,
  publicationLine,
  sourceLine,
} from "../forecast-detail-presentation.js";
import { InputEvidence, driverEvidencePages } from "./ForecastEvidence.js";
import { MeasuredPages } from "./MeasuredPages.js";
import styles from "./ForecastDetailContent.module.scss";

const DetailSelect = ({
  icon,
  className,
  ...props
}: ComponentProps<"select"> & { readonly icon: ReactNode }) => (
  <div className={[styles.selectField, className].filter(Boolean).join(" ")}>
    <span aria-hidden="true" className={styles.selectIcon}>
      {icon}
    </span>
    <select {...props} />
  </div>
);

const GroupIcon = () => (
  <svg viewBox="0 0 24 24">
    <path d="M4 6h16M4 12h16M4 18h16M8 4v4m8 2v4M8 16v4" />
  </svg>
);
const HourIcon = () => (
  <svg viewBox="0 0 24 24">
    <circle cx="12" cy="12" r="9" />
    <path d="M12 7v5l3 2" />
  </svg>
);
const metricIcon = (metric: string) =>
  metric === "cloudbase" || metric === "cloud" ? (
    <CloudbaseIcon />
  ) : metric === "overdevelopment" || metric === "od" ? (
    <OverdevelopmentIcon />
  ) : metric === "p200" ? (
    <RouteIcon />
  ) : metric === "p300" ? (
    <DistanceFlagIcon />
  ) : (
    <OpportunityIcon />
  );

type Metric = DashboardForecastOutputs[keyof DashboardForecastOutputs];
export const informationPages = (paragraphs: readonly string[]): ReactNode[] =>
  paragraphs.flatMap((paragraph) => {
    const words = paragraph.split(/\s+/u);
    const pages: string[] = [];
    let chunk = "";
    for (const word of words) {
      if (chunk.length + word.length > 230 && chunk) {
        pages.push(chunk);
        chunk = "";
      }
      chunk += `${chunk ? " " : ""}${word}`;
    }
    if (chunk) pages.push(chunk);
    return pages.map((text, i) => <p key={`${text.slice(0, 20)}-${String(i)}`}>{text}</p>);
  });
const limitationLabels: Readonly<Record<string, string>> = {
  uncalibrated_baseline: "This baseline has not been calibrated against observations.",
  not_observationally_calibrated:
    "This risk estimate has not been calibrated against observations.",
  model_column_not_terrain_corrected: "The atmospheric profile is not corrected for local terrain.",
  model_site_terrain_mismatch: "The model terrain elevation differs from the launch elevation.",
  potential_base_below_site: "The potential cloud base is below the launch elevation.",
  lcl_applicability_uncertain:
    "The condensation-level estimate may not apply to the predicted cloud conditions.",
  sensitivity_variant_unavailable: "Some alternative parcel calculations were unavailable.",
  sensitive_to_parcel_assumptions:
    "The result is sensitive to the assumed properties of the rising air parcel.",
  incomplete_cloud_regime_coverage: "Cloud formation could not be determined for every hour.",
  incomplete_weather_evidence: "Some weather evidence is missing.",
};
const readableEvidence = (text: string) =>
  limitationLabels[text.trim()] ??
  text
    .trim()
    .replace(
      /\b[a-z]+(?:_[a-z]+)+\b/gu,
      (code) => limitationLabels[code] ?? code.replaceAll("_", " "),
    );
const MetricInformation = ({
  metric,
  label,
  children,
}: {
  readonly metric: Metric;
  readonly label: string;
  readonly children?: ReactNode;
}) => {
  const note = metric.dataStatus === "missing" ? metric.confidenceNote : metric.confidence.note;
  const limitations = [
    ...new Set(
      (metric.limitationsNote ?? "")
        .split(";")
        .map((part) => part.trim())
        .filter(Boolean),
    ),
  ];
  return (
    <div className={styles.metricInformation}>
      <h3>{label}</h3>
      {children}
      {metric.dataStatus === "missing" ? (
        <section>
          <h4>Availability</h4>
          <p>{readableEvidence(metric.missingReason)}</p>
        </section>
      ) : null}
      {note ? (
        <section>
          <h4>About this estimate</h4>
          <p>{readableEvidence(note)}</p>
        </section>
      ) : null}
      {limitations.length ? (
        <section>
          <h4>Limitations</h4>
          <ul>
            {limitations.map((text) => (
              <li key={text}>{readableEvidence(text)}</li>
            ))}
          </ul>
        </section>
      ) : null}
      {!note && !limitations.length && metric.dataStatus !== "missing" ? (
        <p>No additional explanation was published.</p>
      ) : null}
    </div>
  );
};

export const inputInformation = (row: ForecastInputRow): string[] => [
  row.label,
  row.value === null
    ? (row.missingReason ?? "Unavailable")
    : `${String(row.value)} ${row.unit} (canonical) · ${formatInputValue(row)}`,
  `Statistic: ${row.statistic}. Quality: ${row.qualityState}. Provenance: ${String(row.provenanceId ?? "not retained")}.`,
  ...(row.intervalStartUtc
    ? [`Exact interval: ${row.intervalStartUtc} – ${row.intervalEndUtc ?? ""}`]
    : []),
];

const OutputMetric = ({
  icon,
  label,
  metric,
  value,
  information,
}: {
  readonly icon: ReactNode;
  readonly label: string;
  readonly metric: Metric;
  readonly value: string;
  readonly information?: ReactNode;
}) => (
  <article aria-label={label} data-status={metric.dataStatus} className={styles.outputMetric}>
    <div className={styles.outputHeader}>
      <span aria-hidden="true" className={styles.outputIcon}>
        {icon}
      </span>
      <DataStatusBadge compact short status={metric.dataStatus} />
    </div>
    <div className={styles.outputLabel}>
      <span>{label}</span>
      <InformationPopover
        fitViewport={Boolean(information)}
        label={`${label} information`}
        regionLabel={`${label} evidence`}
      >
        <MetricInformation metric={metric} label={label}>
          {information}
        </MetricInformation>
      </InformationPopover>
    </div>
    <div className={styles.outputReading}>
      <strong className={styles.outputValue}>{value}</strong>
    </div>
    <div className={styles.outputConfidence}>
      <ConfidenceIndicator
        compact
        shortUnavailable
        accessibleLabel={`${label} confidence`}
        confidence={p100Confidence(metric)}
        label="Confidence"
      />
    </div>
  </article>
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
  const cloud = presentCloudbase(outputs.cloudbase);
  const chosen = forecast.cloudbaseHours.find(
    (hour) => hour.validAtUtc === defaultCloudbaseHour(forecast),
  );
  return (
    <section aria-labelledby="forecast-detail-heading" className={styles.summary}>
      <div className={styles.summaryHeading}>
        <div>
          <h1
            id="forecast-detail-heading"
            title={`${siteName} · ${formatForecastDateLong(forecast.forecastDate)}`}
          >
            {siteName} · {formatForecastDateLong(forecast.forecastDate)}
          </h1>
          <p title={publicationLine(forecast)}>{publicationLine(forecast)}</p>
        </div>
        <ForecastInformation
          siteName={siteName}
          summary={{ availability: "available", ...forecast }}
          metadataOnly
        />
      </div>
      <div aria-label="Detailed forecast outputs" className={styles.summaryMetrics}>
        <div className={styles.probabilities}>
          {(
            [
              ["100+ km", chance100, <OpportunityIcon />],
              ["200+ km", outputs.chance200KmPct, <RouteIcon />],
              ["300+ km", outputs.chance300KmPct, <DistanceFlagIcon />],
            ] as const
          ).map(([label, metric, icon]) => (
            <article
              aria-label={label}
              data-status={metric.dataStatus}
              className={styles.probabilityRow}
              key={label}
            >
              <div className={styles.probabilityHeading}>
                <strong>
                  {metric.value === null ? "Unavailable" : formatChancePercent(metric.value)}
                </strong>
                <span>{label} chance</span>
              </div>
              <div className={styles.probabilityEvidence}>
                <div className={styles.probabilityMeta}>
                  <div className={styles.outputHeader}>
                    <span aria-hidden="true" className={styles.outputIcon}>
                      {icon}
                    </span>
                    <DataStatusBadge compact short status={metric.dataStatus} />
                  </div>
                  <InformationPopover
                    label={`${label} information`}
                    regionLabel={`${label} evidence`}
                  >
                    <MetricInformation metric={metric} label={label} />
                  </InformationPopover>
                </div>
                <div className={styles.probabilityConfidence}>
                  <span>Model confidence</span>
                  <ConfidenceIndicator
                    compact
                    adjacent
                    shortUnavailable
                    confidence={p100Confidence(metric)}
                    label={null}
                    accessibleLabel={`${label === "100+ km" ? "P100 model" : label} confidence`}
                  />
                </div>
              </div>
              {metric.value !== null ? (
                <ForecastChanceProgress label={`chance of ${label} or more`} value={metric.value} />
              ) : null}
            </article>
          ))}
        </div>
        <div className={styles.outputGrid}>
          <OutputMetric
            icon={<CloudbaseIcon />}
            label={cloud.label}
            metric={outputs.cloudbase}
            value={`${cloud.value}${cloud.unit ? ` ${cloud.unit}` : ""}`}
            information={
              <>
                {"valueMslM" in outputs.cloudbase ? (
                  <div className={styles.metricInformation}>
                    <section>
                      <h4>Height above terrain</h4>
                      <dl className={styles.heightDefinitions}>
                        <dt>Site AGL</dt>
                        <dd>
                          {chosen?.heightSiteAglM == null
                            ? "Unavailable"
                            : `${formatInteger(chosen.heightSiteAglM)} m`}
                        </dd>
                        <dt>Model AGL</dt>
                        <dd>
                          {chosen?.heightModelAglM == null
                            ? "Unavailable"
                            : `${formatInteger(chosen.heightModelAglM)} m`}
                        </dd>
                      </dl>
                    </section>
                  </div>
                ) : null}
              </>
            }
          />
          <OutputMetric
            icon={<OverdevelopmentIcon />}
            label="OD risk"
            metric={outputs.overdevelopmentRisk}
            value={
              outputs.overdevelopmentRisk.value === null
                ? "Unavailable"
                : formatRisk(outputs.overdevelopmentRisk.value)
            }
          />
        </div>
      </div>
    </section>
  );
};

const InputRow = ({ row }: { readonly row: ForecastInputRow }) => (
  <div className={styles.inputRow}>
    <span className={styles.rowLabel}>{row.label}</span>
    <strong>{formatInputValue(row)}</strong>
    <DataStatusBadge compact short status={row.dataStatus} />
    <InformationPopover
      label={`Input information: ${row.label}`}
      regionLabel={`${row.label} input`}
      fitViewport
    >
      <InputEvidence row={row} omitDisplayedValue />
    </InformationPopover>
  </div>
);

export const ForecastInputsPanel = ({
  forecast,
  selectedHour,
  onSelectHour,
}: {
  readonly forecast: ForecastResponse;
  readonly selectedHour: string;
  readonly onSelectHour: (at: string) => void;
}) => {
  const [mode, setMode] = useState("xc");
  const [group, setGroup] = useState("Surface temperature");
  const groups = [...new Set(forecast.forecastInputs.xcFeatures.map((row) => row.group))];
  const hour = forecast.forecastInputs.hourlyContext.find(
    (hour) => hour.validAtUtc === selectedHour,
  );
  const rows =
    mode === "xc"
      ? forecast.forecastInputs.xcFeatures.filter((row) => row.group === group)
      : mode === "od"
        ? (hour?.odInputs ?? [])
        : (hour?.cloudbaseContext ?? []);
  return (
    <DashboardPanel
      className={styles.detailPanel}
      headingId="forecast-inputs-heading"
      title="Forecast inputs"
    >
      <div className={styles.panelContent}>
        <p className={styles.panelMetadata}>{sourceLine(forecast)} · 10:00–20:00 Europe/Sofia</p>
        <div className={styles.selectors}>
          <DetailSelect
            icon={metricIcon(mode)}
            aria-label="Input category"
            value={mode}
            onChange={(e) => {
              setMode(e.target.value);
            }}
          >
            <option value="xc">XC inputs</option>
            <option value="od">OD inputs</option>
            <option value="cloud">Cloudbase context</option>
          </DetailSelect>
          {mode === "xc" ? (
            <DetailSelect
              icon={<GroupIcon />}
              aria-label="XC input group"
              value={group}
              onChange={(e) => {
                setGroup(e.target.value);
              }}
            >
              {groups.map((group) => (
                <option key={group}>{group}</option>
              ))}
            </DetailSelect>
          ) : (
            <DetailSelect
              icon={<HourIcon />}
              aria-label="Input hour"
              value={selectedHour}
              onChange={(e) => {
                onSelectHour(e.target.value);
              }}
            >
              {forecast.cloudbaseHours.map((hour) => (
                <option key={hour.validAtUtc} value={hour.validAtUtc}>
                  {formatSofiaHour(hour.validAtUtc)} Sofia
                </option>
              ))}
            </DetailSelect>
          )}
        </div>
        <MeasuredPages
          key={`${mode}-${group}`}
          items={rows}
          label="Forecast inputs"
          maxRows={6}
          render={(row) => <InputRow row={row} />}
        />
      </div>
    </DashboardPanel>
  );
};

const metricLabels = {
  p100: "100+ km",
  p200: "200+ km",
  p300: "300+ km",
  overdevelopment: "OD risk",
  cloudbase: "Cloudbase",
} as const;
type MetricCode = keyof typeof metricLabels;
export const TopDriversPanel = ({ forecast }: { readonly forecast: ForecastResponse }) => {
  const [selected, setSelected] = useState<MetricCode>("p100");
  const group = forecast.explanations.find((group) => group.metricCode === selected);
  const metadata = forecast.metadata;
  const version =
    metadata.mode === "mock"
      ? metadata.version
      : selected === "overdevelopment"
        ? metadata.overdevelopmentPolicyVersion
        : selected === "cloudbase"
          ? metadata.cloudbaseMethodVersion
          : `XC model ${metadata.xcModelId}`;
  const note =
    selected === "p200"
      ? "Conditional step P(200+ | 100+); final P200 = P100 × conditional estimate"
      : selected === "p100"
        ? "Contributions relative to the training reference (logits)"
        : selected === "p300"
          ? "P300 = P200 × published pooled conversion"
          : selected === "overdevelopment"
            ? "Published risk rules and score points"
            : "Published formation evidence; uncalibrated baseline";
  return (
    <DashboardPanel
      className={styles.detailPanel}
      headingId="forecast-drivers-heading"
      title="Why this result"
    >
      <div className={styles.panelContent}>
        <p className={styles.panelMetadata} title={version}>
          {version}
        </p>
        <div className={styles.tabs} role="tablist" aria-label="Explanation metric">
          {Object.entries(metricLabels).map(([key, label]) => (
            <button
              aria-selected={selected === key}
              key={key}
              role="tab"
              type="button"
              onClick={() => {
                setSelected(key as MetricCode);
              }}
            >
              {label}
            </button>
          ))}
        </div>
        <DetailSelect
          icon={metricIcon(selected)}
          className={styles.metricSelect}
          aria-label="Explanation metric"
          value={selected}
          onChange={(e) => {
            setSelected(e.target.value as MetricCode);
          }}
        >
          {Object.entries(metricLabels).map(([key, label]) => (
            <option value={key} key={key}>
              {label}
            </option>
          ))}
        </DetailSelect>
        <div className={styles.driverNote}>
          {group ? <DataStatusBadge compact short status={group.dataStatus} /> : null}
          <span>{group?.missingReason ?? note}</span>
          <InformationPopover
            label="Explanation limitations"
            regionLabel="Explanation limitations"
            fitViewport
          >
            <div className={styles.metricInformation}>
              <h3>About this explanation</h3>
              <p>{note}</p>
              {group?.confidenceNote ? (
                <section>
                  <h4>Evidence</h4>
                  <p>{readableEvidence(group.confidenceNote)}</p>
                </section>
              ) : null}
              {group?.limitationsNote ? (
                <section>
                  <h4>Limitations</h4>
                  <p>{readableEvidence(group.limitationsNote)}</p>
                </section>
              ) : null}
              {group?.missingReason ? (
                <section>
                  <h4>Availability</h4>
                  <p>{readableEvidence(group.missingReason)}</p>
                </section>
              ) : null}
            </div>
          </InformationPopover>
        </div>
        <MeasuredPages
          key={selected}
          items={group?.drivers ?? []}
          label="Forecast drivers"
          maxRows={3}
          render={(driver) => {
            const presentation = presentDriver(driver);
            return (
              <div className={styles.driverRow}>
                <span
                  aria-label={presentation.meaning}
                  className={styles.driverSymbol}
                  data-tone={presentation.tone}
                >
                  {presentation.symbol}
                </span>
                <span className={styles.rowLabel}>
                  {driver.message}
                  {driver.kind === "pooled_conversion"
                    ? ` · ${String(driver.supportSuccesses)}/${String(driver.supportTotal)}`
                    : ""}
                </span>
                <InformationPopover
                  label={`Driver information: ${driver.code}`}
                  regionLabel={`${driver.code} driver`}
                  fitViewport
                  {...(driver.inputs.length > 3
                    ? { pages: driverEvidencePages(driver) }
                    : { children: driverEvidencePages(driver)[0] })}
                />
              </div>
            );
          }}
        />
      </div>
    </DashboardPanel>
  );
};
