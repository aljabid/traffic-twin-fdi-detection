from __future__ import annotations

import math
import time
from dataclasses import dataclass, replace

from smart_city_security.schemas import Telemetry


@dataclass(frozen=True, slots=True)
class QualityIssue:
    code: str
    severity: str
    detail: str


@dataclass(frozen=True, slots=True)
class QualityAssessment:
    accepted: bool
    score: float
    normalized: Telemetry
    issues: tuple[QualityIssue, ...]


class TelemetryQualityPolicy:

    SIGNAL_STATES = frozenset({"red", "yellow", "green", "unknown"})

    def __init__(
        self,
        *,
        maximum_clock_skew_seconds: float = 120,
        maximum_speed: float = 90,
        reject_below_score: float = 0.6,
    ) -> None:
        self.maximum_clock_skew_seconds = maximum_clock_skew_seconds
        self.maximum_speed = maximum_speed
        self.reject_below_score = reject_below_score
        self._last_sequence: dict[str, int] = {}

    def assess(self, telemetry: Telemetry, *, now: float | None = None) -> QualityAssessment:
        observed_at = time.time() if now is None else now
        issues: list[QualityIssue] = []
        normalized = telemetry
        numeric = (
            telemetry.timestamp,
            telemetry.position,
            telemetry.speed,
            telemetry.occupancy,
        )
        if not all(math.isfinite(value) for value in numeric):
            issues.append(QualityIssue("NON_FINITE", "critical", "numeric field is not finite"))
        if abs(observed_at - telemetry.timestamp) > self.maximum_clock_skew_seconds:
            issues.append(QualityIssue("CLOCK_SKEW", "high", "timestamp exceeds skew policy"))
        if not 0 <= telemetry.speed <= self.maximum_speed:
            issues.append(QualityIssue("SPEED_RANGE", "high", "speed outside physical policy"))
        if not 0 <= telemetry.occupancy <= 1:
            issues.append(
                QualityIssue("OCCUPANCY_RANGE", "high", "occupancy must be in [0, 1]")
            )
        if telemetry.signal_state not in self.SIGNAL_STATES:
            issues.append(QualityIssue("SIGNAL_STATE", "medium", "unknown signal state"))
            normalized = replace(telemetry, signal_state="unknown")
        if not telemetry.intersection_id.strip():
            issues.append(QualityIssue("MISSING_INTERSECTION", "critical", "location is required"))
        previous = self._last_sequence.get(telemetry.device_id)
        if previous is not None and telemetry.sequence_number <= previous:
            issues.append(QualityIssue("SEQUENCE_ORDER", "critical", "sequence is not increasing"))

        deductions = {"critical": 1.0, "high": 0.35, "medium": 0.15, "low": 0.05}
        score = max(0.0, 1.0 - sum(deductions[item.severity] for item in issues))
        accepted = score >= self.reject_below_score and not any(
            item.severity == "critical" for item in issues
        )
        if accepted:
            self._last_sequence[telemetry.device_id] = telemetry.sequence_number
        return QualityAssessment(accepted, score, normalized, tuple(issues))
