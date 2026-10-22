from smart_city_security.integration.avds_full import MODES, run_unit
from smart_city_security.iot_sim import TrafficGenerator


def test_unit_scores_forest_on_rehearsal_and_test():
    stream = TrafficGenerator(6, seed=3).generate(60)
    attacks = ["congestion_spoof", "replay_stale"]
    unit = run_unit(stream, seed=1, attacks=attacks)
    for split in ("validation", "test"):
        for scores in unit["known"][split].values():
            assert scores["worst_case"] == min(scores[m] for m in MODES)
    for held_out, block in unit["unseen"].items():
        assert held_out not in block["validation"]
        assert set(block["test"]) == {*MODES, "worst_case"}
