from smart_city_security.integration.leave_one_out import run_unit
from smart_city_security.iot_sim import TrafficGenerator

DETECTORS = {"forest", "forest_plus", "hybrid", "hybrid_plus"}


def test_unit_scores_seen_and_unseen_per_family():
    families = ["congestion_spoof", "position_spoof"]
    unit = run_unit(TrafficGenerator(6, seed=3).generate(60), seed=1, families=families)
    assert set(unit["seen"]) == set(unit["unseen"]) == DETECTORS
    for block in (unit["seen"]["hybrid_plus"], unit["unseen"]["forest"], unit["lof"]):
        assert set(block) == set(families)
        assert all(0.0 <= s["worst_case"] <= min(s["static"], s["gradient"], s["grid"]) + 1e-12
                   for s in block.values())


def test_category_mode_withholds_the_whole_group():
    families = ["congestion_spoof", "clear_road_spoof", "position_spoof"]
    unit = run_unit(TrafficGenerator(6, seed=3).generate(60), seed=1, families=families, by_category=True)
    assert set(unit) == {"seed", "unseen_category"}
    assert set(unit["unseen_category"]) == DETECTORS
    assert set(unit["unseen_category"]["forest"]) == set(families)
