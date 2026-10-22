from dataclasses import replace

import pytest

from smart_city_security.digital_twin import TrafficDigitalTwin
from smart_city_security.digital_twin.kalman_twin import KalmanTrafficTwin, make_twin
from smart_city_security.integration.avds_experiment import run_unit
from smart_city_security.iot_sim import TrafficGenerator


def _vehicle(n: int = 30) -> list:
    base = TrafficGenerator(1, seed=5).generate(n)
    return [replace(m, speed=40.0, occupancy=0.3, timestamp=float(i)) for i, m in enumerate(base)]


def test_first_message_has_no_divergence():
    state = KalmanTrafficTwin().observe(_vehicle(1)[0])
    assert state.speed_divergence == 0.0
    assert state.occupancy_divergence == 0.0


def test_divergence_is_a_normalised_innovation():
    twin = KalmanTrafficTwin()
    stream = _vehicle()
    for m in stream:
        twin.observe(m)
    steady = twin.predict(stream[-1])
    jumped = twin.predict(replace(stream[-1], speed=60.0, occupancy=0.8))
    assert steady.speed_divergence == pytest.approx(0.0, abs=1e-9)
    assert steady.predicted_speed == pytest.approx(40.0)
    assert jumped.speed_divergence > 4.0
    assert jumped.occupancy_divergence > 4.0


def test_speed_is_tracked_per_vehicle():
    twin = KalmanTrafficTwin()
    a = _vehicle(10)
    b = [replace(m, device_id="other", speed=80.0) for m in a]
    for x, y in zip(a, b, strict=True):
        twin.observe(x)
        twin.observe(y)
    assert twin.predict(a[-1]).predicted_speed == pytest.approx(40.0)


def test_make_twin():
    assert isinstance(make_twin("window", 8), TrafficDigitalTwin)
    assert isinstance(make_twin("kalman"), KalmanTrafficTwin)
    with pytest.raises(ValueError):
        make_twin("oracle")


def test_avds_runs_with_the_kalman_twin():
    stream = TrafficGenerator(6, seed=3).generate(60)
    unit = run_unit(stream, model="isolation_forest", seed=1,
                    attacks=["congestion_spoof", "clear_road_spoof"], calibrate=False, twin_kind="kalman")
    assert set(unit["attacks"]) == {"congestion_spoof", "clear_road_spoof"}
