import type { ForecastResponse } from "@paragliding-forecasts/contracts";
import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { ConfidenceIndicator } from "../../dashboard/components/ConfidenceIndicator.js";
import { formatInteger } from "../../dashboard/forecast-presentation.js";
import { InformationPopover } from "../../dashboard/components/ForecastInformation.js";
import { CloudbaseGuidance } from "./CloudbaseGuidance.js";
import { Pagination } from "../../../components/pagination/Pagination.js";
import { DashboardPanel } from "../../../components/dashboard-panel/DashboardPanel.js";
import {
  cloudbasePlotInsets,
  cloudbaseRegimeLabel,
  numericCloudbaseType,
} from "../cloudbase-chart.js";
import { defaultCloudbaseHour, formatSofiaHour } from "../forecast-detail-presentation.js";
import { informationPages, inputInformation } from "./ForecastDetailContent.js";
import styles from "./CloudbaseChart.module.scss";

const LazyCloudbasePlot = lazy(async () => {
  const { CloudbasePlot } = await import("./CloudbasePlot.js");
  return { default: CloudbasePlot };
});

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
  const daily = selectedHour === defaultCloudbaseHour(forecast) && hour.heightMslM !== null;
  const pages = [
    <div key="height" className={styles.heightSummary}>
      {daily ? <span className={styles.maximumBadge}>Daily maximum</span> : null}
      {hour.heightMslM === null ? (
        <strong className={styles.noHeight}>No numeric height.</strong>
      ) : (
        <>
          <strong className={styles.mslHeight}>
            {formatInteger(hour.heightMslM)} <span>m MSL</span>
          </strong>
          <div className={styles.aglHeights}>
            <span>
              {hour.heightSiteAglM === null ? "Unavailable" : formatInteger(hour.heightSiteAglM)} m
              site AGL
            </span>
            <span>
              {hour.heightModelAglM === null ? "Unavailable" : formatInteger(hour.heightModelAglM)}{" "}
              m model AGL
            </span>
          </div>
        </>
      )}
      <div className={styles.heightConfidence}>
        <ConfidenceIndicator
          compact
          adjacent
          accessibleLabel="Hourly confidence"
          confidence={{ level: hour.confidenceLevel ?? "unavailable", notes: [] }}
        />
      </div>
    </div>,
    ...informationPages([
      `${hour.reasonText} Code: ${hour.reasonCode}.${numericCloudbaseType(hour) === "conditional" ? " Conditional LCL is a conditional condensation level, not an estimated thermal top." : ""}`,
      `${formatSofiaHour(hour.validAtUtc)} Europe/Sofia · ${cloudbaseRegimeLabel(hour)}`,
      ...(hour.note ? [hour.note] : []),
      ...(context?.cloudbaseContext.flatMap(inputInformation) ?? []),
    ]),
  ];
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
  const controls = useRef<HTMLDivElement>(null);
  const [tooltip, setTooltip] = useState(false);
  const [pinned, setPinned] = useState(false);
  const [anchor, setAnchor] = useState<DOMRect | undefined>();
  const hours = forecast.cloudbaseHours;
  const selectedIndex = Math.max(
    0,
    hours.findIndex((hour) => hour.validAtUtc === selectedHour),
  );
  const select = (i: number, button?: HTMLElement) => {
    const hour = hours[i];
    if (!hour) return;
    onSelectHour(hour.validAtUtc);
    if (button) setAnchor(button.getBoundingClientRect());
  };
  return (
    <DashboardPanel
      className={styles.panel}
      headingId="hourly-cloudbase-heading"
      title="Hourly cloudbase"
      accessory={
        <div className={styles.chartAccessory}>
          <span className={styles.zone}>10:00–20:00 Europe/Sofia · m MSL</span>
          <InformationPopover
            label="Hourly cloudbase information"
            regionLabel="Hourly cloudbase guide"
            fitViewport
          >
            <CloudbaseGuidance />
          </InformationPopover>
        </div>
      }
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
        <div className={styles.plot}>
          <Suspense
            fallback={
              <div className={styles.loading} role="status">
                Loading hourly chart…
              </div>
            }
          >
            <LazyCloudbasePlot
              hours={hours}
              maximum={defaultCloudbaseHour(forecast)}
              selectedHour={selectedHour}
            />
          </Suspense>
          <div
            className={styles.hourControls}
            ref={controls}
            role="group"
            aria-label="Select cloudbase hour"
            style={cloudbasePlotInsets}
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
                        ? Math.min(hours.length - 1, i + 1)
                        : event.key === "Home"
                          ? 0
                          : event.key === "End"
                            ? hours.length - 1
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
