import styles from "./Pagination.module.scss";

export const Pagination = ({
  label,
  page,
  pages,
  onPageChange,
}: {
  readonly label: string;
  readonly page: number;
  readonly pages: number;
  readonly onPageChange: (page: number) => void;
}) => (
  <nav aria-label={label} className={styles.pagination}>
    <button
      type="button"
      aria-label="Previous"
      disabled={page === 0}
      onClick={() => {
        onPageChange(page - 1);
      }}
    >
      <svg aria-hidden="true" viewBox="0 0 20 20">
        <path d="m12 5-5 5 5 5" />
      </svg>
    </button>
    <span aria-live="polite" aria-atomic="true">
      {page + 1} of {pages}
    </span>
    <button
      type="button"
      aria-label="Next"
      disabled={page >= pages - 1}
      onClick={() => {
        onPageChange(page + 1);
      }}
    >
      <svg aria-hidden="true" viewBox="0 0 20 20">
        <path d="m8 5 5 5-5 5" />
      </svg>
    </button>
  </nav>
);
