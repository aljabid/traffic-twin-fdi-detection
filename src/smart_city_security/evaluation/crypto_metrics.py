from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from statistics import fmean
from typing import Any

from smart_city_security.pqc.interfaces import CryptoBackend


@dataclass(frozen=True, slots=True)
class CryptoMetrics:
    algorithm: str
    key_establishment_ms: float
    sign_ms: float
    verify_ms: float
    handshake_bytes: int
    public_key_bytes: int
    signature_bytes: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def benchmark_backend(
    backend: CryptoBackend, repetitions: int = 20, payload: bytes = b"telemetry"
) -> CryptoMetrics:
    if repetitions < 1:
        raise ValueError("repetitions must be positive")
    device_id = "benchmark-device"
    key_times: list[float] = []
    sign_times: list[float] = []
    verify_times: list[float] = []
    handshake_bytes = signature_bytes = 0
    for _ in range(repetitions):
        started = time.perf_counter()
        established = backend.establish_key(device_id)
        key_times.append((time.perf_counter() - started) * 1000)
        handshake_bytes = established.handshake_bytes
        started = time.perf_counter()
        signature = backend.sign(device_id, payload)
        sign_times.append((time.perf_counter() - started) * 1000)
        signature_bytes = len(signature)
        started = time.perf_counter()
        if not backend.verify(device_id, payload, signature):
            raise RuntimeError("Backend failed its sign/verify benchmark")
        verify_times.append((time.perf_counter() - started) * 1000)
    return CryptoMetrics(
        algorithm=backend.name,
        key_establishment_ms=fmean(key_times),
        sign_ms=fmean(sign_times),
        verify_ms=fmean(verify_times),
        handshake_bytes=handshake_bytes,
        public_key_bytes=backend.public_key_size(device_id),
        signature_bytes=signature_bytes,
    )
