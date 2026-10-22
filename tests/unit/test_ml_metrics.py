from smart_city_security.evaluation import calculate_ml_metrics


def test_metrics_include_rare_event_measures():
    result = calculate_ml_metrics(
        [False, False, True, True],
        [False, True, False, True],
        [0.1, 0.8, 0.4, 0.9],
    )
    assert result.false_negative_rate == 0.5
    assert result.pr_auc is not None
    assert result.roc_auc is not None
