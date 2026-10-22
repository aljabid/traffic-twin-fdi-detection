from dataclasses import dataclass


@dataclass(slots=True)
class TwinState:
    intersection_id: str
    timestamp: float
    predicted_speed: float
    observed_speed: float
    predicted_occupancy: float
    observed_occupancy: float
    speed_divergence: float
    occupancy_divergence: float

    @property
    def divergence(self) -> float:
        return self.speed_divergence + self.occupancy_divergence
