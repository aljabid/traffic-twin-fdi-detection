from __future__ import annotations

from collections.abc import Callable

from smart_city_security.contracts import HealthStatus


class HealthService:
    def __init__(self, name: str):
        self.name = name
        self._checks: dict[str, Callable[[], bool]] = {}

    def register(self, dependency: str, check: Callable[[], bool]) -> None:
        self._checks[dependency] = check

    def status(self) -> HealthStatus:
        states: dict[str, bool] = {}
        for name, check in self._checks.items():
            try:
                states[name] = bool(check())
            except Exception:
                states[name] = False
        return HealthStatus(
            service=self.name,
            live=True,
            ready=all(states.values()) if states else True,
            dependencies=states,
        )
