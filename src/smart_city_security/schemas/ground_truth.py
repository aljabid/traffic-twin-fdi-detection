from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GroundTruth:
    message_id: str
    label: str
    attack_type: str | None = None

    @property
    def is_attack(self) -> bool:
        return self.label == "attack"
