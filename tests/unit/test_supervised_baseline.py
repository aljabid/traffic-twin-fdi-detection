import numpy as np

from smart_city_security.integration.supervised_baseline import SupervisedDetector, run_unit
from smart_city_security.iot_sim import TrafficGenerator


def test_supervised_detector_meets_fpr_budget_and_separates_classes():
    rng = np.random.default_rng(0)
    benign = rng.normal(0.0, 1.0, size=(600, 4))
    attacks = rng.normal(4.0, 1.0, size=(200, 4))
    detector = SupervisedDetector(benign, attacks, seed=1)
    flags, scores = detector.predict(np.vstack([benign, attacks]))
    assert np.mean(flags[:600]) <= 0.10
    assert np.mean(flags[600:]) > 0.9
    assert np.all((scores >= 0.0) & (scores <= 1.0))


def test_unit_reports_known_and_unseen_settings():
    stream = TrafficGenerator(6, seed=3).generate(60)
    attacks = ["congestion_spoof", "replay_stale"]
    unit = run_unit(stream, seed=1, attacks=attacks)
    for setting in ("known", "unseen"):
        assert set(unit[setting]) == set(attacks)
        for r in unit[setting].values():
            assert r["worst_case"] == min(r["static"], r["adaptive"])
