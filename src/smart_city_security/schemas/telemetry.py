from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(slots=True)
class Telemetry:
    device_id: str
    timestamp: float
    position: float
    speed: float
    intersection_id: str
    occupancy: float
    signal_state: str
    sequence_number: int
    message_id: str
    device_type: str = "vehicle"

    @classmethod
    def create(
        cls,
        device_id: str,
        position: float,
        speed: float,
        intersection_id: str,
        occupancy: float,
        signal_state: str,
        sequence_number: int,
        *,
        timestamp: float | None = None,
        message_id: str | None = None,
        device_type: str = "vehicle",
    ) -> Telemetry:
        return cls(
            device_id=device_id,
            timestamp=time.time() if timestamp is None else timestamp,
            position=position,
            speed=speed,
            intersection_id=intersection_id,
            occupancy=occupancy,
            signal_state=signal_state,
            sequence_number=sequence_number,
            message_id=message_id or str(uuid.uuid4()),
            device_type=device_type,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_bytes(self) -> bytes:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":")).encode()

    @classmethod
    def from_bytes(cls, payload: bytes) -> Telemetry:
        return cls(**json.loads(payload.decode()))
