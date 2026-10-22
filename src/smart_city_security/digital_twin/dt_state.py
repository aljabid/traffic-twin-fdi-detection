from __future__ import annotations

from collections import defaultdict, deque

from smart_city_security.schemas import Telemetry


class DigitalTwinState:
    def __init__(self, history_window: int = 8):
        if history_window < 1:
            raise ValueError("history_window must be positive")
        self.history_window = history_window
        self._history: dict[str, deque[Telemetry]] = defaultdict(
            lambda: deque(maxlen=history_window)
        )

    def history(self, intersection_id: str) -> tuple[Telemetry, ...]:
        return tuple(self._history[intersection_id])

    def update(self, telemetry: Telemetry) -> None:
        self._history[telemetry.intersection_id].append(telemetry)
