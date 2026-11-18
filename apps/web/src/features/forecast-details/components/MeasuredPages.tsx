import { useLayoutEffect, useRef, useState, type ReactNode } from "react";
import styles from "./ForecastDetailContent.module.scss";

// Measure available body space, including text zoom. No section needs a scrollbar.
export const MeasuredPages = <T,>({
  items,
  maxRows,
  render,
  label,
}: {
  readonly items: readonly T[];
  readonly maxRows: number;
  readonly render: (item: T, index: number) => ReactNode;
  readonly label: string;
}) => {
  const body = useRef<HTMLDivElement>(null);
  const [capacity, setCapacity] = useState(1);
  const [page, setPage] = useState(0);
  const pages = Math.max(1, Math.ceil(items.length / capacity));
  const current = Math.min(page, pages - 1);
  const start = current * capacity;

  useLayoutEffect(() => {
    const measure = () => {
      if (!body.current) return;
      const row = body.current.querySelector<HTMLElement>("[data-page-row]");
      const height = row?.getBoundingClientRect().height ?? 28;
      const room = body.current.getBoundingClientRect().height;
      if (room > 0 && height > 0)
        setCapacity(Math.min(maxRows, Math.max(1, Math.floor(room / height))));
    };
    measure();
    const observer = new ResizeObserver(measure);
    if (body.current) observer.observe(body.current);
    window.addEventListener("resize", measure);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", measure);
    };
  }, [maxRows]);

  return (
    <div className={styles.measuredPages}>
      <div className={styles.pageRows} ref={body}>
        {items.slice(start, start + capacity).map((item, index) => (
          <div data-page-row key={start + index}>
            {render(item, start + index)}
          </div>
        ))}
        {items.length === 0 ? (
          <p className={styles.empty}>No distinct driver was published</p>
        ) : null}
      </div>
      <nav aria-label={`${label} pagination`} className={styles.pagination}>
        <button
          disabled={current === 0}
          type="button"
          onClick={() => {
            setPage(current - 1);
          }}
        >
          Previous
        </button>
        <span>
          {items.length
            ? `${String(start + 1)}–${String(Math.min(items.length, start + capacity))} of ${String(items.length)}`
            : "0 of 0"}
        </span>
        <button
          disabled={current === pages - 1}
          type="button"
          onClick={() => {
            setPage(current + 1);
          }}
        >
          Next
        </button>
      </nav>
    </div>
  );
};
