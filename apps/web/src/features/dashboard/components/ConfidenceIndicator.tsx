import type { DisplayConfidence } from "../forecast-presentation.js";
import { formatConfidence } from "../forecast-presentation.js";
import styles from "./ConfidenceIndicator.module.scss";

export interface ConfidenceIndicatorProps {
  readonly confidence: DisplayConfidence;
  readonly compact?: boolean;
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

export const ConfidenceIndicator = ({ compact = false, confidence }: ConfidenceIndicatorProps) => {
  const label = formatConfidence(confidence.level);
  const note = confidence.notes.join(" ");
  const filled = filledSegmentCount(confidence.level);

  return (
    <div className={compact ? styles.compact : undefined} title={note || undefined}>
      <div className={styles.row}>
        <span className={styles.prefix}>Confidence</span>
        <span aria-hidden="true" className={styles.segments}>
          {[1, 2, 3].map((segment) => (
            <span className={segment <= filled ? styles.filled : undefined} key={segment} />
          ))}
        </span>
        <span className={styles.label}>{label.replace(" confidence", "")}</span>
      </div>
      {compact || note.length === 0 ? null : <p className={styles.note}>{note}</p>}
    </div>
  );
};
