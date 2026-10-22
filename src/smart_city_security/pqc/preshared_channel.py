from __future__ import annotations

import os
import time
from collections.abc import Iterable
from dataclasses import dataclass

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from smart_city_security.schemas import SecureMessage, Telemetry
from smart_city_security.security.audit import AuditLog

from .replay_guard import ReplayGuard
from .secure_channel import AuthenticationError

ALGORITHM = "PSK-AESGCM-ECDSA-P256"


@dataclass(frozen=True, slots=True)
class DeviceKey:
    device_id: str
    aes_key: bytes
    public_key_pem: bytes

    def __post_init__(self) -> None:
        if len(self.aes_key) != 32:
            raise ValueError("aes_key must be 32 bytes (AES-256)")


class PreSharedKeyChannel:
    def __init__(
        self,
        device_keys: Iterable[DeviceKey],
        *,
        replay_tolerance_seconds: float = 30,
        audit: AuditLog | None = None,
    ) -> None:
        self._keys = {key.device_id: key for key in device_keys}
        if not self._keys:
            raise ValueError("at least one device key is required")
        self.replay_guard = ReplayGuard(replay_tolerance_seconds)
        self.audit = audit

    def unprotect(self, message: SecureMessage, now: float | None = None) -> Telemetry:
        now = time.time() if now is None else now
        if message.algorithm != ALGORITHM:
            raise AuthenticationError("Unexpected cryptographic algorithm")
        key = self._keys.get(message.device_id)
        if key is None:
            if self.audit:
                self.audit.record(
                    "message_rejected", message.device_id, "failure", "unknown device"
                )
            raise AuthenticationError("Unknown device")

        public_key = serialization.load_pem_public_key(key.public_key_pem)
        if not isinstance(public_key, ec.EllipticCurvePublicKey):
            raise AuthenticationError("Registered key is not an EC public key")
        try:
            public_key.verify(
                message.signature, message.signing_bytes(), ec.ECDSA(hashes.SHA256())
            )
        except InvalidSignature as exc:
            raise AuthenticationError("Invalid message signature") from exc

        self.replay_guard.validate(
            message.device_id,
            message.session_id,
            message.nonce,
            message.sequence_number,
            message.timestamp,
            now,
        )
        try:
            plaintext = AESGCM(key.aes_key).decrypt(
                message.nonce, message.ciphertext, message.session_id.encode()
            )
        except Exception as exc:
            raise AuthenticationError("Ciphertext authentication failed") from exc

        telemetry = Telemetry.from_bytes(plaintext)
        if telemetry.device_id != message.device_id:
            raise AuthenticationError("Device identity mismatch")
        if self.audit:
            self.audit.record("message_accepted", message.device_id)
        return telemetry

    def protect(
        self,
        telemetry: Telemetry,
        aes_key: bytes,
        signing_key_pem: bytes,
        *,
        session_id: str | None = None,
        nonce: bytes | None = None,
        timestamp: int | None = None,
    ) -> SecureMessage:
        session = session_id or f"psk-{telemetry.device_id}"
        nonce = nonce or os.urandom(12)
        ts = int(time.time()) if timestamp is None else timestamp
        ciphertext = AESGCM(aes_key).encrypt(nonce, telemetry.to_bytes(), session.encode())
        message = SecureMessage(
            algorithm=ALGORITHM,
            device_id=telemetry.device_id,
            session_id=session,
            sequence_number=telemetry.sequence_number,
            timestamp=ts,
            nonce=nonce,
            ciphertext=ciphertext,
            signature=b"",
        )
        private_key = serialization.load_pem_private_key(signing_key_pem, password=None)
        if not isinstance(private_key, ec.EllipticCurvePrivateKey):
            raise TypeError("signing key must be an EC private key")
        message.signature = private_key.sign(
            message.signing_bytes(), ec.ECDSA(hashes.SHA256())
        )
        return message
