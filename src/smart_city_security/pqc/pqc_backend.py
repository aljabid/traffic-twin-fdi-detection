from __future__ import annotations

import hashlib
from typing import Any

from .interfaces import BackendUnavailableError, CryptoBackend, EstablishedKey

try:
    import oqs
except (Exception, SystemExit):
    oqs = None


def _select(enabled: list[str], preferred: tuple[str, ...], kind: str) -> str:
    for name in preferred:
        if name in enabled:
            return name
    raise BackendUnavailableError(f"No supported {kind} algorithm found: {preferred}")


class PQCBackend(CryptoBackend):

    name = "ML-KEM-768+ML-DSA-65"

    def __init__(self) -> None:
        if oqs is None:
            raise BackendUnavailableError(
                "PQC requires liboqs and liboqs-python; install the 'pqc' extra"
            )
        self.kem_algorithm = _select(
            oqs.get_enabled_kem_mechanisms(), ("ML-KEM-768", "Kyber768"), "KEM"
        )
        self.signature_algorithm = _select(
            oqs.get_enabled_sig_mechanisms(), ("ML-DSA-65", "Dilithium3"), "signature"
        )
        self.name = f"{self.kem_algorithm}+{self.signature_algorithm}"
        self._signers: dict[str, Any] = {}
        self._public_keys: dict[str, bytes] = {}

    def _signer(self, device_id: str) -> Any:
        if device_id not in self._signers:
            signer = oqs.Signature(self.signature_algorithm)
            self._public_keys[device_id] = signer.generate_keypair()
            self._signers[device_id] = signer
        return self._signers[device_id]

    def establish_key(self, device_id: str) -> EstablishedKey:
        with oqs.KeyEncapsulation(self.kem_algorithm) as twin:
            twin_public = twin.generate_keypair()
            with oqs.KeyEncapsulation(self.kem_algorithm) as device:
                ciphertext, device_secret = device.encap_secret(twin_public)
            twin_secret = twin.decap_secret(ciphertext)
        if device_secret != twin_secret:
            raise RuntimeError("PQC KEM agreement failed")
        return EstablishedKey(
            hashlib.sha256(device_secret).digest(), len(twin_public) + len(ciphertext)
        )

    def sign(self, device_id: str, payload: bytes) -> bytes:
        return bytes(self._signer(device_id).sign(payload))

    def verify(self, device_id: str, payload: bytes, signature: bytes) -> bool:
        self._signer(device_id)
        with oqs.Signature(self.signature_algorithm) as verifier:
            return bool(verifier.verify(payload, signature, self._public_keys[device_id]))

    def public_key_size(self, device_id: str) -> int:
        self._signer(device_id)
        return len(self._public_keys[device_id])
