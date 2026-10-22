import math

import pytest

from smart_city_security.digital_twin import TrafficDigitalTwin
from smart_city_security.iot_sim import TrafficGenerator
from smart_city_security.ml_detection import FeatureBuilder


def test_log1p_transform_compresses_only_the_divergence_columns():
    stream = TrafficGenerator(3, seed=4).generate(20)
    raw_twin, log_twin = TrafficDigitalTwin(8), TrafficDigitalTwin(8)
    raw, logged = FeatureBuilder(True), FeatureBuilder(True, "log1p")
    for m in stream:
        a = raw.build(m, raw_twin.observe(m)).values
        b = logged.build(m, log_twin.observe(m)).values
        assert list(a[:-2]) == list(b[:-2])
        assert b[-2] == pytest.approx(math.log1p(abs(a[-2])))
        assert b[-1] == pytest.approx(math.log1p(abs(a[-1])))


def test_unknown_transform_is_rejected():
    with pytest.raises(ValueError):
        FeatureBuilder(True, "sqrt")
