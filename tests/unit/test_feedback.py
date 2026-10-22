from smart_city_security.ml_detection.feedback import FeedbackStore


def test_operator_feedback_is_recorded():
    item = FeedbackStore().record("a1", "operator-1", "true_positive")
    assert item.recorded_at and item.verdict == "true_positive"
