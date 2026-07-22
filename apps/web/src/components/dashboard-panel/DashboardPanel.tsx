import type { ReactNode } from "react";

import styles from "./DashboardPanel.module.scss";

export interface DashboardPanelProps {
  readonly busy?: boolean;
  readonly children: ReactNode;
  readonly className?: string | undefined;
  readonly headingId: string;
  readonly title: string;
  readonly accessory?: ReactNode;
}

export const DashboardPanel = ({
  accessory,
  busy = false,
  children,
  className,
  headingId,
  title,
}: DashboardPanelProps) => {
  const panelClassName = [styles.panel, className]
    .filter((candidate): candidate is string => candidate !== undefined)
    .join(" ");

  return (
    <section aria-busy={busy || undefined} aria-labelledby={headingId} className={panelClassName}>
      <div className={styles.header}>
        <h2 id={headingId}>{title}</h2>
        {accessory === undefined ? null : <div className={styles.accessory}>{accessory}</div>}
      </div>
      <div className={styles.body}>{children}</div>
    </section>
  );
};
