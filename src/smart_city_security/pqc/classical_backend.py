from __future__ import annotations

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from .interfaces import CryptoBackend, EstablishedKey


class ClassicalBackend(CryptoBackend):

    name = "ECDH-P256+ECDSA-P256"

    def __init__(self) -> None:
        self._signing_keys: dict[str, ec.EllipticCurvePrivateKey] = {}

    def _signing_key(self, device_id: str) -> ec.EllipticCurvePrivateKey:
        return self._signing_keys.setdefault(
            device_id, ec.generate_private_key(ec.SECP256R1())
        )

    def establish_key(self, device_id: str) -> EstablishedKey:
        device_key = ec.generate_private_key(ec.SECP256R1())
        twin_key = ec.generate_private_key(ec.SECP256R1())
        device_secret = device_key.exchange(ec.ECDH(), twin_key.public_key())
        twin_secret = twin_key.exchange(ec.ECDH(), device_key.public_key())
        if device_secret != twin_secret:
            raise RuntimeError("ECDH agreement failed")
        shared = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=f"smart-city:{device_id}".encode(),
        ).derive(device_secret)
        device_public = device_key.public_key().public_bytes(
            serialization.Encoding.X962,
            serialization.PublicFormat.UncompressedPoint,
        )
        twin_public = twin_key.public_key().public_bytes(
            serialization.Encoding.X962,
            serialization.PublicFormat.UncompressedPoint,
        )
        return EstablishedKey(shared, len(device_public) + len(twin_public))

    def sign(self, device_id: str, payload: bytes) -> bytes:
        return self._signing_key(device_id).sign(payload, ec.ECDSA(hashes.SHA256()))

    def verify(self, device_id: str, payload: bytes, signature: bytes) -> bool:
        try:
            self._signing_key(device_id).public_key().verify(
                signature, payload, ec.ECDSA(hashes.SHA256())
            )
            return True
        except InvalidSignature:
            return False

    def public_key_size(self, device_id: str) -> int:
        return len(
            self._signing_key(device_id)
            .public_key()
            .public_bytes(
                serialization.Encoding.X962,
                serialization.PublicFormat.UncompressedPoint,
            )
        )
