import type { CloudbaseHour } from "@paragliding-forecasts/contracts";

export const numericCloudbaseType = (hour: CloudbaseHour) =>
  hour.heightMslM === null
    ? null
    : hour.regime === "cumulus"
      ? "estimated"
      : hour.regime === "indeterminate"
        ? "conditional"
        : null;
export const cloudbaseSegments = (hours: readonly CloudbaseHour[]) => {
  const segments: { type: "estimated" | "conditional"; indices: number[] }[] = [];
  hours.forEach((hour, i) => {
    const type = numericCloudbaseType(hour);
    if (!type) return;
    const last = segments.at(-1);
    if (last?.type === type && last.indices.at(-1) === i - 1) last.indices.push(i);
    else segments.push({ type, indices: [i] });
  });
  return segments;
};
export const cloudbaseScale = (hours: readonly CloudbaseHour[]) => {
  const values = hours.flatMap((hour) => (hour.heightMslM === null ? [] : [hour.heightMslM]));
  return {
    min: Math.min(0, Math.floor(Math.min(...values, 0) / 500) * 500),
    max: Math.max(500, Math.ceil(Math.max(...values, 0) / 500) * 500),
  };
};
export const cloudbaseRegimeLabel = (hour: CloudbaseHour) =>
  hour.regime === "cumulus"
    ? "Estimated cloudbase"
    : hour.regime === "indeterminate"
      ? hour.heightMslM === null
        ? "Uncertain"
        : "Conditional LCL"
      : hour.regime === "other_cloud"
        ? "Other cloud"
        : hour.regime === "missing"
          ? "Unavailable"
          : "Blue";
