import type { ForecastResponse } from "@paragliding-forecasts/contracts";
import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Pagination } from "../../../components/pagination/Pagination.js";
import { DashboardPanel } from "../../../components/dashboard-panel/DashboardPanel.js";
import {
  cloudbaseRegimeLabel,
  cloudbaseScale,
  cloudbaseSegments,
  numericCloudbaseType,
} from "../cloudbase-chart.js";
import { defaultCloudbaseHour, formatSofiaHour } from "../forecast-detail-presentation.js";
import { informationPages, inputInformation } from "./ForecastDetailContent.js";
import styles from "./CloudbaseChart.module.scss";

const colors = {
  estimated: "var(--color-primary)",
  conditional: "var(--color-warning)",
  blue: "var(--color-accent-sky)",
  other_cloud: "var(--color-text-secondary)",
  indeterminate: "var(--color-warning)",
  missing: "var(--color-border-strong)",
  cumulus: "var(--color-primary)",
};

const HourTooltip = ({
  forecast,
  selectedHour,
  anchor,
  onClose,
}: {
  readonly forecast: ForecastResponse;
  readonly selectedHour: string;
  readonly anchor: DOMRect;
  readonly onClose: () => void;
}) => {
  const [page, setPage] = useState(0);
  const panel = useRef<HTMLDivElement>(null);
  const hour = forecast.cloudbaseHours.find((hour) => hour.validAtUtc === selectedHour);
  const context = forecast.forecastInputs.hourlyContext.find(
    (hour) => hour.validAtUtc === selectedHour,
  );
  useEffect(() => {
    const key = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    const outside = (event: PointerEvent) => {
      if (
        event.target instanceof Node &&
        !panel.current?.contains(event.target) &&
        !(event.target instanceof Element && event.target.closest("[data-chart-hour]"))
      )
        onClose();
    };
    document.addEventListener("keydown", key);
    document.addEventListener("pointerdown", outside);
    return () => {
      document.removeEventListener("keydown", key);
      document.removeEventListener("pointerdown", outside);
    };
  }, [onClose]);
  if (!hour) return null;
  const pages = informationPages([
    `${formatSofiaHour(hour.validAtUtc)} Europe/Sofia · ${cloudbaseRegimeLabel(hour)}${selectedHour === defaultCloudbaseHour(forecast) && hour.heightMslM !== null ? " · Daily maximum" : ""}. ${hour.heightMslM === null ? "No numeric height." : `${String(hour.heightMslM)} m MSL; ${String(hour.heightModelAglM)} m model AGL; ${String(hour.heightSiteAglM)} m site AGL.`} ${hour.confidenceLevel ?? "Unavailable"} confidence.`,
    `${hour.reasonText} Code: ${hour.reasonCode}.${numericCloudbaseType(hour) === "conditional" ? " Conditional LCL is a conditional condensation level, not an estimated thermal top." : ""}`,
    ...(hour.note ? [hour.note] : []),
    ...(context?.cloudbaseContext.flatMap(inputInformation) ?? []),
  ]);
  const above = anchor.top > window.innerHeight / 2;
  return createPortal(
    <div
      className={styles.tooltip}
      aria-label="Cloudbase hour information"
      role="region"
      ref={panel}
      style={{
        left: Math.max(
          8,
          Math.min(anchor.left, window.innerWidth - Math.min(390, window.innerWidth - 16) - 8),
        ),
        top: above ? anchor.top - 8 : anchor.bottom + 8,
        transform: above ? "translateY(-100%)" : undefined,
      }}
    >
      {pages[page]}
      <div className={styles.tooltipControls}>
        <Pagination
          label="Cloudbase tooltip pages"
          page={page}
          pages={pages.length}
          onPageChange={setPage}
        />
        <button
          className={styles.closeTooltip}
          type="button"
          aria-label="Close cloudbase tooltip"
          onClick={onClose}
        >
          ×
        </button>
      </div>
    </div>,
    document.body,
  );
};

export const CloudbaseChart = ({
  forecast,
  selectedHour,
  onSelectHour,
}: {
  readonly forecast: ForecastResponse;
  readonly selectedHour: string;
  readonly onSelectHour: (at: string) => void;
}) => {
  const chart = useRef<HTMLDivElement>(null);
  const controls = useRef<HTMLDivElement>(null);
  const gradientId = useId().replaceAll(":", "");
  const [size, setSize] = useState({ width: 1000, height: 180 });
  const [tooltip, setTooltip] = useState(false);
  const [pinned, setPinned] = useState(false);
  const [anchor, setAnchor] = useState<DOMRect | undefined>();
  const hours = forecast.cloudbaseHours;
  const selectedIndex = Math.max(
    0,
    hours.findIndex((hour) => hour.validAtUtc === selectedHour),
  );
  const maximum = defaultCloudbaseHour(forecast);
  const scale = cloudbaseScale(hours);
  const segments = cloudbaseSegments(hours);
  useLayoutEffect(() => {
    const measure = () => {
      const rect = chart.current?.getBoundingClientRect();
      if (rect && rect.width > 0 && rect.height > 0)
        setSize({ width: rect.width, height: rect.height });
    };
    measure();
    const observer = new ResizeObserver(measure);
    if (chart.current) observer.observe(chart.current);
    return () => {
      observer.disconnect();
    };
  }, []);
  const left = 44,
    right = 10,
    top = 4,
    bottom = 28;
  const width = Math.max(1, size.width - left - right),
    height = Math.max(1, size.height - top - bottom);
  const x = (i: number) => left + (i * width) / 10;
  const y = (v: number) => top + height - ((v - scale.min) / (scale.max - scale.min)) * height;
  const select = (i: number, button?: HTMLElement) => {
    const hour = hours[i];
    if (!hour) return;
    onSelectHour(hour.validAtUtc);
    if (button) setAnchor(button.getBoundingClientRect());
  };
  const numeric = hours.some((hour) => hour.heightMslM !== null);
  return (
    <DashboardPanel
      className={styles.panel}
      headingId="hourly-cloudbase-heading"
      title="Hourly cloudbase"
      accessory={<span className={styles.zone}>10:00–20:00 Europe/Sofia · m MSL</span>}
    >
      <div className={styles.chartContent}>
        <div aria-label="Cloudbase legend" className={styles.legend}>
          <span data-regime="cumulus">● Estimated</span>
          <span data-regime="conditional">◇ ┄ Conditional LCL</span>
          <span data-regime="blue">B Blue</span>
          <span data-regime="other_cloud">O Other cloud</span>
          <span data-regime="indeterminate">? Uncertain</span>
          <span data-regime="missing">▧ Unavailable</span>
        </div>
        <div className={styles.plot} ref={chart}>
          <svg
            aria-label="Hourly cloudbase heights in metres MSL"
            role="img"
            viewBox={`0 0 ${String(size.width)} ${String(size.height)}`}
            preserveAspectRatio="none"
          >
            <defs>
              {segments
                .filter((s) => s.indices.length > 1)
                .map((segment, index) => (
                  <linearGradient
                    id={`${gradientId}-${String(index)}`}
                    key={index}
                    x1="0"
                    x2="0"
                    y1="0"
                    y2="1"
                  >
                    <stop
                      offset="0%"
                      stopColor={colors[segment.type]}
                      stopOpacity={segment.type === "estimated" ? 0.22 : 0.12}
                    />
                    <stop offset="100%" stopColor={colors[segment.type]} stopOpacity="0" />
                  </linearGradient>
                ))}
              <pattern
                id={`${gradientId}-missing`}
                width="6"
                height="6"
                patternUnits="userSpaceOnUse"
              >
                <path d="M0 6L6 0" stroke="var(--color-border-strong)" strokeWidth="1" />
              </pattern>
            </defs>
            {numeric
              ? Array.from({ length: 5 }, (_, i) => {
                  const value = scale.min + ((scale.max - scale.min) * i) / 4;
                  return (
                    <g key={i}>
                      <line
                        x1={left}
                        x2={size.width - right}
                        y1={y(value)}
                        y2={y(value)}
                        className={styles.grid}
                      />
                      <text x={left - 5} y={y(value) + 3} textAnchor="end">
                        {Math.round(value)}
                      </text>
                    </g>
                  );
                })
              : null}
            {segments
              .filter((s) => s.indices.length > 1)
              .map((segment, index) => {
                const points = segment.indices.map((i) => {
                  const h = hours[i];
                  return `${String(x(i))},${String(y(h?.heightMslM ?? 0))}`;
                });
                const first = segment.indices[0] ?? 0,
                  last = segment.indices.at(-1) ?? first;
                return (
                  <g key={index} data-segment={segment.type}>
                    <polygon
                      data-gradient-segment={segment.type}
                      points={`${String(x(first))},${String(y(scale.min))} ${points.join(" ")} ${String(x(last))},${String(y(scale.min))}`}
                      fill={`url(#${gradientId}-${String(index)})`}
                    />
                    <polyline
                      points={points.join(" ")}
                      fill="none"
                      stroke={colors[segment.type]}
                      strokeWidth="2"
                      strokeDasharray={segment.type === "conditional" ? "6 4" : undefined}
                    />
                  </g>
                );
              })}
            {hours.map((hour, i) => {
              const type = numericCloudbaseType(hour);
              const px = x(i),
                py = y(hour.heightMslM ?? scale.min);
              const daily = hour.validAtUtc === maximum && hour.heightMslM !== null;
              const mark =
                type === "estimated"
                  ? "●"
                  : type === "conditional"
                    ? "◇"
                    : hour.regime === "blue"
                      ? "B"
                      : hour.regime === "other_cloud"
                        ? "O"
                        : hour.regime === "missing"
                          ? "▧"
                          : "?";
              return (
                <g key={hour.validAtUtc} data-regime={hour.regime}>
                  {hour.validAtUtc === selectedHour ? (
                    <line
                      x1={px}
                      x2={px}
                      y1={top}
                      y2={top + height + 18}
                      stroke="var(--color-heading)"
                      strokeDasharray="2 3"
                      opacity="0.4"
                    />
                  ) : null}
                  {type ? (
                    <g data-numeric-marker={type} data-daily-maximum={daily || undefined}>
                      {daily ? (
                        <circle
                          cx={px}
                          cy={py}
                          r="7"
                          fill="none"
                          stroke="var(--color-heading)"
                          strokeWidth="1.5"
                        />
                      ) : null}
                      {type === "estimated" ? (
                        <circle cx={px} cy={py} r="3.5" fill={colors[type]} />
                      ) : (
                        <path
                          d={`M${String(px)} ${String(py - 4)}l4 4-4 4-4-4Z`}
                          fill={colors[type]}
                        />
                      )}
                    </g>
                  ) : null}
                  <rect
                    x={Math.max(left - 8, px - width / 22)}
                    y={top + height + 5}
                    width={Math.min(width / 11, size.width - right - px + width / 22)}
                    height="14"
                    fill={
                      hour.regime === "missing"
                        ? `url(#${gradientId}-missing)`
                        : colors[hour.regime]
                    }
                    opacity="0.15"
                    stroke={colors[hour.regime]}
                    strokeDasharray={hour.regime === "missing" ? "2 2" : undefined}
                  />
                  <text
                    x={px}
                    y={top + height + 16}
                    textAnchor="middle"
                    fill={type ? colors[type] : colors[hour.regime]}
                  >
                    {mark}
                  </text>
                  {size.width > 600 || i % 2 === 0 ? (
                    <text x={px} y={size.height - 3} textAnchor="middle">
                      {formatSofiaHour(hour.validAtUtc).slice(0, 2)}
                    </text>
                  ) : null}
                </g>
              );
            })}
            {!numeric ? (
              <text
                x={left + width / 2}
                y={top + height / 2}
                textAnchor="middle"
                className={styles.noHeights}
              >
                No numeric cloudbase heights published
              </text>
            ) : null}
          </svg>
          <div
            className={styles.hourControls}
            ref={controls}
            role="group"
            aria-label="Select cloudbase hour"
            style={{ left: left - 8, right: right - 8 }}
          >
            {hours.map((hour, i) => (
              <button
                key={hour.validAtUtc}
                data-chart-hour={hour.validAtUtc}
                type="button"
                tabIndex={i === selectedIndex ? 0 : -1}
                aria-label={`${formatSofiaHour(hour.validAtUtc)} Sofia · ${cloudbaseRegimeLabel(hour)}`}
                aria-pressed={hour.validAtUtc === selectedHour}
                onFocus={(event) => {
                  select(i, event.currentTarget);
                  setTooltip(true);
                }}
                onPointerEnter={(event) => {
                  if (event.pointerType === "mouse" && !pinned) {
                    select(i, event.currentTarget);
                    setTooltip(true);
                  }
                }}
                onPointerLeave={() => {
                  if (!pinned) setTooltip(false);
                }}
                onBlur={() => {
                  if (!pinned) setTooltip(false);
                }}
                onClick={(event) => {
                  select(i, event.currentTarget);
                  setPinned(true);
                  setTooltip(true);
                }}
                onKeyDown={(event) => {
                  const target =
                    event.key === "ArrowLeft"
                      ? Math.max(0, i - 1)
                      : event.key === "ArrowRight"
                        ? Math.min(10, i + 1)
                        : event.key === "Home"
                          ? 0
                          : event.key === "End"
                            ? 10
                            : undefined;
                  if (target !== undefined) {
                    event.preventDefault();
                    select(target);
                    controls.current?.querySelectorAll("button")[target]?.focus();
                  }
                }}
              >
                <span className="visually-hidden">{formatSofiaHour(hour.validAtUtc)}</span>
              </button>
            ))}
          </div>
        </div>
      </div>
      {tooltip && anchor ? (
        <HourTooltip
          key={selectedHour}
          forecast={forecast}
          selectedHour={selectedHour}
          anchor={anchor}
          onClose={() => {
            setTooltip(false);
            setPinned(false);
          }}
        />
      ) : null}
    </DashboardPanel>
  );
};
