from __future__ import annotations

from collections import defaultdict
from threading import RLock
from typing import Protocol

from smart_city_security.schemas import Telemetry


class TelemetryRepository(Protocol):
    def append(self, telemetry: Telemetry) -> None: ...
    def get(self, message_id: str) -> Telemetry | None: ...
    def recent(self, device_id: str, limit: int = 100) -> list[Telemetry]: ...


class InMemoryTelemetryRepository:

    def __init__(self) -> None:
        self._messages: dict[str, Telemetry] = {}
        self._devices: dict[str, list[str]] = defaultdict(list)
        self._lock = RLock()

    def append(self, telemetry: Telemetry) -> None:
        with self._lock:
            if telemetry.message_id in self._messages:
                raise ValueError(f"Duplicate message: {telemetry.message_id}")
            self._messages[telemetry.message_id] = telemetry
            self._devices[telemetry.device_id].append(telemetry.message_id)

    def get(self, message_id: str) -> Telemetry | None:
        with self._lock:
            return self._messages.get(message_id)

    def recent(self, device_id: str, limit: int = 100) -> list[Telemetry]:
        if limit < 1:
            return []
        with self._lock:
            ids = self._devices.get(device_id, [])[-limit:]
            return [self._messages[item] for item in ids]
