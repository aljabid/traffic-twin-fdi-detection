from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TwinScenario:
    name: str
    speed_multiplier: float
    occupancy_multiplier: float
    dropout_probability: float


SCENARIOS = {
    "normal_rush_hour": TwinScenario("normal_rush_hour", 0.75, 1.4, 0.0),
    "incident": TwinScenario("incident", 0.2, 2.0, 0.02),
    "sensor_dropout": TwinScenario("sensor_dropout", 1.0, 1.0, 0.35),
}


def get_scenario(name: str) -> TwinScenario:
    try:
        return SCENARIOS[name]
    except KeyError as exc:
        raise ValueError(f"Unknown twin scenario: {name}") from exc
