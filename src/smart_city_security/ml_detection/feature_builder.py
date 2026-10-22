from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np

from smart_city_security.iot_sim.device_profiles import DEFAULT_PROFILES
from smart_city_security.schemas import Telemetry, TwinState

BASE_FEATURE_NAMES = (
    "speed",
    "occupancy",
    "speed_delta",
    "position_delta",
    "interarrival",
    "message_rate",
    "profile_speed_violation",
)
DIVERGENCE_FEATURE_NAMES = ("speed_divergence", "occupancy_divergence")
DIVERGENCE_TRANSFORMS = ("none", "log1p")


@dataclass(frozen=True, slots=True)
class FeatureRecord:
    message_id: str
    values: np.ndarray


class FeatureBuilder:
    def __init__(self, include_divergence: bool = True, divergence_transform: str = "none",
                 history: int = 1):
        if divergence_transform not in DIVERGENCE_TRANSFORMS:
            raise ValueError(f"unknown divergence transform: {divergence_transform!r}")
        if history < 1:
            raise ValueError("history must be at least 1")
        self.include_divergence = include_divergence
        self.divergence_transform = divergence_transform
        self.history = history
        self._previous: dict[str, Telemetry] = {}
        self._window: dict[str, deque[Telemetry]] = {}

    @property
    def feature_names(self) -> tuple[str, ...]:
        lags = tuple(
            f"{field}_lag{k}" for k in range(1, self.history) for field in ("speed", "occupancy")
        )
        return BASE_FEATURE_NAMES + (
            DIVERGENCE_FEATURE_NAMES if self.include_divergence else ()
        ) + lags

    def build(
        self, telemetry: Telemetry, twin: TwinState, *, commit: bool = True
    ) -> FeatureRecord:
        previous = self._previous.get(telemetry.device_id)
        if previous is None:
            speed_delta = position_delta = 0.0
            interarrival = 1.0
        else:
            speed_delta = abs(telemetry.speed - previous.speed)
            position_delta = abs(telemetry.position - previous.position)
            interarrival = max(1e-6, telemetry.timestamp - previous.timestamp)
        profile = DEFAULT_PROFILES.get(telemetry.device_type)
        violation = float(
            profile is None
            or telemetry.speed < profile.min_speed
            or telemetry.speed > profile.max_speed
        )
        values = [
            telemetry.speed,
            telemetry.occupancy,
            speed_delta,
            position_delta,
            interarrival,
            1.0 / interarrival,
            violation,
        ]
        if self.include_divergence:
            if self.divergence_transform == "log1p":
                values.extend((float(np.log1p(abs(twin.speed_divergence))),
                               float(np.log1p(abs(twin.occupancy_divergence)))))
            else:
                values.extend((twin.speed_divergence, twin.occupancy_divergence))
        if self.history > 1:
            past = list(self._window.get(telemetry.device_id, ()))[::-1]
            for k in range(self.history - 1):
                lag = past[k] if k < len(past) else telemetry
                values.extend((lag.speed, lag.occupancy))
        if commit:
            self._previous[telemetry.device_id] = telemetry
            if self.history > 1:
                self._window.setdefault(
                    telemetry.device_id, deque(maxlen=self.history - 1)
                ).append(telemetry)
        return FeatureRecord(telemetry.message_id, np.asarray(values, dtype=float))

    def build_many(
        self, pairs: list[tuple[Telemetry, TwinState]]
    ) -> tuple[list[str], np.ndarray]:
        records = [self.build(telemetry, twin) for telemetry, twin in pairs]
        if not records:
            return [], np.empty((0, len(self.feature_names)))
        return [item.message_id for item in records], np.vstack([item.values for item in records])
