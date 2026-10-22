from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

CURRENT_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class EventEnvelope:
    event_type: str
    payload: dict[str, Any]
    schema_version: int = CURRENT_SCHEMA_VERSION
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    occurred_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )
    correlation_id: str | None = None

    def __post_init__(self) -> None:
        if self.schema_version != CURRENT_SCHEMA_VERSION:
            raise ValueError(f"Unsupported schema version: {self.schema_version}")
        if not self.event_type or not isinstance(self.payload, dict):
            raise ValueError("event_type and dictionary payload are required")

    def to_bytes(self) -> bytes:
        return json.dumps(
            asdict(self), sort_keys=True, separators=(",", ":")
        ).encode()

    @classmethod
    def from_bytes(cls, value: bytes) -> EventEnvelope:
        data = json.loads(value.decode("utf-8"))
        return cls(**data)


@dataclass(frozen=True, slots=True)
class AlertEvent:
    alert_id: str
    device_id: str
    severity: str
    category: str
    score: float
    explanation: str
    requires_operator_ack: bool = True

    def __post_init__(self) -> None:
        if self.severity not in {"info", "low", "medium", "high", "critical"}:
            raise ValueError("invalid alert severity")


@dataclass(frozen=True, slots=True)
class HealthStatus:
    service: str
    live: bool
    ready: bool
    dependencies: dict[str, bool] = field(default_factory=dict)
    detail: str = ""
