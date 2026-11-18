// Explicit SQL owners/columns matching publication/drivers.py and OD SELECTORS.
export const surfaceInputs = [
  [
    "surface_pressure_pa",
    "Surface pressure",
    "surface_pressure_pa",
    "air_pressure_pa",
    "surface",
    "Pa",
  ],
  [
    "temperature_2m_k",
    "Air temperature, 2 m",
    "air_temperature_2m_k",
    "air_temperature_k",
    "2m",
    "K",
  ],
  [
    "specific_humidity_2m_kg_kg",
    "Specific humidity, 2 m",
    "specific_humidity_2m_kg_per_kg",
    "specific_humidity_kg_per_kg",
    "2m",
    "kg/kg",
  ],
  [
    "pbl_model_agl_m",
    "Provider PBL, model AGL",
    "provider_boundary_layer_height_agl_m",
    "provider_boundary_layer_height_agl_m",
    "canonical",
    "m",
  ],
  [
    "low_cloud_percent",
    "Low cloud cover",
    "low_cloud_cover_percent",
    "cloud_cover_percent",
    "low",
    "%",
  ],
  [
    "total_cloud_percent",
    "Total cloud cover",
    "total_cloud_cover_percent",
    "cloud_cover_percent",
    "total",
    "%",
  ],
  [
    "stored_weather_lcl",
    "Stored weather LCL, model AGL",
    "mixed_layer_lcl_agl_m",
    "mixed_layer_lcl_agl_m",
    "canonical",
    "m",
  ],
  [
    "humidity",
    "Relative humidity, 2 m",
    "relative_humidity_2m_percent",
    "relative_humidity_percent",
    "2m",
    "%",
  ],
  ["wind", "Wind speed, 10 m", "wind_speed_10m_m_s", "wind_speed_m_s", "10m", "m/s"],
] as const;

export const convectionInputs = [
  [
    "cape",
    "Surface parcel CAPE",
    "cape_j_per_kg",
    "convective_available_potential_energy_j_per_kg",
  ],
  [
    "cin",
    "Surface parcel CIN magnitude",
    "cin_magnitude_j_per_kg",
    "convective_inhibition_magnitude_j_per_kg",
  ],
] as const;

export const heatingInputs = [
  [
    "sensible_heat_flux_w_m2",
    "Sensible heat flux, upward",
    "surface_sensible_heat_flux_upward_w_m2",
  ],
  ["latent_heat_flux_w_m2", "Latent heat flux, upward", "surface_latent_heat_flux_upward_w_m2"],
] as const;
