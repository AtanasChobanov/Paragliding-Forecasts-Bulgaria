import { getTableName } from "drizzle-orm";
import { getTableConfig } from "drizzle-orm/sqlite-core";
import { describe, expect, it } from "vitest";

import {
  flightRecords,
  flightSources,
  flightIngestionRuns,
  sites,
  sourceSiteMappings,
  weatherDailyFeatureProfileLayers,
  weatherDailyFeatureSnapshotInputs,
  weatherDailyFeatureSnapshots,
  weatherFieldProvenance,
  weatherGridPoints,
  weatherGrids,
  weatherIngestionRuns,
  weatherPointConvectionMeasurements,
  weatherPointIntervalMeasurements,
  weatherPointProfileLevels,
  weatherPointSamples,
  weatherProductRuns,
  weatherProductValidTimes,
  weatherSamplingFootprintNodes,
  weatherSamplingFootprints,
  weatherSiteSamplingConfigs,
  weatherSources,
} from "../src/schema.js";

describe("flight foundation schema", () => {
  it("declares exactly the five T-012 persistence tables", () => {
    expect(
      [flightSources, sites, sourceSiteMappings, flightIngestionRuns, flightRecords]
        .map((table) => getTableName(table))
        .sort(),
    ).toEqual([
      "flight_ingestion_runs",
      "flight_records",
      "flight_sources",
      "sites",
      "source_site_mappings",
    ]);
  });

  it("declares the composite parent keys required by SQLite foreign keys", () => {
    getTableConfig(flightSources);
    getTableConfig(sites);
    const mappingConfig = getTableConfig(sourceSiteMappings);
    const runConfig = getTableConfig(flightIngestionRuns);
    const recordConfig = getTableConfig(flightRecords);

    expect(mappingConfig.uniqueConstraints.map((constraint) => constraint.getName())).toContain(
      "source_site_mappings_id_source_id_parent_key_unique",
    );
    expect(runConfig.uniqueConstraints.map((constraint) => constraint.getName())).toContain(
      "ingestion_runs_id_source_id_parent_key_unique",
    );
    expect(recordConfig.foreignKeys.map((foreignKey) => foreignKey.getName())).toEqual(
      expect.arrayContaining([
        "flight_records_mapping_source_fk",
        "flight_records_created_run_source_fk",
        "flight_records_last_validated_run_source_fk",
      ]),
    );
    expect(mappingConfig.foreignKeys.map((foreignKey) => foreignKey.getName())).toEqual(
      expect.arrayContaining([
        "source_site_mappings_source_id_flight_sources_id_fk",
        "source_site_mappings_site_id_sites_id_fk",
      ]),
    );
    expect(runConfig.foreignKeys.map((foreignKey) => foreignKey.getName())).toEqual([
      "flight_ingestion_runs_source_id_flight_sources_id_fk",
    ]);
  });
});

const weatherTables = [
  weatherSources,
  weatherIngestionRuns,
  weatherProductRuns,
  weatherProductValidTimes,
  weatherSiteSamplingConfigs,
  weatherGrids,
  weatherGridPoints,
  weatherSamplingFootprints,
  weatherSamplingFootprintNodes,
  weatherPointSamples,
  weatherPointProfileLevels,
  weatherPointConvectionMeasurements,
  weatherPointIntervalMeasurements,
  weatherDailyFeatureSnapshots,
  weatherDailyFeatureSnapshotInputs,
  weatherDailyFeatureProfileLayers,
  weatherFieldProvenance,
];

describe("weather persistence schema", () => {
  it("declares the normalized hourly and daily weather tables", () => {
    expect(weatherTables.map((table) => getTableName(table)).sort()).toEqual([
      "weather_daily_feature_profile_layers",
      "weather_daily_feature_snapshot_inputs",
      "weather_daily_feature_snapshots",
      "weather_field_provenance",
      "weather_grid_points",
      "weather_grids",
      "weather_ingestion_runs",
      "weather_point_convection_measurements",
      "weather_point_interval_measurements",
      "weather_point_profile_levels",
      "weather_point_samples",
      "weather_product_runs",
      "weather_product_valid_times",
      "weather_sampling_footprint_nodes",
      "weather_sampling_footprints",
      "weather_site_sampling_configs",
      "weather_sources",
    ]);
  });

  it("normalizes source, product, valid-time, and ingestion ownership", () => {
    const runConfig = getTableConfig(weatherIngestionRuns);
    const productConfig = getTableConfig(weatherProductRuns);
    const validTimeConfig = getTableConfig(weatherProductValidTimes);
    const productColumns = productConfig.columns.map((column) => column.name);

    expect(runConfig.columns.map((column) => column.name)).toEqual(
      expect.arrayContaining(["product_run_id", "target_local_date"]),
    );
    expect(runConfig.columns.map((column) => column.name)).not.toContain("source_id");
    expect(productColumns).not.toContain("valid_from_utc");
    expect(productColumns).not.toContain("valid_to_utc");
    expect(productColumns).not.toContain("created_by_ingestion_run_id");
    expect(productColumns).not.toContain("last_validated_by_ingestion_run_id");
    expect(validTimeConfig.uniqueConstraints.map((constraint) => constraint.getName())).toContain(
      "weather_product_valid_times_product_valid_unique",
    );
  });

  it("keeps normalized location and grid ownership without redundant foreign keys", () => {
    const nodeColumns = getTableConfig(weatherSamplingFootprintNodes).columns.map(
      (column) => column.name,
    );
    const sampleColumns = getTableConfig(weatherPointSamples).columns.map((column) => column.name);

    expect(nodeColumns).toEqual([
      "footprint_id",
      "grid_point_id",
      "distance_km",
      "interpolation_weight",
    ]);
    expect(sampleColumns).not.toContain("site_id");
    expect(sampleColumns).not.toContain("grid_id");
    expect(sampleColumns).toEqual(
      expect.arrayContaining([
        "ingestion_run_id",
        "product_valid_time_id",
        "point_footprint_id",
        "provider_boundary_layer_height_agl_m",
        "specific_humidity_2m_kg_per_kg",
      ]),
    );
    expect(sampleColumns).not.toContain("product_run_id");
    expect(sampleColumns).not.toContain("valid_at_utc");
    expect(sampleColumns).not.toContain("valid_local_date");
    expect(sampleColumns).not.toContain("lead_hours");
    expect(sampleColumns).not.toContain("provider_boundary_layer_height_msl_m");
  });

  it("stores interval quality only through per-field provenance", () => {
    const intervalColumns = getTableConfig(weatherPointIntervalMeasurements).columns.map(
      (column) => column.name,
    );
    const provenanceConfig = getTableConfig(weatherFieldProvenance);

    expect(intervalColumns).toEqual(
      expect.arrayContaining([
        "field_code",
        "component",
        "canonical_value",
        "interval_start_utc",
        "interval_end_utc",
      ]),
    );
    expect(intervalColumns).not.toContain("source_step_start_hours");
    expect(intervalColumns).not.toContain("source_step_end_hours");
    expect(intervalColumns).not.toContain("quality_state");
    expect(provenanceConfig.columns.map((column) => column.name)).toContain("quality_state");
    expect(provenanceConfig.indexes.map((index) => index.config.name)).toEqual(
      expect.arrayContaining([
        "weather_field_provenance_sample_field_unique",
        "weather_field_provenance_convection_field_unique",
        "weather_field_provenance_interval_field_unique",
        "weather_field_provenance_profile_field_unique",
        "weather_field_provenance_feature_field_unique",
        "weather_field_provenance_feature_layer_field_unique",
      ]),
    );
  });

  it("uses relational daily inputs and layer rows without content hashes", () => {
    const gridColumns = getTableConfig(weatherGrids).columns.map((column) => column.name);
    const footprintColumns = getTableConfig(weatherSamplingFootprints).columns.map(
      (column) => column.name,
    );
    const snapshotColumns = getTableConfig(weatherDailyFeatureSnapshots).columns.map(
      (column) => column.name,
    );

    expect(gridColumns).toEqual(["id", "source_id", "grid_key"]);
    expect(footprintColumns).not.toContain("footprint_version");
    expect(footprintColumns).not.toContain("definition_sha256");
    expect(snapshotColumns).not.toContain("weather_sample_id");
    expect(snapshotColumns).not.toContain("input_fingerprint_sha256");
    expect(snapshotColumns).not.toEqual(
      expect.arrayContaining([
        "mixed_layer_lcl_agl_mean_m",
        "mixed_layer_lcl_agl_max_m",
        "surface_buoyancy_flux_kinematic_mean_k_m_s",
        "convective_velocity_scale_mean_m_s",
        "convective_velocity_scale_max_m_s",
      ]),
    );
    expect(getTableConfig(weatherDailyFeatureSnapshotInputs).primaryKeys).toHaveLength(1);
    expect(getTableConfig(weatherDailyFeatureProfileLayers).uniqueConstraints).toHaveLength(1);
  });
});
