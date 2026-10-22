import numpy as np

from smart_city_security.evaluation.v2x_datasets import RawMessage
from smart_city_security.integration.veremi_benchmark import SETTINGS, evaluate_window, prepare


def _traffic(kind: str, seed: int) -> list[RawMessage]:
    rng = np.random.default_rng(seed)
    out = []
    for v in range(30):
        attacker = v % 3 == 0
        x, speed = float(rng.uniform(0, 400)), float(rng.uniform(8, 14))
        for t in range(150):
            x += speed
            shown_x = x + (float(rng.uniform(-300, 300)) if attacker and kind == "position" else 0.0)
            shown_speed = speed * 3.6 + (40.0 if attacker and kind == "speed" else 0.0)
            out.append(RawMessage(str(v), float(t) + v * 0.01, shown_x, 5.0 * (v % 4), shown_speed, attacker))
    return out


def test_window_scored_under_all_settings():
    prepared = {"RandomPos": prepare(_traffic("position", 1), "RandomPos"),
                "ConstPos": prepare(_traffic("position", 2), "ConstPos"),
                "ConstSpeedOffset": prepare(_traffic("speed", 3), "ConstSpeedOffset")}
    assert prepared["RandomPos"]["test_labels"].mean() > 0.2
    scores = evaluate_window(prepared, "RandomPos", seed=1)
    assert set(scores) == {"lof", *SETTINGS}
    for setting in SETTINGS:
        assert set(scores[setting]) == {"forest", "forest_plus", "hybrid", "hybrid_plus", "plausibility_knn"}
    assert scores["seen"]["forest_plus"]["f1"] > 0.8
    assert 0.0 <= scores["unseen_category"]["hybrid_plus"]["fpr"] <= 1.0
