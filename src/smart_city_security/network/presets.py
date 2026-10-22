from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class NetworkPreset:
    name: str
    latency_ms: float
    jitter_ms: float
    packet_loss: float


PRESETS = {
    "ideal": NetworkPreset("ideal", latency_ms=1.0, jitter_ms=0.2, packet_loss=0.001),
    "congested": NetworkPreset(
        "congested", latency_ms=8.0, jitter_ms=3.0, packet_loss=0.02
    ),
    "degraded": NetworkPreset(
        "degraded", latency_ms=25.0, jitter_ms=10.0, packet_loss=0.08
    ),
}


def get_preset(name: str) -> NetworkPreset:
    try:
        return PRESETS[name]
    except KeyError as exc:
        raise ValueError(f"Unknown network preset: {name}") from exc
