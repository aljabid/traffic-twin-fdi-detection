from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class AuditEvent:
    event: str
    device_id: str | None = None
    outcome: str = "success"
    detail: str = ""
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AuditLog:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else None
        self.events: list[AuditEvent] = []

    def record(
        self,
        event: str,
        device_id: str | None = None,
        outcome: str = "success",
        detail: str = "",
    ) -> None:
        item = AuditEvent(event, device_id, outcome, detail, datetime.now(UTC).isoformat())
        self.events.append(item)
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(item.to_dict()) + "\n")
