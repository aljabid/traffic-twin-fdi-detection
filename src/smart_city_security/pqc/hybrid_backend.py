from __future__ import annotations

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from .interfaces import CryptoBackend, EstablishedKey


def _pack(first: bytes, second: bytes) -> bytes:
    return len(first).to_bytes(4, "big") + first + second


def _unpack(value: bytes) -> tuple[bytes, bytes]:
    if len(value) < 4:
        raise ValueError("Invalid hybrid signature")
    length = int.from_bytes(value[:4], "big")
    if length < 1 or 4 + length >= len(value):
        raise ValueError("Invalid hybrid signature")
    return value[4 : 4 + length], value[4 + length :]


class HybridBackend(CryptoBackend):

    def __init__(self, classical: CryptoBackend, post_quantum: CryptoBackend):
        self.classical = classical
        self.post_quantum = post_quantum
        self.name = f"HYBRID[{classical.name}|{post_quantum.name}]"

    def establish_key(self, device_id: str) -> EstablishedKey:
        classical = self.classical.establish_key(device_id)
        pqc = self.post_quantum.establish_key(device_id)
        combined = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=f"smart-city-hybrid:{device_id}".encode(),
        ).derive(classical.shared_key + pqc.shared_key)
        return EstablishedKey(
            combined, classical.handshake_bytes + pqc.handshake_bytes
        )

    def sign(self, device_id: str, payload: bytes) -> bytes:
        return _pack(
            self.classical.sign(device_id, payload),
            self.post_quantum.sign(device_id, payload),
        )

    def verify(self, device_id: str, payload: bytes, signature: bytes) -> bool:
        try:
            classical, pqc = _unpack(signature)
        except ValueError:
            return False
        return self.classical.verify(
            device_id, payload, classical
        ) and self.post_quantum.verify(device_id, payload, pqc)

    def public_key_size(self, device_id: str) -> int:
        return self.classical.public_key_size(
            device_id
        ) + self.post_quantum.public_key_size(device_id)
