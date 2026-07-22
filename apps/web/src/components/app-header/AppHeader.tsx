import styles from "./AppHeader.module.scss";

const CanopyMark = () => (
  <svg aria-hidden="true" className={styles.mark} focusable="false" viewBox="0 0 64 64">
    <path
      d="M9 24C13 12 22 7 32 7s19 5 23 17c-6-3-12-3-17 2-4-5-8-5-12 0-5-5-11-5-17-2Z"
      fill="currentColor"
    />
    <path d="m18 24 12 31m16-31L34 55M32 27v28" fill="none" stroke="currentColor" />
    <circle cx="32" cy="25" r="3.5" fill="var(--color-surface)" />
  </svg>
);

const ShieldMark = () => (
  <svg aria-hidden="true" focusable="false" viewBox="0 0 24 24">
    <path d="M12 3 19 6v5c0 4.6-2.8 8.1-7 10-4.2-1.9-7-5.4-7-10V6l7-3Z" />
    <path d="M12 8v4m0 4h.01" />
  </svg>
);

export const AppHeader = () => (
  <header className={styles.header}>
    <div className={styles.brand} aria-label="XC Forecast">
      <CanopyMark />
      <span>XC Forecast</span>
    </div>
    <span aria-hidden="true" className={styles.divider} />
    <span className={styles.currentSection}>Dashboard</span>
    <p className={styles.safetyContext}>
      <ShieldMark />
      <span>
        <strong>Decision support only</strong>
        <span className={styles.safetyDetail}>Not aviation weather</span>
      </span>
    </p>
  </header>
);
