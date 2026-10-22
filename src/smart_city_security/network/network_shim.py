from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Generic, TypeVar

from .presets import NetworkPreset, get_preset

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class Transmission(Generic[T]):
    delivered: bool
    payload: T | None
    delay_ms: float


class NetworkShim:
    def __init__(
        self,
        preset: str | NetworkPreset = "ideal",
        *,
        seed: int = 42,
        sleep: bool = False,
    ):
        self.preset = get_preset(preset) if isinstance(preset, str) else preset
        self.random = random.Random(seed)
        self.sleep = sleep

    def transmit(self, payload: T) -> Transmission[T]:
        dropped = self.random.random() < self.preset.packet_loss
        delay = max(
            0.0,
            self.random.gauss(self.preset.latency_ms, self.preset.jitter_ms),
        )
        if self.sleep and delay:
            time.sleep(delay / 1000)
        return Transmission(not dropped, None if dropped else payload, delay)
