from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ServiceLevelObjective:
    name: str
    target: float
    window_seconds: int

    def __post_init__(self) -> None:
        if not 0 < self.target <= 1 or self.window_seconds <= 0:
            raise ValueError("Invalid SLO target or window")


@dataclass(frozen=True, slots=True)
class SLOStatus:
    name: str
    achieved: float
    target: float
    error_budget_remaining: float
    passed: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_availability(
    objective: ServiceLevelObjective, *, successful: int, total: int
) -> SLOStatus:
    if total < 1 or not 0 <= successful <= total:
        raise ValueError("Invalid event counts")
    achieved = successful / total
    allowed_failures = 1 - objective.target
    consumed = max(0.0, 1 - achieved)
    remaining = max(0.0, 1 - consumed / allowed_failures) if allowed_failures else float(achieved == 1)
    return SLOStatus(
        objective.name,
        achieved,
        objective.target,
        remaining,
        achieved >= objective.target,
    )
