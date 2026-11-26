import { requirePublishedValue } from "./require-published-value.js";
import {
  sofiaFlyingHours,
  xcInputInventory,
  type ForecastDetailInputs,
  type ForecastInputRow,
} from "@paragliding-forecasts/contracts";
import type { DatabaseSync } from "node:sqlite";
import { z } from "zod";

import { convectionInputs, heatingInputs, surfaceInputs } from "./forecast-input-catalogue.js";

export type SqlRow = Record<string, unknown>;
const id = (row: SqlRow) => z.number().int().positive().parse(row.id);
const string = (value: unknown) => z.string().parse(value);
export const numberOrNull = (value: unknown) => z.number().nullable().parse(value);
const presentQuality = new Set(["real", "derived"]);

type InputSpec = Pick<
  ForecastInputRow,
  "key" | "label" | "group" | "scope" | "unit" | "statistic"
> &
  Partial<ForecastInputRow>;

export class SqliteForecastInputs {
  readonly inputs: ForecastDetailInputs;
  readonly provenance: readonly SqlRow[];
  readonly resolved: ForecastInputRow[] = [];
  readonly validTimes = new Map<number, string>();

  constructor(database: DatabaseSync, snapshotId: number, date: string) {
    const snapshot = database
      .prepare("SELECT * FROM weather_daily_feature_snapshots WHERE id = ?")
      .get(snapshotId);
    if (!snapshot) throw new Error("Published snapshot is missing.");
    const layers = database
      .prepare(
        "SELECT * FROM weather_daily_feature_profile_layers WHERE daily_feature_snapshot_id = ? ORDER BY layer_base_agl_m",
      )
      .all(snapshotId);
    if (
      layers.length !== 2 ||
      layers[0]?.layer_base_agl_m !== 0 ||
      layers[0].layer_top_agl_m !== 1500 ||
      layers[1]?.layer_base_agl_m !== 1500 ||
      layers[1].layer_top_agl_m !== 3000
    ) {
      throw new Error("Published snapshot requires its two exact profile layers.");
    }
    const samples = database
      .prepare(
        `SELECT s.*, v.valid_at_utc, v.product_run_id
      FROM weather_daily_feature_snapshot_inputs i
      JOIN weather_point_samples s ON s.id = i.weather_point_sample_id
      JOIN weather_product_valid_times v ON v.id = s.product_valid_time_id
      WHERE i.daily_feature_snapshot_id = ? ORDER BY v.valid_at_utc`,
      )
      .all(snapshotId);
    const ingestion = database
      .prepare("SELECT product_run_id FROM weather_ingestion_runs WHERE id = ?")
      .get(z.number().parse(snapshot.ingestion_run_id));
    if (
      samples.some(
        (s) =>
          s.ingestion_run_id !== snapshot.ingestion_run_id ||
          s.point_footprint_id !== snapshot.point_footprint_id ||
          s.product_run_id !== ingestion?.product_run_id,
      )
    )
      throw new Error("Snapshot input belongs to a different weather graph.");
    const hours = sofiaFlyingHours(date);
    if (samples.length !== 11 || samples.some((s, i) => s.valid_at_utc !== hours[i]))
      throw new Error("Published snapshot has an incomplete or duplicated hourly input graph.");
    const sampleIds = JSON.stringify(samples.map(id));
    const intervals = database
      .prepare(
        "SELECT * FROM weather_point_interval_measurements WHERE weather_point_sample_id IN (SELECT value FROM json_each(?))",
      )
      .all(sampleIds);
    const convection = database
      .prepare(
        "SELECT * FROM weather_point_convection_measurements WHERE weather_point_sample_id IN (SELECT value FROM json_each(?))",
      )
      .all(sampleIds);
    this.provenance = database
      .prepare(
        `SELECT * FROM weather_field_provenance WHERE daily_feature_snapshot_id = ?
      OR daily_feature_profile_layer_id IN (SELECT id FROM weather_daily_feature_profile_layers WHERE daily_feature_snapshot_id = ?)
      OR weather_point_sample_id IN (SELECT value FROM json_each(?))
      OR point_interval_measurement_id IN (SELECT id FROM weather_point_interval_measurements WHERE weather_point_sample_id IN (SELECT value FROM json_each(?)))
      OR point_convection_measurement_id IN (SELECT id FROM weather_point_convection_measurements WHERE weather_point_sample_id IN (SELECT value FROM json_each(?)))`,
      )
      .all(snapshotId, snapshotId, sampleIds, sampleIds, sampleIds);

    const xcFeatures = xcInputInventory.map((spec) => {
      const owner =
        spec.scope === "daily"
          ? snapshot
          : layers.find(
              (l) =>
                l.layer_base_agl_m === spec.layerBaseAglM &&
                l.layer_top_agl_m === spec.layerTopAglM,
            );
      if (!owner) throw new Error("Missing XC layer owner.");
      const { column, fieldCode, variant, ...publicSpec } = spec;
      return this.resolve(
        publicSpec,
        owner,
        spec.scope === "daily" ? "daily_feature_snapshot_id" : "daily_feature_profile_layer_id",
        column,
        fieldCode,
        variant,
        spec.statistic,
      );
    });
    const hourlyContext = samples.map((sample, i) => {
      const at = string(sample.valid_at_utc);
      const base = { group: "Hourly context", scope: "hourly", statistic: "instantaneous" };
      const surface = surfaceInputs.map(([key, label, column, code, variant, unit]) =>
        this.resolve(
          { ...base, key, label, unit },
          sample,
          "weather_point_sample_id",
          column,
          code,
          variant,
          key === "stored_weather_lcl" ? "instantaneous" : null,
        ),
      );
      for (const field of surface)
        if (field.provenanceId !== undefined) this.validTimes.set(field.provenanceId, at);
      const low = surface.find((row) => row.key === "low_cloud_percent");
      if (!low) throw new Error("Missing cloud catalogue entry.");
      const odInputs: ForecastInputRow[] = [
        { ...low, key: "low_cloud" },
        ...surface.filter((row) => ["humidity", "wind"].includes(row.key)),
      ];
      this.resolved.push(requirePublishedValue(odInputs[0]));
      const end = hours[i + 1];
      const rainSpec = {
        ...base,
        key: "rain",
        label: "Rain accumulation",
        unit: "mm",
        statistic: "accumulation",
      };
      const candidates = intervals.filter(
        (m) =>
          m.field_code === "precipitation_amount_mm" &&
          m.component === "total" &&
          m.statistic_type === "accumulation" &&
          m.interval_start_utc === at &&
          m.interval_end_utc === end,
      );
      const rain = end
        ? this.uniqueInterval(rainSpec, candidates, "precipitation_amount_mm")
        : this.unavailable(rainSpec, "Outside OD interval inputs");
      odInputs.unshift(rain);
      for (const [key, label, column, code] of convectionInputs) {
        const spec = { ...base, key, label, unit: "J/kg" };
        const owners = convection.filter(
          (m) =>
            m.weather_point_sample_id === sample.id &&
            m.parcel_method === "surface" &&
            m.layer_bottom_pressure_from_ground_pa === null &&
            m.layer_top_pressure_from_ground_pa === null,
        );
        const exact = owners.filter((owner) =>
          this.provenance.some(
            (p) =>
              p.point_convection_measurement_id === owner.id &&
              p.field_code === code &&
              p.field_variant === "surface" &&
              p.statistic_type === null,
          ),
        );
        const candidates = exact.length ? exact : owners;
        for (const candidate of end ? candidates : []) {
          const field = this.resolve(
            spec,
            candidate,
            "point_convection_measurement_id",
            column,
            code,
            "surface",
            null,
          );
          if (field.provenanceId !== undefined) this.validTimes.set(field.provenanceId, at);
        }
        odInputs.push(
          !end
            ? this.unavailable(spec, "Outside OD interval inputs")
            : candidates.length === 1
              ? this.resolve(
                  spec,
                  requirePublishedValue(candidates[0]),
                  "point_convection_measurement_id",
                  column,
                  code,
                  "surface",
                  null,
                )
              : this.unavailable(
                  spec,
                  candidates.length
                    ? "Ambiguous surface parcel input"
                    : "Surface parcel input is not retained",
                ),
        );
      }
      const cloudbaseContext = surface.filter((row) => !["humidity", "wind"].includes(row.key));
      for (const [key, label, code] of heatingInputs) {
        const spec = { ...base, key, label, unit: "W/m2", statistic: "interval_average" };
        const candidates = intervals.filter(
          (m) =>
            m.weather_point_sample_id === sample.id &&
            m.field_code === code &&
            m.component === "not_applicable" &&
            m.statistic_type === "interval_average" &&
            m.interval_end_utc === at,
        );
        // Keep every exact interval for FK resolution, even when the context is ambiguous.
        for (const candidate of candidates) this.resolveInterval(spec, candidate, code);
        cloudbaseContext.push(this.uniqueInterval(spec, candidates, code));
      }
      return { validAtUtc: at, odInputs, cloudbaseContext };
    });
    this.inputs = {
      windowStartUtc: requirePublishedValue(hours[0]),
      windowEndUtc: requirePublishedValue(hours[10]),
      featureContractVersion: string(snapshot.feature_contract_version),
      xcFeatures,
      hourlyContext,
    };
  }

  private unavailable(spec: InputSpec, reason: string): ForecastInputRow {
    return {
      ...spec,
      value: null,
      dataStatus: "missing",
      qualityState: "missing",
      missingReason: reason,
    };
  }

  private resolve(
    spec: InputSpec,
    owner: SqlRow,
    ownerKey: string,
    column: string,
    code: string,
    variant: string,
    statistic: string | null,
  ): ForecastInputRow {
    const matches = this.provenance.filter(
      (p) =>
        p[ownerKey] === owner.id &&
        p.field_code === code &&
        p.field_variant === variant &&
        p.statistic_type === statistic,
    );
    if (matches.length > 1) throw new Error("Duplicated field provenance.");
    const p = matches[0];
    const value = numberOrNull(owner[column]);
    if (!p) return this.unavailable(spec, "Exact field provenance is not retained in SQLite");
    const quality = string(p.quality_state);
    if ((value !== null) !== presentQuality.has(quality))
      throw new Error("Weather value contradicts its exact provenance quality.");
    const result: ForecastInputRow =
      value === null
        ? {
            ...this.unavailable(
              spec,
              string(p.missing_reason_code ?? "Weather input is unavailable"),
            ),
            qualityState: quality,
            provenanceId: id(p),
          }
        : { ...spec, value, dataStatus: "real", qualityState: quality, provenanceId: id(p) };
    this.resolved.push(result);
    return result;
  }

  private resolveInterval(spec: InputSpec, owner: SqlRow, code: string): ForecastInputRow {
    const start = string(owner.interval_start_utc),
      end = string(owner.interval_end_utc);
    return this.resolve(
      {
        ...spec,
        intervalStartUtc: start,
        intervalEndUtc: end,
        label: `${spec.label} · ${start.slice(11, 16)}–${end.slice(11, 16)} UTC`,
      },
      owner,
      "point_interval_measurement_id",
      "canonical_value",
      code,
      "canonical",
      string(owner.statistic_type),
    );
  }

  private uniqueInterval(spec: InputSpec, candidates: readonly SqlRow[], code: string) {
    if (candidates.length !== 1)
      return this.unavailable(
        spec,
        candidates.length
          ? "Ambiguous retained interval inputs"
          : "Exact interval input is not retained",
      );
    return this.resolveInterval(spec, requirePublishedValue(candidates[0]), code);
  }
}
