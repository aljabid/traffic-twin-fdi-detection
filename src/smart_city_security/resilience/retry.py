from __future__ import annotations

import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

_T = TypeVar("_T")


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    attempts: int = 3
    base_delay_seconds: float = 0.05
    max_delay_seconds: float = 1.0
    jitter: float = 0.1

    def execute(self, operation: Callable[..., _T], *args: object, **kwargs: object) -> _T:
        if self.attempts < 1:
            raise ValueError("attempts must be positive")
        for attempt in range(self.attempts):
            try:
                return operation(*args, **kwargs)
            except Exception:
                if attempt + 1 == self.attempts:
                    raise
                delay = min(
                    self.max_delay_seconds,
                    self.base_delay_seconds * (2**attempt),
                )
                delay *= 1 + random.uniform(-self.jitter, self.jitter)
                time.sleep(max(0, delay))
        raise AssertionError("unreachable: loop either returns or raises")
