from __future__ import annotations

from statistics import fmean

from smart_city_security.schemas import Telemetry, TwinState

from .divergence import absolute_divergence
from .dt_state import DigitalTwinState


class TrafficDigitalTwin:

    def __init__(self, history_window: int = 8):
        self.state = DigitalTwinState(history_window)

    def predict(self, telemetry: Telemetry) -> TwinState:
        history = self.state.history(telemetry.intersection_id)
        if history:
            predicted_speed = fmean(item.speed for item in history)
            predicted_occupancy = fmean(item.occupancy for item in history)
        else:
            predicted_speed = telemetry.speed
            predicted_occupancy = telemetry.occupancy
        return TwinState(
            intersection_id=telemetry.intersection_id,
            timestamp=telemetry.timestamp,
            predicted_speed=predicted_speed,
            observed_speed=telemetry.speed,
            predicted_occupancy=predicted_occupancy,
            observed_occupancy=telemetry.occupancy,
            speed_divergence=absolute_divergence(predicted_speed, telemetry.speed),
            occupancy_divergence=absolute_divergence(
                predicted_occupancy, telemetry.occupancy
            ),
        )

    def commit(self, telemetry: Telemetry) -> None:
        self.state.update(telemetry)

    def observe(self, telemetry: Telemetry) -> TwinState:
        twin_state = self.predict(telemetry)
        self.commit(telemetry)
        return twin_state
