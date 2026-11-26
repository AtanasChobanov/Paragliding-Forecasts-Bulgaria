import type { ReactNode } from "react";
import styles from "./ForecastDetailContent.module.scss";

export const ScrollableList = <T,>({
  items,
  render,
  label,
}: {
  readonly items: readonly T[];
  readonly render: (item: T, index: number) => ReactNode;
  readonly label: string;
}) => (
  <div
    className={styles.scrollableList}
    data-scroll-list
    role="region"
    aria-label={`${label} list`}
    tabIndex={0}
  >
    {items.map((item, index) => (
      <div data-list-row key={index}>
        {render(item, index)}
      </div>
    ))}
    {items.length === 0 ? <p className={styles.empty}>No distinct driver was published</p> : null}
  </div>
);
