from smart_city_security.integration.hybrid_robustness import (
    ATTACKS_TESTED,
    NETWORK_PRESETS,
    run_unit,
)
from smart_city_security.iot_sim import TrafficGenerator


def _stream():
    return TrafficGenerator(6, seed=3).generate(60)


def test_network_mode_reports_every_preset_and_detector():
    unit = run_unit(_stream(), seed=1, mode="network")
    assert set(unit["network"]) == set(NETWORK_PRESETS)
    for row in unit["network"].values():
        assert set(row) == {"forest", "lof", "hybrid", "hybrid_plus"}
        for scores in row.values():
            assert 0.0 <= scores["benign_fpr"] <= 1.0
            assert set(ATTACKS_TESTED) <= set(scores)


def test_poisoning_mode_reports_clean_and_poisoned_rates():
    unit = run_unit(_stream(), seed=1, mode="poisoning", poison_rates=(0.1,))
    assert set(unit["poisoning"]) == {"0.0", "0.1"}
