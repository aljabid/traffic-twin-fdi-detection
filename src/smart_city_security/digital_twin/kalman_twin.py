from __future__ import annotations

import math
from dataclasses import dataclass

from smart_city_security.schemas import Telemetry, TwinState

from .dt_model import TrafficDigitalTwin

SPEED_PROCESS_STD = 3.0
SPEED_MEASUREMENT_STD = 1.0
OCC_PROCESS_STD = 0.02
OCC_MEASUREMENT_STD = 0.02


@dataclass(slots=True)
class _LocalLevel:
    x: float
    p: float

    def predict(self, q: float) -> tuple[float, float]:
        return self.x, self.p + q


def _innovation(track: _LocalLevel | None, z: float, q: float, r: float) -> tuple[float, float]:
    if track is None:
        return z, 0.0
    x_pred, p_pred = track.predict(q)
    return x_pred, abs(z - x_pred) / math.sqrt(p_pred + r)


def _update(track: _LocalLevel | None, z: float, q: float, r: float) -> _LocalLevel:
    if track is None:
        return _LocalLevel(z, r)
    x_pred, p_pred = track.predict(q)
    gain = p_pred / (p_pred + r)
    return _LocalLevel(x_pred + gain * (z - x_pred), (1.0 - gain) * p_pred)


class KalmanTrafficTwin:

    def __init__(self) -> None:
        self._speed: dict[str, _LocalLevel] = {}
        self._occupancy: dict[str, _LocalLevel] = {}
        self._q_s, self._r_s = SPEED_PROCESS_STD**2, SPEED_MEASUREMENT_STD**2
        self._q_o, self._r_o = OCC_PROCESS_STD**2, OCC_MEASUREMENT_STD**2

    def predict(self, telemetry: Telemetry) -> TwinState:
        speed_pred, speed_z = _innovation(
            self._speed.get(telemetry.device_id), telemetry.speed, self._q_s, self._r_s
        )
        occ_pred, occ_z = _innovation(
            self._occupancy.get(telemetry.intersection_id), telemetry.occupancy, self._q_o, self._r_o
        )
        return TwinState(
            intersection_id=telemetry.intersection_id,
            timestamp=telemetry.timestamp,
            predicted_speed=speed_pred,
            observed_speed=telemetry.speed,
            predicted_occupancy=occ_pred,
            observed_occupancy=telemetry.occupancy,
            speed_divergence=speed_z,
            occupancy_divergence=occ_z,
        )

    def commit(self, telemetry: Telemetry) -> None:
        self._speed[telemetry.device_id] = _update(
            self._speed.get(telemetry.device_id), telemetry.speed, self._q_s, self._r_s
        )
        self._occupancy[telemetry.intersection_id] = _update(
            self._occupancy.get(telemetry.intersection_id), telemetry.occupancy, self._q_o, self._r_o
        )

    def observe(self, telemetry: Telemetry) -> TwinState:
        state = self.predict(telemetry)
        self.commit(telemetry)
        return state


TWIN_KINDS = ("window", "kalman")


def make_twin(kind: str = "window", history_window: int = 8) -> TrafficDigitalTwin | KalmanTrafficTwin:
    if kind == "window":
        return TrafficDigitalTwin(history_window)
    if kind == "kalman":
        return KalmanTrafficTwin()
    raise ValueError(f"unknown twin kind: {kind!r}; expected one of {TWIN_KINDS}")
