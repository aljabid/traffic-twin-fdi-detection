from smart_city_security.integration.benchmark_runner import run_benchmark


def test_benchmark_runner():
    result = run_benchmark("configs/test.yaml", repeats=1)
    assert result["summary"]["n"] == 1
