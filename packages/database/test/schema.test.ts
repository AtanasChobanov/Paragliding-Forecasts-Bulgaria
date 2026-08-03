import { getTableName } from "drizzle-orm";
import { getTableConfig } from "drizzle-orm/sqlite-core";
import { describe, expect, it } from "vitest";

import {
  flightRecords,
  flightSources,
  ingestionRuns,
  sites,
  sourceSiteMappings,
} from "../src/schema.js";

describe("flight foundation schema", () => {
  it("declares exactly the five T-012 persistence tables", () => {
    expect(
      [flightSources, sites, sourceSiteMappings, ingestionRuns, flightRecords]
        .map((table) => getTableName(table))
        .sort(),
    ).toEqual([
      "flight_records",
      "flight_sources",
      "ingestion_runs",
      "sites",
      "source_site_mappings",
    ]);
  });

  it("declares the composite parent keys required by SQLite foreign keys", () => {
    getTableConfig(flightSources);
    getTableConfig(sites);
    const mappingConfig = getTableConfig(sourceSiteMappings);
    const runConfig = getTableConfig(ingestionRuns);
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
      "ingestion_runs_source_id_flight_sources_id_fk",
    ]);
  });
});
