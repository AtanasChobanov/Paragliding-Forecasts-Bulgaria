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

const BellMark = () => (
  <svg aria-hidden="true" className={styles.bell} focusable="false" viewBox="0 0 24 24">
    <path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9Z" />
    <path d="M10 21h4" />
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
    <BellMark />
    <p className="visually-hidden">
      <strong>Decision support only</strong>
      <span>Not aviation weather</span>
    </p>
  </header>
);
