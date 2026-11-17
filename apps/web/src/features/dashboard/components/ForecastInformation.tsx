import type {
  AvailableForecastSummary,
  DashboardForecastOutputs,
} from "@paragliding-forecasts/contracts";
import { type CSSProperties, useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { formatConfidence, formatDataStatus, presentCloudbase } from "../forecast-presentation.js";
import styles from "./ForecastInformation.module.scss";

interface ForecastInformationProps {
  readonly siteName: string;
  readonly summary: AvailableForecastSummary;
}

const dateTimeOptions: Intl.DateTimeFormatOptions = {
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
  timeZoneName: "short",
};
const sofiaTime = new Intl.DateTimeFormat("en-GB", {
  ...dateTimeOptions,
  timeZone: "Europe/Sofia",
});
const utcTime = new Intl.DateTimeFormat("en-GB", { ...dateTimeOptions, timeZone: "UTC" });

const metricNotes = (outputs: DashboardForecastOutputs) => {
  return [
    ["100+ km chance", outputs.chance100KmPct],
    ["200+ km chance", outputs.chance200KmPct],
    ["300+ km chance", outputs.chance300KmPct],
    [presentCloudbase(outputs.cloudbase).label, outputs.cloudbase],
    ["OD risk", outputs.overdevelopmentRisk],
  ] as const;
};

const ForecastInformationContent = ({ siteName, summary }: ForecastInformationProps) => {
  const { metadata, outputs } = summary;
  const risk = outputs.overdevelopmentRisk;

  return (
    <>
      <h3>{siteName}</h3>
      <dl className={styles.metadata}>
        <dt>Source</dt>
        <dd>{metadata.source}</dd>
        <dt>Published (Sofia)</dt>
        <dd>
          <time dateTime={summary.generatedAt}>
            {sofiaTime.format(new Date(summary.generatedAt))}
          </time>
        </dd>
        {metadata.mode === "sqlite" ? (
          <>
            <dt>GFS cycle</dt>
            <dd>
              <time dateTime={metadata.cycleAtUtc}>
                {utcTime.format(new Date(metadata.cycleAtUtc))}
              </time>
            </dd>
            <dt>Horizon</dt>
            <dd>
              D+{metadata.horizonDays}
              {metadata.fromPreviousIssue ? " · From previous issue" : ""}
            </dd>
            <dt>XC model</dt>
            <dd>{metadata.xcModelId}</dd>
            <dt>Cloudbase method</dt>
            <dd>{metadata.cloudbaseMethodVersion}</dd>
            <dt>OD policy</dt>
            <dd>{metadata.overdevelopmentPolicyVersion}</dd>
          </>
        ) : (
          <>
            <dt>Mode</dt>
            <dd>Mock data</dd>
            <dt>Version</dt>
            <dd>{metadata.version}</dd>
          </>
        )}
      </dl>
      <dl className={styles.metrics}>
        {metricNotes(outputs).map(([label, metric]) => (
          <div key={label}>
            <dt>{label}</dt>
            <dd>
              <strong>
                {formatDataStatus(metric.dataStatus)} ·{" "}
                {formatConfidence(metric.confidence?.level ?? "unavailable")}
              </strong>
              {metric.dataStatus === "missing" ? (
                <>
                  <p>{metric.missingReason}</p>
                  {metric.confidenceNote ? <p>{metric.confidenceNote}</p> : null}
                </>
              ) : metric.confidence.note ? (
                <p>{metric.confidence.note}</p>
              ) : null}
              {metric.limitationsNote ? <p>{metric.limitationsNote}</p> : null}
              {label === "OD risk" && risk.dataStatus !== "missing" && risk.score !== undefined ? (
                <p>OD score {risk.score} / 100</p>
              ) : null}
            </dd>
          </div>
        ))}
      </dl>
    </>
  );
};

export const ForecastInformation = ({ siteName, summary }: ForecastInformationProps) => {
  const panelId = useId();
  const button = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const hideTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const [open, setOpen] = useState(false);
  const [pinned, setPinned] = useState(false);
  const [position, setPosition] = useState<CSSProperties>({});

  const cancelHide = () => {
    clearTimeout(hideTimer.current);
  };
  const show = () => {
    cancelHide();
    setOpen(true);
  };
  const scheduleHide = () => {
    cancelHide();
    if (!pinned) {
      hideTimer.current = setTimeout(() => {
        if (
          !button.current?.matches(":focus-visible") &&
          !panel.current?.contains(document.activeElement)
        ) {
          setOpen(false);
        }
      }, 120);
    }
  };

  useEffect(
    () => () => {
      clearTimeout(hideTimer.current);
    },
    [],
  );

  useLayoutEffect(() => {
    if (!open) {
      return;
    }

    const positionPanel = () => {
      if (button.current === null || panel.current === null) {
        return;
      }
      const anchor = button.current.getBoundingClientRect();
      const inset = 8;
      const viewportWidth = document.documentElement.clientWidth;
      const below = window.innerHeight - anchor.bottom - 2 * inset;
      const above = anchor.top - 2 * inset;
      const placeAbove = above > below;
      setPosition({
        left: Math.max(
          inset,
          Math.min(anchor.left, viewportWidth - panel.current.offsetWidth - inset),
        ),
        top: placeAbove ? anchor.top - inset : anchor.bottom + inset,
        transform: placeAbove ? "translateY(-100%)" : undefined,
        maxHeight: Math.max(0, placeAbove ? above : below),
      });
    };

    positionPanel();
    window.addEventListener("resize", positionPanel);
    window.addEventListener("scroll", positionPanel, true);
    return () => {
      window.removeEventListener("resize", positionPanel);
      window.removeEventListener("scroll", positionPanel, true);
    };
  }, [open]);

  useEffect(() => {
    if (!open) {
      return;
    }

    const dismiss = () => {
      clearTimeout(hideTimer.current);
      setOpen(false);
      setPinned(false);
    };
    const onPointerDown = (event: PointerEvent) => {
      if (
        event.target instanceof Node &&
        !button.current?.contains(event.target) &&
        !panel.current?.contains(event.target)
      ) {
        dismiss();
      }
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        if (panel.current?.contains(document.activeElement)) {
          button.current?.focus();
        }
        dismiss();
      }
    };

    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <>
      <button
        aria-controls={panelId}
        aria-expanded={open}
        aria-label="Forecast information"
        className={styles.trigger}
        ref={button}
        type="button"
        onBlur={(event) => {
          if (!panel.current?.contains(event.relatedTarget)) {
            scheduleHide();
          }
        }}
        onClick={(event) => {
          cancelHide();
          setOpen(!pinned);
          setPinned(!pinned);
          if (!pinned && event.detail === 0) {
            requestAnimationFrame(() => panel.current?.focus());
          }
        }}
        onFocus={show}
        onPointerEnter={(event) => {
          if (event.pointerType === "mouse") {
            show();
          }
        }}
        onPointerLeave={scheduleHide}
      >
        <svg aria-hidden="true" focusable="false" viewBox="0 0 24 24">
          <circle cx="12" cy="12" r="9" />
          <path d="M12 11v6m0-10h.01" />
        </svg>
      </button>
      {createPortal(
        <div
          aria-label={`Forecast information for ${siteName}`}
          className={styles.popup}
          hidden={!open}
          id={panelId}
          ref={panel}
          role="region"
          style={position}
          tabIndex={-1}
          onPointerEnter={cancelHide}
          onPointerLeave={scheduleHide}
        >
          {open ? <ForecastInformationContent siteName={siteName} summary={summary} /> : null}
        </div>,
        document.body,
      )}
    </>
  );
};
