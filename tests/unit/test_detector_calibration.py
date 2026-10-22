import numpy as np

from smart_city_security.ml_detection.ml_models import IsolationForestDetector


def test_detector_calibrates_declared_training_tail():
    rng = np.random.default_rng(4)
    features = rng.normal(size=(500, 4))
    detector = IsolationForestDetector(contamination=0.04, seed=4).fit(features)
    predictions, _scores = detector.predict(features)
    assert 0.02 <= float(predictions.mean()) <= 0.06
