from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

from .interfaces import CryptoBackend


@dataclass(slots=True)
class Session:
    session_id: str
    device_id: str
    shared_key: bytes
    created_at: float
    messages_sent: int
    handshake_bytes: int


class SessionManager:
    def __init__(
        self,
        backend: CryptoBackend,
        max_messages: int = 50,
        max_age_seconds: float = 300,
    ):
        if max_messages < 1 or max_age_seconds <= 0:
            raise ValueError("Session limits must be positive")
        self.backend = backend
        self.max_messages = max_messages
        self.max_age_seconds = max_age_seconds
        self.sessions: dict[str, Session] = {}
        self.by_device: dict[str, str] = {}

    def _expired(self, session: Session, now: float) -> bool:
        return (
            session.messages_sent >= self.max_messages
            or now - session.created_at >= self.max_age_seconds
        )

    def current(self, device_id: str, now: float | None = None) -> Session:
        now = time.time() if now is None else now
        session_id = self.by_device.get(device_id)
        session = self.sessions.get(session_id) if session_id else None
        if session is None or self._expired(session, now):
            established = self.backend.establish_key(device_id)
            session = Session(
                session_id=str(uuid.uuid4()),
                device_id=device_id,
                shared_key=established.shared_key,
                created_at=now,
                messages_sent=0,
                handshake_bytes=established.handshake_bytes,
            )
            self.sessions[session.session_id] = session
            self.by_device[device_id] = session.session_id
        return session

    def mark_sent(self, session: Session) -> None:
        session.messages_sent += 1

    def get_valid(self, session_id: str, device_id: str, now: float | None = None) -> Session:
        now = time.time() if now is None else now
        session = self.sessions.get(session_id)
        if session is None or session.device_id != device_id:
            raise ValueError("Unknown session")
        if now - session.created_at >= self.max_age_seconds:
            raise ValueError("Expired session")
        if self.by_device.get(device_id) != session_id:
            raise ValueError("Superseded session")
        return session
