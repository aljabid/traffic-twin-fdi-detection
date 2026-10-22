from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from threading import RLock
from typing import Any

Validator = Callable[[dict[str, Any]], None]
Migration = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True, slots=True)
class SchemaDefinition:
    event_type: str
    version: int
    validator: Validator


class SchemaRegistry:

    def __init__(self) -> None:
        self._schemas: dict[tuple[str, int], SchemaDefinition] = {}
        self._migrations: dict[tuple[str, int], Migration] = {}
        self._lock = RLock()

    def register(self, event_type: str, version: int, validator: Validator) -> None:
        if not event_type or version < 1:
            raise ValueError("event_type and positive version are required")
        key = (event_type, version)
        with self._lock:
            if key in self._schemas:
                raise ValueError(f"Schema already registered: {event_type} v{version}")
            self._schemas[key] = SchemaDefinition(event_type, version, validator)

    def register_migration(
        self, event_type: str, from_version: int, migration: Migration
    ) -> None:
        key = (event_type, from_version)
        with self._lock:
            if key in self._migrations:
                raise ValueError(f"Migration already registered: {event_type} v{from_version}")
            self._migrations[key] = migration

    def latest_version(self, event_type: str) -> int:
        with self._lock:
            versions = [version for name, version in self._schemas if name == event_type]
        if not versions:
            raise KeyError(f"Unknown event type: {event_type}")
        return max(versions)

    def validate(self, event_type: str, version: int, payload: dict[str, Any]) -> None:
        with self._lock:
            definition = self._schemas.get((event_type, version))
        if definition is None:
            raise ValueError(f"Unsupported schema: {event_type} v{version}")
        definition.validator(payload)

    def migrate(
        self,
        event_type: str,
        from_version: int,
        payload: dict[str, Any],
        to_version: int | None = None,
    ) -> tuple[int, dict[str, Any]]:
        target = self.latest_version(event_type) if to_version is None else to_version
        if from_version > target:
            raise ValueError("Downgrade migrations are not supported")
        current, value = from_version, dict(payload)
        self.validate(event_type, current, value)
        while current < target:
            with self._lock:
                migration = self._migrations.get((event_type, current))
            if migration is None:
                raise ValueError(
                    f"Missing migration: {event_type} v{current} to v{current + 1}"
                )
            value = migration(value)
            current += 1
            self.validate(event_type, current, value)
        return current, value
