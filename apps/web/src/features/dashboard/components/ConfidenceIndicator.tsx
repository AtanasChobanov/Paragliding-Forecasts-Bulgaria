import type { DisplayConfidence } from "../forecast-presentation.js";
import { formatConfidence } from "../forecast-presentation.js";
import styles from "./ConfidenceIndicator.module.scss";

export interface ConfidenceIndicatorProps {
  readonly accessibleLabel?: string;
  readonly confidence: DisplayConfidence;
  readonly compact?: boolean;
  /** Visible description for the meter; use null only when nearby copy is explicit. */
  readonly label?: string | null;
  /** Whether to render the supplementary confidence note. */
  readonly showNote?: boolean;
  readonly shortUnavailable?: boolean;
}

const filledSegmentCount = (level: DisplayConfidence["level"]): number => {
  switch (level) {
    case "high":
      return 3;
    case "medium":
      return 2;
    case "low":
      return 1;
    case "mixed":
    case "unavailable":
      return 0;
  }
};

export const ConfidenceIndicator = ({
  accessibleLabel,
  compact = false,
  confidence,
  label: prefix = "Confidence",
  showNote = !compact,
  shortUnavailable = false,
}: ConfidenceIndicatorProps) => {
  const label = formatConfidence(confidence.level);
  const note = confidence.notes.join(" ");
  const unavailable = confidence.level === "unavailable";
  const filled = filledSegmentCount(confidence.level);

  return (
    <div
      aria-label={accessibleLabel === undefined ? undefined : `${accessibleLabel}. ${label}`}
      className={compact ? styles.compact : undefined}
      role={accessibleLabel === undefined ? undefined : "group"}
      title={note || undefined}
    >
      <div className={styles.row}>
        {prefix === null || unavailable ? null : <span className={styles.prefix}>{prefix}</span>}
        {unavailable ? null : (
          <span aria-hidden="true" className={styles.segments}>
            {[1, 2, 3].map((segment) => (
              <span className={segment <= filled ? styles.filled : undefined} key={segment} />
            ))}
          </span>
        )}
        <span className={styles.label}>
          {unavailable && shortUnavailable ? "Unavailable" : label.replace(" confidence", "")}
        </span>
      </div>
      {!showNote || note.length === 0 ? null : <p className={styles.note}>{note}</p>}
    </div>
  );
};
