from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from time import perf_counter
from typing import Any


@dataclass(frozen=True, slots=True)
class FaultScenario:
    name: str
    expected_behavior: str
    maximum_recovery_seconds: float
    inject: Callable[[], None]
    recover: Callable[[], None]
    verify_safe: Callable[[], bool]


@dataclass(frozen=True, slots=True)
class FaultResult:
    name: str
    passed: bool
    safe_during_fault: bool
    recovered: bool
    recovery_seconds: float
    error: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_fault_scenario(scenario: FaultScenario) -> FaultResult:
    error = None
    safe = recovered = False
    try:
        scenario.inject()
        safe = bool(scenario.verify_safe())
    except Exception as exc:
        error = f"injection or safety verification failed: {exc}"
    recovery_started = perf_counter()
    try:
        scenario.recover()
        recovered = bool(scenario.verify_safe())
    except Exception as exc:
        error = f"{error}; recovery failed: {exc}" if error else f"recovery failed: {exc}"
    recovery_seconds = perf_counter() - recovery_started
    passed = (
        safe
        and recovered
        and recovery_seconds <= scenario.maximum_recovery_seconds
        and error is None
    )
    return FaultResult(
        scenario.name, passed, safe, recovered, recovery_seconds, error
    )


def run_fault_campaign(scenarios: list[FaultScenario]) -> dict[str, Any]:
    if not scenarios:
        raise ValueError("At least one fault scenario is required")
    results = tuple(run_fault_scenario(scenario) for scenario in scenarios)
    return {
        "passed": all(result.passed for result in results),
        "scenarios": [result.to_dict() for result in results],
    }
