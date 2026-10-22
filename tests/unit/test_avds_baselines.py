import numpy as np
import pytest

from smart_city_security.integration.avds_baselines import FusionDetector, run_unit
from smart_city_security.iot_sim import TrafficGenerator


class _Fixed:

    name = "fixed"

    def __init__(self, column: int) -> None:
        self.column = column

    def predict(self, features):
        scores = features[:, self.column]
        return scores > 1e9, scores


def test_fusion_takes_the_larger_percentile_and_meets_the_fpr_budget():
    rng = np.random.default_rng(0)
    train_on = rng.normal(size=(2000, 3))
    train_off = train_on[:, :2]
    fusion = FusionDetector(_Fixed(0), _Fixed(2), train_off, train_on, target_fpr=0.05)
    flags, fused = fusion.predict(train_on)
    assert np.mean(flags) <= 0.05 + 1e-9
    assert np.all((fused >= 0.0) & (fused <= 1.0))
    probe = np.array([[10.0, 0.0, 0.0], [0.0, 0.0, 10.0], [0.0, 0.0, 0.0]])
    flags, _ = fusion.predict(probe)
    assert flags.tolist() == [True, True, False]


@pytest.fixture(scope="module")
def unit():
    stream = TrafficGenerator(6, seed=3).generate(60)
    return run_unit(stream, model="isolation_forest", seed=1, attacks=["congestion_spoof", "replay_stale"])


def test_unit_reports_clean_rule_and_ensemble(unit):
    assert set(unit["clean_validation_fpr"]) == {"false", "true"}
    assert unit["clean_choice"] == (unit["clean_validation_fpr"]["true"] < unit["clean_validation_fpr"]["false"])
    for scores in unit["ensemble"].values():
        assert scores["worst_case"] == min(scores["static"], scores["adaptive"])
        assert 0.0 <= scores["worst_case"] <= 1.0


def test_unit_rehearses_the_ensemble_on_validation(unit):
    assert set(unit["ensemble_validation"]) == set(unit["ensemble"])
    for scores in unit["ensemble_validation"].values():
        assert set(scores) == {"static", "adaptive"}
