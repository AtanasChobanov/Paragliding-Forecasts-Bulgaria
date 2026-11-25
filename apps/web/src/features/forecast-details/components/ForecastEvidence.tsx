import type { ForecastDriver, ForecastInputRow } from "@paragliding-forecasts/contracts";
import type { ReactNode } from "react";
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

export const InputEvidence = ({
  row,
  omitDisplayedValue = false,
}: {
  readonly row: ForecastInputRow;
  readonly omitDisplayedValue?: boolean;
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
        <dt>Exact source value</dt>
        <dd>
          {String(row.value)} {row.unit}
        </dd>
      </>
    ) : null}
    <dt>Statistic</dt>
    <dd>{readable(row.statistic)}</dd>
    <dt>Quality</dt>
    <dd>{readable(row.qualityState)}</dd>
    <dt>Source record</dt>
    <dd>{row.provenanceId ?? "Not retained"}</dd>
    {row.intervalStartUtc ? (
      <>
        <dt>Interval</dt>
        <dd>
          {timestamp(row.intervalStartUtc)} –{" "}
          {row.intervalEndUtc ? timestamp(row.intervalEndUtc) : "Unavailable"}
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
  <div className={styles.evidenceInputs}>
    {inputs.map((input, index) => (
      <section key={`${input.inputKey}-${String(index)}`}>
        <h4>{input.field?.label ?? readable(input.inputKey)}</h4>
        {input.validAtUtc ? (
          <p className={styles.evidenceTime}>
            {timestamp(input.validAtUtc)}
            {input.intervalEndUtc ? ` – ${timestamp(input.intervalEndUtc)}` : ""}
          </p>
        ) : null}
        {input.field ? (
          <InputEvidence row={input.field} />
        ) : (
          <p>{input.unavailableReason ?? "Exact input is retained in the ML artifact."}</p>
        )}
        {!input.field && input.provenanceId !== undefined ? (
          <p>Source record: {input.provenanceId}</p>
        ) : null}
      </section>
    ))}
  </div>
);

export const driverEvidencePages = (driver: ForecastDriver): ReactNode[] => {
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
      {driver.inputs.length <= 3 && driver.inputs.length > 0 ? (
        <section>
          <h4>Published inputs</h4>
          <DriverInputs inputs={driver.inputs} />
        </section>
      ) : null}
    </div>
  );
  if (driver.inputs.length <= 3) return [overview];
  const groups = new Map<string, ForecastDriver["inputs"]>();
  for (const input of driver.inputs) {
    const key = input.field?.group ?? "Other published inputs";
    groups.set(key, [...(groups.get(key) ?? []), input]);
  }
  return [
    overview,
    ...Array.from(groups, ([group, inputs]) => (
      <div key={group} className={styles.metricInformation}>
        <h3>{group}</h3>
        <DriverInputs inputs={inputs} />
      </div>
    )),
  ];
};
