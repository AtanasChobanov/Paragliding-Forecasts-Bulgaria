import type { CloudbaseHour } from "@paragliding-forecasts/contracts";
import { useId } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  XAxis,
  YAxis,
  usePlotArea,
  useXAxisScale,
} from "recharts";

import { formatInteger } from "../../dashboard/forecast-presentation.js";
import {
  cloudbasePlotInsets,
  cloudbaseScale,
  cloudbaseSegments,
  numericCloudbaseType,
} from "../cloudbase-chart.js";
import { formatSofiaHour } from "../forecast-detail-presentation.js";
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
type NumericType = "estimated" | "conditional";
interface ChartRow {
  readonly hour: CloudbaseHour;
  readonly index: number;
}

const HeightMarker = ({
  cx,
  cy,
  index,
  hours,
  type,
  maximum,
  selectedHour,
}: {
  readonly cx?: number;
  readonly cy?: number;
  readonly index?: number;
  readonly hours: readonly CloudbaseHour[];
  readonly type: NumericType;
  readonly maximum: string;
  readonly selectedHour: string;
}) => {
  const hour = index === undefined ? undefined : hours[index];
  if (
    typeof cx !== "number" ||
    typeof cy !== "number" ||
    !hour ||
    numericCloudbaseType(hour) !== type
  )
    return null;
  const daily = hour.validAtUtc === maximum;
  return (
    <g data-numeric-marker={type} data-daily-maximum={daily || undefined}>
      {hour.validAtUtc === selectedHour ? (
        <circle cx={cx} cy={cy} r={9} fill={colors[type]} opacity={0.14} />
      ) : null}
      {daily ? (
        <circle
          cx={cx}
          cy={cy}
          r={7}
          fill="var(--color-surface)"
          stroke="var(--color-heading)"
          strokeWidth={1.5}
        />
      ) : null}
      {type === "estimated" ? (
        <circle cx={cx} cy={cy} r={3.5} fill={colors[type]} />
      ) : (
        <path d={`M${String(cx)} ${String(cy - 4)}l4 4-4 4-4-4Z`} fill={colors[type]} />
      )}
    </g>
  );
};

// Recharts supplies the coordinates, keeping the regime band aligned with its axes.
const RegimeBand = ({
  hours,
  patternId,
  numeric,
}: {
  readonly hours: readonly CloudbaseHour[];
  readonly patternId: string;
  readonly numeric: boolean;
}) => {
  const plot = usePlotArea();
  const xScale = useXAxisScale();
  if (!plot || !xScale) return null;
  const cellWidth = plot.width / hours.length;
  return (
    <g>
      {hours.map((hour, index) => {
        const x = xScale(index);
        if (x === undefined) return null;
        const type = numericCloudbaseType(hour);
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
          <g
            key={hour.validAtUtc}
            data-regime={hour.regime}
            data-chart-regime-hour={hour.validAtUtc}
          >
            <rect
              x={x - cellWidth / 2}
              y={plot.y + plot.height + 4}
              width={cellWidth}
              height={14}
              fill={hour.regime === "missing" ? `url(#${patternId})` : colors[hour.regime]}
              opacity={0.15}
              stroke={colors[hour.regime]}
              strokeDasharray={hour.regime === "missing" ? "2 2" : undefined}
            />
            <text
              x={x}
              y={plot.y + plot.height + 15}
              textAnchor="middle"
              fill={type ? colors[type] : colors[hour.regime]}
            >
              {mark}
            </text>
          </g>
        );
      })}
      {!numeric ? (
        <text
          x={plot.x + plot.width / 2}
          y={plot.y + plot.height / 2}
          textAnchor="middle"
          className={styles.noHeights}
        >
          No numeric cloudbase heights published
        </text>
      ) : null}
    </g>
  );
};

export const CloudbasePlot = ({
  hours,
  maximum,
  selectedHour,
}: {
  readonly hours: readonly CloudbaseHour[];
  readonly maximum: string;
  readonly selectedHour: string;
}) => {
  const id = useId().replaceAll(":", "");
  const segments = cloudbaseSegments(hours);
  const scale = cloudbaseScale(hours);
  const numeric = hours.some((hour) => hour.heightMslM !== null);
  const data: ChartRow[] = hours.map((hour, index) => ({ hour, index }));
  return (
    <ResponsiveContainer width="100%" height="100%" minWidth={0}>
      <ComposedChart
        data={data}
        margin={{ top: 9, right: cloudbasePlotInsets.right, bottom: 0, left: 0 }}
        // The adjacent DOM controls provide one roving keyboard target for every hour,
        // including hours with no numeric point. Avoid a second, competing focus path.
        accessibilityLayer={false}
        role="img"
        aria-label="Hourly cloudbase heights in metres MSL"
      >
        <defs>
          {segments
            .filter((segment) => segment.indices.length > 1)
            .map((segment, index) => (
              <linearGradient
                key={index}
                id={`${id}-segment-${String(index)}`}
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
                <stop offset="100%" stopColor={colors[segment.type]} stopOpacity={0} />
              </linearGradient>
            ))}
          <pattern id={`${id}-missing`} width={6} height={6} patternUnits="userSpaceOnUse">
            <path d="M0 6L6 0" stroke="var(--color-border-strong)" strokeWidth={1} />
          </pattern>
        </defs>
        {numeric ? (
          <CartesianGrid vertical={false} stroke="var(--color-border)" strokeDasharray="3 4" />
        ) : null}
        <XAxis
          dataKey="index"
          type="number"
          domain={[-0.5, hours.length - 0.5]}
          ticks={hours.map((_, i) => i)}
          height={34}
          axisLine={false}
          tickLine={false}
          tickMargin={20}
          minTickGap={12}
          tick={{ fill: "var(--color-text-secondary)" }}
          tickFormatter={(index: number) => {
            const hour = hours[index];
            return hour ? formatSofiaHour(hour.validAtUtc) : "";
          }}
        />
        <YAxis
          width={cloudbasePlotInsets.left}
          domain={[scale.min, scale.max]}
          allowDataOverflow
          ticks={Array.from({ length: 5 }, (_, i) => scale.min + ((scale.max - scale.min) * i) / 4)}
          tick={numeric ? { fontSize: 10, fill: "var(--color-text-secondary)" } : false}
          axisLine={false}
          tickLine={false}
          tickFormatter={formatInteger}
        />
        {segments
          .filter((segment) => segment.indices.length > 1)
          .map((segment, index) => (
            <Area
              key={index}
              type="linear"
              dataKey={(row: ChartRow) =>
                segment.indices.includes(row.index) ? row.hour.heightMslM : null
              }
              baseValue={scale.min}
              connectNulls={false}
              stroke="none"
              fill={`url(#${id}-segment-${String(index)})`}
              fillOpacity={1}
              dot={false}
              activeDot={false}
              isAnimationActive={false}
              data-gradient-segment={segment.type}
            />
          ))}
        {segments.map((segment, index) => (
          <Line
            key={index}
            type="linear"
            dataKey={(row: ChartRow) =>
              segment.indices.includes(row.index) ? row.hour.heightMslM : null
            }
            connectNulls={false}
            stroke={colors[segment.type]}
            strokeWidth={2}
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeDasharray={segment.type === "conditional" ? "6 4" : "0"}
            activeDot={false}
            isAnimationActive={false}
            data-segment={segment.type}
            dot={
              <HeightMarker
                hours={hours}
                type={segment.type}
                maximum={maximum}
                selectedHour={selectedHour}
              />
            }
          />
        ))}
        <ReferenceLine
          x={hours.findIndex((hour) => hour.validAtUtc === selectedHour)}
          stroke="var(--color-heading)"
          strokeDasharray="2 3"
          strokeOpacity={0.35}
        />
        <RegimeBand hours={hours} patternId={`${id}-missing`} numeric={numeric} />
      </ComposedChart>
    </ResponsiveContainer>
  );
};
