import numpy as np
import pytest

from smart_city_security.integration.sota_baselines import KalmanChiSquared, plausibility, run_unit
from smart_city_security.iot_sim import TrafficGenerator


def test_plausibility_flags_inconsistent_movement():
    consistent = np.array([[36.0, 0.2, 0.0, 10.0, 1.0, 1.0, 0.0, 0.0, 0.0]])
    jumped = np.array([[36.0, 0.2, 0.0, 160.0, 1.0, 1.0, 0.0, 0.0, 0.0]])
    assert plausibility(consistent)[0, -2] == pytest.approx(0.0)
    assert plausibility(jumped)[0, -2] == pytest.approx(150.0)


def test_kalman_chi2_meets_budget_and_ranks_by_innovation():
    benign = np.random.default_rng(0).normal(size=(4000, 9))
    det = KalmanChiSquared(benign, target_fpr=0.05)
    flags, _ = det.predict(benign)
    assert abs(np.mean(flags) - 0.05) < 0.01
    probe = np.zeros((2, 9))
    probe[1, -2:] = 5.0
    assert det.predict(probe)[0].tolist() == [False, True]


def test_unit_scores_all_three_baselines():
    unit = run_unit(TrafficGenerator(6, seed=3).generate(60), seed=1, attacks=["congestion_spoof", "time_shift"])
    assert set(unit["scores"]) == {"plausibility_knn", "gradient_boosting", "kalman_chi2"}
