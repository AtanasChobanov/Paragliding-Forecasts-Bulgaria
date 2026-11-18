// Published T-022 reason codes; unknown codes retain a readable fallback.
const reasons: Readonly<Record<string, string>> = {
  near_saturated_surface: "The model surface is nearly saturated.",
  widespread_low_cloud: "The model indicates widespread low cloud.",
  low_cloud_input_missing_or_invalid: "Low-cloud cover is unavailable.",
  potential_base_outside_profile: "The conditional LCL is outside the retained model profile.",
  ccl_not_found_in_profile: "No convective condensation level was found in the model profile.",
  multiple_ccl_intersections: "The model profile gives multiple convective condensation levels.",
  formation_input_missing: "Inputs needed to assess cumulus formation are missing.",
  heating_and_condensation_supported: "The model supports heating and local cumulus condensation.",
  positive_heating_not_established: "The model does not establish positive surface heating.",
  local_cumulus_formation_not_supported: "The model does not support local cumulus formation.",
  transition_or_conflicting_evidence: "The model gives mixed signals for local cumulus formation.",
  cloud_type_unknown: "Cloud type is uncertain.",
  required_source_input_unavailable: "Required source inputs are unavailable.",
  surface_or_model_terrain_missing: "Surface or model terrain inputs are missing.",
  model_profile_order_invalid: "The retained model profile has inconsistent vertical ordering.",
  model_profile_missing: "The retained model profile is incomplete.",
  buoyancy_input_missing: "Surface buoyancy inputs are unavailable.",
  condensation_pressure_outside_profile:
    "The condensation pressure is outside the retained model profile.",
  mixed_layer_pressure_invalid: "The modelled mixed layer pressure is invalid.",
  mixed_layer_profile_insufficient: "The model profile has insufficient mixed layer coverage.",
  mixed_layer_profile_duplicate_pressure: "The mixed layer repeats pressure levels.",
  mixed_layer_pressure_boundary_not_bracketed:
    "The model profile does not span the mixed layer boundary.",
  mixed_layer_integration_invalid: "The mixed layer averages could not be calculated.",
  parcel_vapour_pressure_invalid: "The parcel vapour pressure is invalid.",
  parcel_relative_humidity_invalid: "The parcel relative humidity is invalid.",
  lcl_solver_non_real: "A condensation level could not be calculated from the model profile.",
  lcl_height_invalid: "The calculated condensation height is invalid.",
  thermodynamic_input_invalid: "The model profile contains invalid thermodynamic inputs.",
  blue: "All eleven hours lack model support for local cumulus formation.",
  other_cloud: "Other cloud is forecast throughout the flying window.",
  indeterminate: "The available hours do not establish a cloudbase maximum.",
  missing: "Cloudbase inputs are unavailable throughout the flying window.",
};
export const cloudbaseReasonText = (code: string): string =>
  reasons[code] ?? `${code.replaceAll("_", " ").replace(/^./, (c) => c.toUpperCase())}.`;
