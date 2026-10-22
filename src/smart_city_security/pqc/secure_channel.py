from __future__ import annotations

import os
import time

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from smart_city_security.schemas import SecureMessage, Telemetry
from smart_city_security.security.audit import AuditLog
from smart_city_security.security.device_registry import DeviceRegistry

from .interfaces import CryptoBackend
from .replay_guard import ReplayGuard
from .session_manager import SessionManager


class AuthenticationError(ValueError):
    pass


class SecureChannel:
    def __init__(
        self,
        backend: CryptoBackend,
        *,
        max_messages: int = 50,
        max_age_seconds: float = 300,
        replay_tolerance_seconds: float = 30,
        registry: DeviceRegistry | None = None,
        audit: AuditLog | None = None,
    ):
        self.backend = backend
        self.sessions = SessionManager(backend, max_messages, max_age_seconds)
        self.replay_guard = ReplayGuard(replay_tolerance_seconds)
        self.registry = registry
        self.audit = audit

    def protect(self, telemetry: Telemetry, now: float | None = None) -> SecureMessage:
        if self.registry and not self.registry.authorize(telemetry.device_id):
            if self.audit: self.audit.record("message_rejected", telemetry.device_id, "failure", "device not enrolled")
            raise AuthenticationError("Device is not enrolled or is revoked")
        now = time.time() if now is None else now
        session = self.sessions.current(telemetry.device_id, now)
        nonce = os.urandom(12)
        ciphertext = AESGCM(session.shared_key).encrypt(
            nonce, telemetry.to_bytes(), session.session_id.encode()
        )
        message = SecureMessage(
            algorithm=self.backend.name,
            device_id=telemetry.device_id,
            session_id=session.session_id,
            sequence_number=telemetry.sequence_number,
            timestamp=now,
            nonce=nonce,
            ciphertext=ciphertext,
            signature=b"",
        )
        message.signature = self.backend.sign(telemetry.device_id, message.signing_bytes())
        self.sessions.mark_sent(session)
        return message

    def unprotect(self, message: SecureMessage, now: float | None = None) -> Telemetry:
        now = time.time() if now is None else now
        if message.algorithm != self.backend.name:
            raise AuthenticationError("Unexpected cryptographic algorithm")
        if not self.backend.verify(
            message.device_id, message.signing_bytes(), message.signature
        ):
            raise AuthenticationError("Invalid message signature")
        session = self.sessions.get_valid(message.session_id, message.device_id, now)
        self.replay_guard.validate(
            message.device_id,
            message.session_id,
            message.nonce,
            message.sequence_number,
            message.timestamp,
            now,
        )
        try:
            plaintext = AESGCM(session.shared_key).decrypt(
                message.nonce, message.ciphertext, message.session_id.encode()
            )
        except Exception as exc:
            raise AuthenticationError("Ciphertext authentication failed") from exc
        telemetry = Telemetry.from_bytes(plaintext)
        if telemetry.device_id != message.device_id:
            raise AuthenticationError("Device identity mismatch")
        if self.audit: self.audit.record("message_accepted", message.device_id)
        return telemetry
