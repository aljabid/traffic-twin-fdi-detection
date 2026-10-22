import numpy as np

from smart_city_security.ml_detection.statistical_baseline import OneClassDetector


def test_one_class_baseline():
    model = OneClassDetector(0.2).fit(np.array([[0, 0], [0.1, 0], [0, 0.1], [0.2, 0.1]]))
    labels, _ = model.predict(np.array([[0, 0], [10, 10]]))
    assert len(labels) == 2
