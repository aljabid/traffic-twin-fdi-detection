from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

_T = TypeVar("_T")


class CircuitOpenError(RuntimeError):
    pass


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, recovery_seconds: float = 30) -> None:
        if failure_threshold < 1 or recovery_seconds <= 0:
            raise ValueError("circuit breaker limits must be positive")
        self.failure_threshold = failure_threshold
        self.recovery_seconds = recovery_seconds
        self.failures = 0
        self.opened_at: float | None = None

    @property
    def state(self) -> str:
        if self.opened_at is None:
            return "closed"
        if time.monotonic() - self.opened_at >= self.recovery_seconds:
            return "half_open"
        return "open"

    def call(self, operation: Callable[..., _T], *args: object, **kwargs: object) -> _T:
        if self.state == "open":
            raise CircuitOpenError("dependency circuit is open")
        try:
            result = operation(*args, **kwargs)
        except Exception:
            self.failures += 1
            if self.failures >= self.failure_threshold:
                self.opened_at = time.monotonic()
            raise
        self.failures = 0
        self.opened_at = None
        return result
