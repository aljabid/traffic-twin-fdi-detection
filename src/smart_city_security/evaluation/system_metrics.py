from __future__ import annotations

from dataclasses import asdict, dataclass
from statistics import fmean
from typing import Any


@dataclass(frozen=True, slots=True)
class SystemMetrics:
    sent: int
    delivered: int
    rejected: int
    throughput_messages_per_second: float
    mean_latency_ms: float
    p95_latency_ms: float
    mean_wire_bytes: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def calculate_system_metrics(
    sent: int,
    delivered: int,
    rejected: int,
    elapsed_seconds: float,
    latencies_ms: list[float],
    wire_sizes: list[int],
) -> SystemMetrics:
    ordered = sorted(latencies_ms)
    p95_index = max(0, min(len(ordered) - 1, int(len(ordered) * 0.95))) if ordered else 0
    return SystemMetrics(
        sent=sent,
        delivered=delivered,
        rejected=rejected,
        throughput_messages_per_second=delivered / max(elapsed_seconds, 1e-9),
        mean_latency_ms=fmean(latencies_ms) if latencies_ms else 0.0,
        p95_latency_ms=ordered[p95_index] if ordered else 0.0,
        mean_wire_bytes=fmean(wire_sizes) if wire_sizes else 0.0,
    )
