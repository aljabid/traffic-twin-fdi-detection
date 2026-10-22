from dataclasses import replace

import numpy as np
import pytest

from smart_city_security.integration.alarm_tradeoff import (
    BUDGETS,
    QuantileThreshold,
    alarms_per_vehicle_hour,
    k_of_n,
    run_unit,
)
from smart_city_security.iot_sim import TrafficGenerator


class _Col:
    name = "col"

    def predict(self, features):
        return features[:, 0] > 1e9, features[:, 0]


def test_quantile_threshold_meets_budget():
    benign = np.random.default_rng(0).normal(size=(2000, 2))
    det = QuantileThreshold(_Col(), benign, 0.01)
    flags, _ = det.predict(benign)
    assert np.mean(flags) <= 0.011


def test_k_of_n_and_vehicle_hour_rate():
    base = TrafficGenerator(1, seed=4).generate(6)
    msgs = [replace(m, device_id="d", timestamp=float(i * 60)) for i, m in enumerate(base)]
    assert k_of_n(msgs, [True, True, False, True, True, True], 2, 3) == [False, True, True, True, True, True]
    assert alarms_per_vehicle_hour(msgs, [True, False, True, False, False, False]) == pytest.approx(24.0)


def test_unit_covers_all_budgets_and_rules():
    unit = run_unit(TrafficGenerator(6, seed=3).generate(60), seed=1)
    assert set(unit["budgets"]) == {str(b) for b in BUDGETS}
    for per_detector in unit["budgets"].values():
        assert set(per_detector) == {"forest", "lof", "hybrid", "hybrid_plus"}
        for rules in per_detector.values():
            assert set(rules) == {"1of1", "2of3", "3of5", "4of5"}
