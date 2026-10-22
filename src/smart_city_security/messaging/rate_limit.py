from __future__ import annotations

import time


class TokenBucket:
    def __init__(self, rate_per_second: float, capacity: float):
        if rate_per_second <= 0 or capacity <= 0:
            raise ValueError("rate and capacity must be positive")
        self.rate = rate_per_second
        self.capacity = capacity
        self.tokens = capacity
        self.updated_at = time.monotonic()

    def allow(self, cost: float = 1.0, now: float | None = None) -> bool:
        if cost <= 0:
            raise ValueError("cost must be positive")
        current = time.monotonic() if now is None else now
        elapsed = max(0.0, current - self.updated_at)
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        self.updated_at = current
        if self.tokens < cost:
            return False
        self.tokens -= cost
        return True
