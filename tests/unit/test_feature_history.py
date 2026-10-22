from dataclasses import replace

import pytest

from smart_city_security.digital_twin import TrafficDigitalTwin
from smart_city_security.iot_sim import TrafficGenerator
from smart_city_security.ml_detection import FeatureBuilder


def _device_stream(n: int = 6) -> list:
    base = TrafficGenerator(1, seed=8).generate(n)
    return [replace(m, speed=10.0 * (i + 1), occupancy=0.1 * (i + 1), timestamp=float(i))
            for i, m in enumerate(base)]


def test_default_history_keeps_the_original_layout():
    assert len(FeatureBuilder(True).feature_names) == 9
    assert len(FeatureBuilder(False).feature_names) == 7


def test_history_appends_previous_readings_most_recent_first():
    builder, twin = FeatureBuilder(True, history=3), TrafficDigitalTwin(8)
    assert builder.feature_names[-4:] == ("speed_lag1", "occupancy_lag1", "speed_lag2", "occupancy_lag2")
    rows = [builder.build(m, twin.observe(m)).values for m in _device_stream()]
    assert len(rows[0]) == 13
    assert list(rows[0][-4:]) == pytest.approx([10.0, 0.1, 10.0, 0.1])
    assert list(rows[3][-4:]) == pytest.approx([30.0, 0.3, 20.0, 0.2])


def test_uncommitted_probes_do_not_enter_the_window():
    builder, twin = FeatureBuilder(False, history=2), TrafficDigitalTwin(8)
    stream = _device_stream(3)
    builder.build(stream[0], twin.observe(stream[0]))
    builder.build(replace(stream[1], speed=999.0), twin.predict(stream[1]), commit=False)
    row = builder.build(stream[1], twin.observe(stream[1])).values
    assert row[-2] == pytest.approx(10.0)


def test_history_must_be_positive():
    with pytest.raises(ValueError):
        FeatureBuilder(True, history=0)
