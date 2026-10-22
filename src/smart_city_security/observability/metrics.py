from __future__ import annotations

from collections import defaultdict
from threading import RLock


class MetricsRegistry:
    def __init__(self) -> None:
        self._counters: dict[str, float] = defaultdict(float)
        self._observations: dict[str, list[float]] = defaultdict(list)
        self._lock = RLock()

    def increment(self, name: str, amount: float = 1) -> None:
        with self._lock:
            self._counters[name] += amount

    def observe(self, name: str, value: float) -> None:
        with self._lock:
            self._observations[name].append(float(value))

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            observations: dict[str, object] = {}
            for name, values in self._observations.items():
                ordered = sorted(values)
                index = max(0, min(len(ordered) - 1, int(len(ordered) * 0.95)))
                observations[name] = {
                    "count": len(values),
                    "mean": sum(values) / len(values),
                    "p95": ordered[index],
                }
            return {"counters": dict(self._counters), "observations": observations}
