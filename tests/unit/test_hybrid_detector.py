import numpy as np

from smart_city_security.integration.hybrid_detector import HybridDetector, run_unit
from smart_city_security.integration.supervised_baseline import SupervisedDetector
from smart_city_security.iot_sim import TrafficGenerator


class _ColumnScore:
    name = "column"

    def predict(self, features):
        return features[:, 0] > 1e9, features[:, 0]


def test_hybrid_alarms_when_either_part_is_suspicious():
    rng = np.random.default_rng(0)
    benign = rng.normal(size=(800, 3))
    attacks = benign[:200].copy()
    attacks[:, 2] += 6.0
    forest = SupervisedDetector(benign, attacks, seed=1)
    hybrid = HybridDetector(forest, _ColumnScore(), benign, base_dims=2)
    flags, _ = hybrid.predict(benign)
    assert np.mean(flags) <= 0.12
    probe = np.array([[8.0, 0.0, 0.0], [0.0, 0.0, 6.0], [0.0, 0.0, 0.0]])
    flags, scores = hybrid.predict(probe)
    assert flags[:2].tolist() == [True, True]
    assert np.all((scores >= 0.0) & (scores <= 1.0))


def test_unit_scores_three_detectors_on_rehearsal_and_novel_families():
    stream = TrafficGenerator(6, seed=3).generate(60)
    unit = run_unit(stream, seed=1, rehearsal=["congestion_spoof"], novel=["position_spoof"])
    assert set(unit["scores"]) == {"forest", "lof", "hybrid"}
    for per_attack in unit["scores"].values():
        assert set(per_attack) == {"congestion_spoof", "position_spoof"}
