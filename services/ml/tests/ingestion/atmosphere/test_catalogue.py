from __future__ import annotations

import hashlib
from importlib import resources

import pytest

from paragliding_forecasts_ml.ingestion.atmosphere.catalogue import CatalogueError, load_catalogue


def test_packaged_catalogue_is_the_single_runtime_vocabulary() -> None:
    catalogue = load_catalogue()
    resource = resources.files("paragliding_forecasts_ml.ingestion.atmosphere").joinpath(
        "resources", "weather-field-catalogue.json"
    )

    assert catalogue.version == "t017-spike-v1"
    assert len(catalogue.field_codes) == 31
    assert catalogue.sha256 == hashlib.sha256(resource.read_bytes()).hexdigest()
    assert catalogue.field_unit("air_temperature_k") == "K"
    assert "noaa_gfs_0p25_aws_grib2" in catalogue.source_ids
    assert "copernicus_era5" in catalogue.source_ids


def test_catalogue_rejects_unknown_runtime_vocabulary() -> None:
    catalogue = load_catalogue()

    with pytest.raises(CatalogueError, match="Unknown canonical field"):
        catalogue.validate_field_code("invented_thermal_index")
    with pytest.raises(CatalogueError, match="Unknown catalogue quality"):
        catalogue.validate_quality_state("estimated")
