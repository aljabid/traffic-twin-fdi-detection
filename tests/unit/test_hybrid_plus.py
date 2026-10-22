import numpy as np

from smart_city_security.integration.hybrid_plus import DETECTORS, PlausibleForest, run_unit
from smart_city_security.iot_sim import TrafficGenerator


def test_plausible_forest_uses_extended_features_and_budget():
    rng = np.random.default_rng(0)
    benign = np.abs(rng.normal(1.0, 0.3, size=(800, 9)))
    attacks = benign[:200].copy()
    attacks[:, 3] += 100.0
    forest = PlausibleForest(benign, attacks, seed=1)
    flags, _ = forest.predict(benign)
    assert np.mean(flags) <= 0.12
    assert forest.predict(attacks)[0].mean() > 0.9
    assert forest.model.n_features_in_ == 11


def test_unit_scores_requested_detectors():
    unit = run_unit(TrafficGenerator(6, seed=3).generate(60), seed=1,
                    attacks=["congestion_spoof", "position_spoof"], detectors=list(DETECTORS))
    assert set(unit["scores"]) == set(DETECTORS)
