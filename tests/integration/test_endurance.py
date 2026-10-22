from smart_city_security.integration.endurance_runner import run_endurance


def test_short_endurance_run_meets_acceptance_targets():
    report = run_endurance("configs/test.yaml", iterations=2)
    assert report["passed"]
    assert report["handled"] == report["sent"]
    assert report["peak_memory_bytes"] > 0
