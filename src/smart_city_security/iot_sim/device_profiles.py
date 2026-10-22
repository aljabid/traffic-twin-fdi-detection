from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DeviceProfile:
    device_type: str
    min_speed: float
    max_speed: float
    typical_occupancy: float
    publish_rate_hz: float


DEFAULT_PROFILES = {
    "vehicle": DeviceProfile("vehicle", 4.0, 18.0, 0.25, 10.0),
    "bus": DeviceProfile("bus", 3.0, 13.0, 0.45, 5.0),
    "road_sensor": DeviceProfile("road_sensor", 0.0, 0.0, 0.35, 2.0),
}


def get_profile(device_type: str) -> DeviceProfile:
    try:
        return DEFAULT_PROFILES[device_type]
    except KeyError as exc:
        raise ValueError(f"Unknown device type: {device_type}") from exc
