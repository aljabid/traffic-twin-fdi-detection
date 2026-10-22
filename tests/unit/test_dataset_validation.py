from smart_city_security.digital_twin.validation import prediction_metrics


def test_prediction_metrics():
    result = prediction_metrics([1, 3], [2, 2])
    assert result["mae"] == 1
