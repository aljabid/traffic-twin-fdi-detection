from __future__ import annotations

import random
import time
from dataclasses import dataclass

from smart_city_security.iot_sim.device_profiles import get_profile
from smart_city_security.schemas import Telemetry


@dataclass(slots=True)
class SimulatedDevice:
    device_id: str
    device_type: str
    position: float
    intersection_id: str
    sequence_number: int = 0


class TrafficGenerator:
    def __init__(self, device_count: int = 10, seed: int = 42):
        if device_count < 1:
            raise ValueError("device_count must be positive")
        self.random = random.Random(seed)
        types = ("vehicle", "vehicle", "vehicle", "bus", "road_sensor")
        self.devices = [
            SimulatedDevice(
                device_id=f"device-{index:03d}",
                device_type=types[index % len(types)],
                position=self.random.uniform(0, 1000),
                intersection_id=f"I{index % 5 + 1}",
            )
            for index in range(device_count)
        ]

    def next_message(self, device: SimulatedDevice, timestamp: float | None = None) -> Telemetry:
        profile = get_profile(device.device_type)
        speed = (
            0.0
            if profile.max_speed == 0
            else self.random.uniform(profile.min_speed, profile.max_speed)
        )
        device.position = (device.position + speed / max(profile.publish_rate_hz, 1)) % 1000
        device.sequence_number += 1
        occupancy = min(1.0, max(0.0, self.random.gauss(profile.typical_occupancy, 0.08)))
        signal = self.random.choice(("red", "green", "green", "green", "yellow"))
        return Telemetry.create(
            device_id=device.device_id,
            position=round(device.position, 4),
            speed=round(speed, 4),
            intersection_id=device.intersection_id,
            occupancy=round(occupancy, 4),
            signal_state=signal,
            sequence_number=device.sequence_number,
            timestamp=timestamp,
            device_type=device.device_type,
        )

    def generate(self, messages_per_device: int, start_time: float | None = None) -> list[Telemetry]:
        if messages_per_device < 1:
            return []
        current = time.time() if start_time is None else start_time
        output: list[Telemetry] = []
        for _ in range(messages_per_device):
            for device in self.devices:
                profile = get_profile(device.device_type)
                output.append(self.next_message(device, current))
                current += 1 / profile.publish_rate_hz
        return output


def generate_traffic(device_count: int, messages_per_device: int, seed: int = 42) -> list[Telemetry]:
    return TrafficGenerator(device_count, seed).generate(messages_per_device)
