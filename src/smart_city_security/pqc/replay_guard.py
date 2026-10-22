from __future__ import annotations

import time


class ReplayError(ValueError):
    pass


class ReplayGuard:
    def __init__(self, tolerance_seconds: float = 30):
        self.tolerance_seconds = tolerance_seconds
        self._nonces: set[tuple[str, bytes]] = set()
        self._sequences: dict[tuple[str, str], int] = {}

    def validate(
        self,
        device_id: str,
        session_id: str,
        nonce: bytes,
        sequence_number: int,
        timestamp: float,
        now: float | None = None,
    ) -> None:
        now = time.time() if now is None else now
        if abs(now - timestamp) > self.tolerance_seconds:
            raise ReplayError("Message timestamp outside permitted window")
        nonce_key = (session_id, nonce)
        if nonce_key in self._nonces:
            raise ReplayError("Duplicate nonce")
        sequence_key = (device_id, session_id)
        previous = self._sequences.get(sequence_key, -1)
        if sequence_number <= previous:
            raise ReplayError("Non-increasing sequence number")
        self._nonces.add(nonce_key)
        self._sequences[sequence_key] = sequence_number
