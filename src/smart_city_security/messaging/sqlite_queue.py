from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock

from smart_city_security.contracts import EventEnvelope


@dataclass(frozen=True, slots=True)
class QueuedEvent:
    sequence: int
    event: EventEnvelope
    attempts: int


class SQLiteEventQueue:

    def __init__(self, path: str | Path, *, max_attempts: int = 5) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.max_attempts = max_attempts
        self._lock = RLock()
        self._db = sqlite3.connect(self.path, isolation_level=None, check_same_thread=False)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS event_queue (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                payload BLOB NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                available_at REAL NOT NULL,
                leased_until REAL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS event_dead_letter (
                sequence INTEGER PRIMARY KEY,
                event_id TEXT NOT NULL,
                payload BLOB NOT NULL,
                attempts INTEGER NOT NULL,
                reason TEXT NOT NULL,
                failed_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_queue_available
            ON event_queue(available_at, leased_until, sequence);
            """
        )

    def publish(self, event: EventEnvelope, *, delay_seconds: float = 0) -> int:
        if delay_seconds < 0:
            raise ValueError("delay_seconds cannot be negative")
        with self._lock, self._db:
            cursor = self._db.execute(
                """
                INSERT INTO event_queue
                    (event_id, payload, available_at, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.to_bytes(),
                    time.time() + delay_seconds,
                    datetime.now(UTC).isoformat(),
                ),
            )
            if cursor.lastrowid is None:
                raise RuntimeError("insert did not return a row id")
            return cursor.lastrowid

    def lease(self, *, lease_seconds: float = 30) -> QueuedEvent | None:
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        now = time.time()
        with self._lock, self._db:
            row = self._db.execute(
                """
                SELECT sequence, payload, attempts FROM event_queue
                WHERE available_at <= ?
                  AND (leased_until IS NULL OR leased_until <= ?)
                ORDER BY sequence LIMIT 1
                """,
                (now, now),
            ).fetchone()
            if row is None:
                return None
            updated = self._db.execute(
                """
                UPDATE event_queue SET leased_until = ?
                WHERE sequence = ?
                  AND (leased_until IS NULL OR leased_until <= ?)
                """,
                (now + lease_seconds, row[0], now),
            )
            if updated.rowcount != 1:
                return None
        return QueuedEvent(int(row[0]), EventEnvelope.from_bytes(row[1]), int(row[2]))

    def acknowledge(self, sequence: int) -> bool:
        with self._lock, self._db:
            cursor = self._db.execute(
                "DELETE FROM event_queue WHERE sequence = ?", (sequence,)
            )
            return cursor.rowcount == 1

    def reject(self, sequence: int, reason: str, *, retry_delay_seconds: float = 1) -> bool:
        if not reason:
            raise ValueError("dead-letter reason is required")
        with self._lock, self._db:
            row = self._db.execute(
                "SELECT event_id, payload, attempts FROM event_queue WHERE sequence = ?",
                (sequence,),
            ).fetchone()
            if row is None:
                return False
            attempts = int(row[2]) + 1
            if attempts >= self.max_attempts:
                self._db.execute(
                    """
                    INSERT OR REPLACE INTO event_dead_letter
                        (sequence, event_id, payload, attempts, reason, failed_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        sequence,
                        row[0],
                        row[1],
                        attempts,
                        reason,
                        datetime.now(UTC).isoformat(),
                    ),
                )
                self._db.execute(
                    "DELETE FROM event_queue WHERE sequence = ?", (sequence,)
                )
            else:
                self._db.execute(
                    """
                    UPDATE event_queue SET attempts = ?, available_at = ?,
                        leased_until = NULL WHERE sequence = ?
                    """,
                    (attempts, time.time() + max(0, retry_delay_seconds), sequence),
                )
            return True

    def depth(self) -> int:
        with self._lock:
            return int(self._db.execute("SELECT COUNT(*) FROM event_queue").fetchone()[0])

    def dead_letter_depth(self) -> int:
        with self._lock:
            return int(
                self._db.execute("SELECT COUNT(*) FROM event_dead_letter").fetchone()[0]
            )

    def close(self) -> None:
        with self._lock:
            self._db.close()
