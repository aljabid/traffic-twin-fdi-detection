from smart_city_security.evaluation.statistics import summarize_runs


def test_statistics_has_confidence_interval():
    result = summarize_runs([1, 2, 3])
    assert result["ci95_high"] > result["mean"] > result["ci95_low"]
