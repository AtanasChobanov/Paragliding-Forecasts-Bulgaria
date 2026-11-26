import type { ForecastDriver, ForecastInputRow } from "@paragliding-forecasts/contracts";
import { formatInputValue } from "../forecast-detail-presentation.js";
import styles from "./ForecastDetailContent.module.scss";

const readable = (value: string) => value.replaceAll("_", " ");
const timestamp = (value: string) =>
  `${new Intl.DateTimeFormat("en-GB", {
    timeZone: "Europe/Sofia",
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(new Date(value))} Sofia`;

const intervalTime = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Europe/Sofia",
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

export const InputEvidence = ({
  row,
  omitDisplayedValue = false,
  presentation = false,
}: {
  readonly row: ForecastInputRow;
  readonly omitDisplayedValue?: boolean;
  readonly presentation?: boolean;
}) => (
  <dl className={styles.evidenceFields}>
    {row.value === null ? (
      <>
        <dt>Availability</dt>
        <dd>{readable(row.missingReason ?? "Unavailable")}</dd>
      </>
    ) : !omitDisplayedValue ||
      formatInputValue(row).replaceAll(",", "") !== `${String(row.value)} ${row.unit}` ? (
      <>
        <dt>{presentation ? "Value" : "Exact source value"}</dt>
        <dd>{presentation ? formatInputValue(row) : `${String(row.value)} ${row.unit}`}</dd>
      </>
    ) : null}
    <dt>Statistic</dt>
    <dd>{readable(row.statistic)}</dd>
    <dt>Quality</dt>
    <dd>{readable(row.qualityState)}</dd>
    <dt>Source record ID</dt>
    <dd>{row.provenanceId ?? "Not retained"}</dd>
    {row.intervalStartUtc ? (
      <>
        <dt>Interval</dt>
        <dd>
          {presentation && row.intervalEndUtc ? (
            `${intervalTime.formatRange(new Date(row.intervalStartUtc), new Date(row.intervalEndUtc))} Sofia`
          ) : (
            <>
              {timestamp(row.intervalStartUtc)} –{" "}
              {row.intervalEndUtc ? timestamp(row.intervalEndUtc) : "Unavailable"}
            </>
          )}
        </dd>
      </>
    ) : null}
    {row.layerBaseAglM !== undefined || row.layerTopAglM !== undefined ? (
      <>
        <dt>Layer above terrain</dt>
        <dd>
          {row.layerBaseAglM ?? "Unavailable"} – {row.layerTopAglM ?? "Unavailable"} m AGL
        </dd>
      </>
    ) : null}
  </dl>
);

const DriverInputs = ({ inputs }: { readonly inputs: ForecastDriver["inputs"] }) => (
  <dl className={styles.evidenceFields}>
    {inputs.map((input, index) => (
      <div className={styles.driverInputValue} key={`${input.inputKey}-${String(index)}`}>
        <dt>{input.field?.label ?? readable(input.inputKey)}</dt>
        <dd title={input.field?.missingReason ?? input.unavailableReason}>
          {input.field?.value != null ? formatInputValue(input.field) : "Unavailable"}
        </dd>
      </div>
    ))}
  </dl>
);

export const DriverEvidence = ({ driver }: { readonly driver: ForecastDriver }) => {
  const overview = (
    <div key="explanation" className={styles.metricInformation}>
      <h3>Why this result</h3>
      <p>{driver.message}</p>
      <section>
        <h4>Calculation details</h4>
        <dl className={styles.evidenceFields}>
          <dt>Published reference</dt>
          <dd>{driver.code}</dd>
          <dt>Rank</dt>
          <dd>{driver.rank}</dd>
          {driver.xcStage ? (
            <>
              <dt>Model step</dt>
              <dd>
                {driver.xcStage === "q200" ? "200+ km given 100+ km (Q200)" : "100+ km (P100)"}
              </dd>
            </>
          ) : null}
          {driver.contributionLogit !== undefined ? (
            <>
              <dt>Model contribution</dt>
              <dd>{driver.contributionLogit} logits</dd>
            </>
          ) : null}
          {driver.scorePoints !== undefined ? (
            <>
              <dt>Risk contribution</dt>
              <dd>{driver.scorePoints} points</dd>
            </>
          ) : null}
          {driver.kind === "pooled_conversion" ? (
            <>
              <dt>Pooled conversion</dt>
              <dd>
                P300 = P200 × {driver.supportSuccesses}/{driver.supportTotal}
              </dd>
            </>
          ) : null}
        </dl>
        {driver.contributionLogit !== undefined ? (
          <p className={styles.evidenceTime}>
            Relative to the training reference; not percentage points or a causal effect.
          </p>
        ) : null}
      </section>
      {driver.inputs.length <= 8 && driver.inputs.length > 0 ? (
        <section>
          <h4>Published inputs</h4>
          <DriverInputs inputs={driver.inputs} />
        </section>
      ) : null}
    </div>
  );
  if (driver.inputs.length <= 8) return overview;
  const groups = new Map<string, ForecastDriver["inputs"]>();
  for (const input of driver.inputs) {
    const key = input.field?.group ?? "Other published inputs";
    groups.set(key, [...(groups.get(key) ?? []), input]);
  }
  return (
    <>
      {overview}
      {Array.from(groups, ([group, inputs]) => (
        <div key={group} className={styles.metricInformation}>
          <h3>{group}</h3>
          <DriverInputs inputs={inputs} />
        </div>
      ))}
    </>
  );
};
