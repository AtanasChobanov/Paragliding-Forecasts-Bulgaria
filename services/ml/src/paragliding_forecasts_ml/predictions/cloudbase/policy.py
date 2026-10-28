"""Explicit, uncalibrated cloud-formation and conditional-height policy."""

from dataclasses import asdict, dataclass

SCHEMA_VERSION = "cloudbase-batch/2"
METHOD_VERSION = "mixed100-romps-ccl/2"


@dataclass(frozen=True)
class CloudbasePolicy:
    version: str = "cloudbase-baseline-policy/2"
    mixed_depth_pa: float = 10_000.0
    sensitivity_depth_pa: float = 5_000.0
    height_margin_m: float = 250.0
    temperature_margin_k: float = 1.0
    widespread_low_cloud_percent: float = 80.0
    blue_max_low_cloud_percent: float = 20.0
    near_saturation_fraction: float = 0.99
    sensitivity_temperature_offsets_k: tuple[float, ...] = (-1.0, 0.0, 1.0)
    terrain_warning_m: float = 250.0
    validation_status: str = "not_observationally_calibrated"

    def as_dict(self) -> dict:
        result = asdict(self)
        result["sensitivity_temperature_offsets_k"] = list(self.sensitivity_temperature_offsets_k)
        return result


POLICY = CloudbasePolicy()
