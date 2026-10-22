from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock

from smart_city_security.schemas import Telemetry

SCHEMA = """
CREATE TABLE IF NOT EXISTS telemetry (
    message_id TEXT PRIMARY KEY,
    device_id TEXT NOT NULL,
    timestamp REAL NOT NULL,
    payload BLOB NOT NULL,
    ingested_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_telemetry_device_time
ON telemetry(device_id, timestamp DESC);
"""


class SQLiteTelemetryRepository:

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(
            self.path, check_same_thread=False, isolation_level=None
        )
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA foreign_keys=ON")
        self._connection.executescript(SCHEMA)
        self._lock = RLock()

    def append(self, telemetry: Telemetry) -> None:
        try:
            with self._lock, self._connection:
                self._connection.execute(
                    """
                    INSERT INTO telemetry
                    (message_id, device_id, timestamp, payload, ingested_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        telemetry.message_id,
                        telemetry.device_id,
                        telemetry.timestamp,
                        telemetry.to_bytes(),
                        datetime.now(UTC).isoformat(),
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"Duplicate message: {telemetry.message_id}") from exc

    def get(self, message_id: str) -> Telemetry | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT payload FROM telemetry WHERE message_id = ?", (message_id,)
            ).fetchone()
        return Telemetry.from_bytes(row[0]) if row else None

    def recent(self, device_id: str, limit: int = 100) -> list[Telemetry]:
        if limit < 1:
            return []
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT payload FROM telemetry
                WHERE device_id = ? ORDER BY timestamp DESC LIMIT ?
                """,
                (device_id, limit),
            ).fetchall()
        return [Telemetry.from_bytes(row[0]) for row in reversed(rows)]

    def purge_before(self, timestamp: float) -> int:
        with self._lock, self._connection:
            cursor = self._connection.execute(
                "DELETE FROM telemetry WHERE timestamp < ?", (timestamp,)
            )
            return cursor.rowcount

    def backup(self, destination: str | Path) -> Path:
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, sqlite3.connect(target) as backup:
            self._connection.backup(backup)
        return target

    def close(self) -> None:
        with self._lock:
            self._connection.close()
