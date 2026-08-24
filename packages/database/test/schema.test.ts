import { getTableName } from "drizzle-orm";
import { getTableConfig } from "drizzle-orm/sqlite-core";
import { describe, expect, it } from "vitest";

import {
  flightRecords,
  flightSources,
  flightIngestionRuns,
  sites,
  sourceSiteMappings,
  weatherConvectionMeasurements,
  weatherFeatureSnapshots,
  weatherFieldProvenance,
  weatherGridPoints,
  weatherGrids,
  weatherIngestionRuns,
  weatherIntervalMeasurements,
  weatherProductRuns,
  weatherProfileLevels,
  weatherSamples,
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
  weatherSiteSamplingConfigs,
  weatherGrids,
  weatherGridPoints,
  weatherSamplingFootprints,
  weatherSamplingFootprintNodes,
  weatherSamples,
  weatherProfileLevels,
  weatherConvectionMeasurements,
  weatherIntervalMeasurements,
  weatherFeatureSnapshots,
  weatherFieldProvenance,
];

describe("weather persistence schema", () => {
  it("declares exactly the fourteen tables in the accepted draw.io contract", () => {
    expect(weatherTables.map((table) => getTableName(table)).sort()).toEqual([
      "weather_convection_measurements",
      "weather_feature_snapshots",
      "weather_field_provenance",
      "weather_grid_points",
      "weather_grids",
      "weather_ingestion_runs",
      "weather_interval_measurements",
      "weather_product_runs",
      "weather_profile_levels",
      "weather_samples",
      "weather_sampling_footprint_nodes",
      "weather_sampling_footprints",
      "weather_site_sampling_configs",
      "weather_sources",
    ]);
  });

  it("enforces source-consistent product-run provenance", () => {
    const runConfig = getTableConfig(weatherIngestionRuns);
    const productConfig = getTableConfig(weatherProductRuns);

    expect(runConfig.uniqueConstraints.map((constraint) => constraint.getName())).toContain(
      "weather_ingestion_runs_id_source_id_parent_key_unique",
    );
    expect(productConfig.foreignKeys.map((foreignKey) => foreignKey.getName())).toEqual(
      expect.arrayContaining([
        "weather_product_runs_created_run_source_fk",
        "weather_product_runs_last_validated_run_source_fk",
      ]),
    );
  });

  it("keeps normalized location and grid ownership without redundant foreign keys", () => {
    const nodeColumns = getTableConfig(weatherSamplingFootprintNodes).columns.map(
      (column) => column.name,
    );
    const sampleColumns = getTableConfig(weatherSamples).columns.map((column) => column.name);

    expect(nodeColumns).toEqual([
      "footprint_id",
      "grid_point_id",
      "distance_km",
      "interpolation_weight",
    ]);
    expect(sampleColumns).not.toEqual(expect.arrayContaining(["site_id", "grid_id"]));
    expect(sampleColumns).toEqual(
      expect.arrayContaining([
        "product_run_id",
        "point_footprint_id",
        "provider_boundary_layer_height_agl_m",
        "provider_boundary_layer_height_msl_m",
      ]),
    );
  });

  it("stores interval quality only through per-field provenance", () => {
    const intervalColumns = getTableConfig(weatherIntervalMeasurements).columns.map(
      (column) => column.name,
    );
    const provenanceConfig = getTableConfig(weatherFieldProvenance);

    expect(intervalColumns).toEqual(
      expect.arrayContaining([
        "field_code",
        "component",
        "canonical_value",
        "source_step_start_hours",
        "source_step_end_hours",
      ]),
    );
    expect(intervalColumns).not.toContain("quality_state");
    expect(provenanceConfig.columns.map((column) => column.name)).toContain("quality_state");
    expect(provenanceConfig.indexes.map((index) => index.config.name)).toEqual(
      expect.arrayContaining([
        "weather_field_provenance_sample_field_unique",
        "weather_field_provenance_convection_field_unique",
        "weather_field_provenance_interval_field_unique",
        "weather_field_provenance_profile_field_unique",
        "weather_field_provenance_feature_field_unique",
      ]),
    );
  });
});
