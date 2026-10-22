from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace

from smart_city_security.schemas import Telemetry


def perturb_speed(message: Telemetry, delta: float) -> Telemetry:
    return replace(
        message,
        speed=max(0.0, message.speed + delta),
        message_id=f"perturbed-{message.message_id}",
    )


def perturb_clock(message: Telemetry, delta_seconds: float) -> Telemetry:
    return replace(
        message,
        timestamp=message.timestamp + delta_seconds,
        message_id=f"clock-{message.message_id}",
    )


def drop_sensor_value(message: Telemetry, field: str) -> Telemetry:
    defaults: dict[str, float | str] = {"speed": 0.0, "occupancy": 0.0, "signal_state": "unknown"}
    if field not in defaults:
        raise ValueError(f"Unsupported sensor field: {field}")
    return replace(message, **{field: defaults[field]}, message_id=f"drop-{message.message_id}")


def attack_success_rate(predictions: Iterable[object], expected_attack: bool = True) -> float:
    values = [bool(value) for value in predictions]
    if not values:
        return 0.0
    expected = values if expected_attack else [not value for value in values]
    return sum(expected) / len(values)


@dataclass(frozen=True, slots=True)
class RobustnessScenarioResult:
    scenario: str
    samples: int
    detected: int
    detection_rate: float


def evaluate_robustness(
    messages: list[Telemetry],
    detector: Callable[[Telemetry], bool],
    transformations: dict[str, Callable[[Telemetry], Telemetry]],
) -> tuple[RobustnessScenarioResult, ...]:
    if not messages:
        raise ValueError("messages cannot be empty")
    results = []
    for name, transform in transformations.items():
        predictions = [bool(detector(transform(message))) for message in messages]
        detected = sum(predictions)
        results.append(
            RobustnessScenarioResult(name, len(predictions), detected, detected / len(predictions))
        )
    return tuple(results)
