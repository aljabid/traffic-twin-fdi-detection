from __future__ import annotations

import random
import uuid
from dataclasses import replace

from smart_city_security.schemas import GroundTruth, Telemetry

ATTACK_TYPES = ("dos", "injection", "replay", "spoofing")


class AttackInjector:
    def __init__(self, seed: int = 42):
        self.random = random.Random(seed)
        self.replay_sources: dict[str, str] = {}

    def injection(self, message: Telemetry) -> Telemetry:
        return replace(
            message,
            message_id=str(uuid.uuid4()),
            speed=message.speed + self.random.uniform(45, 80),
            position=(message.position + self.random.uniform(300, 600)) % 1000,
        )

    def replay(self, message: Telemetry) -> Telemetry:
        replay_id = str(uuid.uuid4())
        self.replay_sources[replay_id] = message.message_id
        return replace(message, message_id=replay_id)

    def spoofing(self, message: Telemetry) -> Telemetry:
        return replace(
            message,
            message_id=str(uuid.uuid4()),
            device_id=f"spoof-{message.device_id}",
            speed=max(35.0, message.speed * 4),
            device_type="road_sensor",
        )

    def dos(self, message: Telemetry, count: int = 5) -> list[Telemetry]:
        return [
            replace(
                message,
                message_id=str(uuid.uuid4()),
                sequence_number=message.sequence_number + index + 1,
                timestamp=message.timestamp + index * 0.0001,
            )
            for index in range(count)
        ]

    def inject(
        self, messages: list[Telemetry], attack_ratio: float = 0.15
    ) -> tuple[list[Telemetry], dict[str, GroundTruth]]:
        if not 0 <= attack_ratio <= 1:
            raise ValueError("attack_ratio must be between 0 and 1")
        output = list(messages)
        labels = {m.message_id: GroundTruth(m.message_id, "normal") for m in messages}
        attack_count = min(len(messages), round(len(messages) * attack_ratio))
        selected = self.random.sample(messages, attack_count)
        for index, original in enumerate(selected):
            attack_type = ATTACK_TYPES[index % len(ATTACK_TYPES)]
            if attack_type == "dos":
                generated = self.dos(original)
            else:
                generated = [getattr(self, attack_type)(original)]
            for malicious in generated:
                output.append(malicious)
                labels[malicious.message_id] = GroundTruth(
                    malicious.message_id, "attack", attack_type
                )
        output.sort(key=lambda item: item.timestamp)
        return output, labels
